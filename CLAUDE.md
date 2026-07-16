# dm-dbcore: AI Agent Instructions

## Style Gate — run it, do not eyeball it

`STYLE_GUIDE.md` is the authority for this project and for projects built on it.
Its mechanically-decidable rules are enforced by a gate. Run it after any change
to model classes, connection modules, or the templates:

```bash
python scripts/check_style.py templates/ dm_dbcore/     # this repo
python scripts/check_style.py path/to/project/db/        # a downstream project
```

Exit status is non-zero on violation. It catches: legacy `declarative_base()` /
`registry()` / `@mapper_registry.mapped`, `__tablename__` + `autoload`, manually
declared columns, `Table()` calls missing `schema=` or `autoload_with=`, missing
model docstrings, and psycopg2 connection URLs.

The gate's docstring lists what it *cannot* see — semantic correctness of
relationships, whether `schema=` names the *right* schema, and runtime-assembled
URLs. Those remain human-review duties; do not assume a green gate means
reviewed.

A green gate is necessary, not sufficient: templates also have a `main()` that
must be run against a live database.

## SQLAlchemy Model Definition Pattern

All SQLAlchemy model classes MUST use **database reflection** to populate column definitions. Do NOT manually declare columns with `mapped_column()`.

### Correct Pattern (reflection)

```python
from sqlalchemy import Table
from project_core.db.models.base import Base
from project_core.db import get_engine

engine = get_engine()

class MyTable(Base):
    """Description of what this table represents."""
    __table__ = Table("my_table", Base.metadata, schema="my_schema", autoload_with=engine)
```

Key points:
- `__table__ = Table(...)` with `autoload_with=engine` reflects all columns from the database
- Always specify `schema=` explicitly (e.g., `"core"`, `"components"`)
- Do NOT declare columns — they come from the database
- Add relationships, properties, and classmethods as needed

### Wrong Pattern (manual columns)

```python
# DO NOT DO THIS
class MyTable(Base):
    __tablename__ = "my_table"
    __table_args__ = {"schema": "my_schema", "extend_existing": True}

    pk: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    some_fk: Mapped[int] = mapped_column(
        ForeignKey("other_schema.other_table.pk"), nullable=False
    )
```

This pattern:
- Duplicates the database schema in Python code
- Can drift from the actual database
- Requires manual updates when columns change
- Fights the framework — SQLAlchemy has reflection for exactly this reason

### Adding Relationships

Define relationships after `__table__`. Use `__table__.c.column_name` for `foreign_keys` and `remote_side` arguments:

```python
class Parent(Base):
    __table__ = Table("parent", Base.metadata, schema="core", autoload_with=engine)

    children = relationship("Child", back_populates="parent")


class Child(Base):
    __table__ = Table("child", Base.metadata, schema="core", autoload_with=engine)

    parent = relationship(
        "Parent",
        back_populates="children",
        foreign_keys=[__table__.c.parent_pk],
    )
```

For self-referential relationships:

```python
class TreeNode(Base):
    __table__ = Table("tree_node", Base.metadata, schema="core", autoload_with=engine)

    parent = relationship(
        "TreeNode",
        remote_side=[__table__.c.pk],
        back_populates="children",
        foreign_keys=[__table__.c.parent_pk],
    )
    children = relationship(
        "TreeNode",
        back_populates="parent",
        foreign_keys=[__table__.c.parent_pk],
    )
```

### Assigning Foreign Keys via Relationships

When creating objects, prefer relationship assignment over raw FK integer assignment:

```python
# Correct — use the relationship
component = DocumentComponent(
    component_type=chunk_type,       # relationship object
    section=abstract_section,        # relationship object
    sequence_in_document=1,
)

# Avoid — directly assigning FK integers
component = DocumentComponent(
    document_component_type_pk=chunk_type.pk,   # raw FK int
    document_section_pk=abstract_section.pk,     # raw FK int
    sequence_in_document=1,
)
```

SQLAlchemy resolves FK values from relationship assignments during flush.

### Joined-Table Inheritance (FK-as-PK)

When a table's PK is also a FK to a parent table (shared-PK inheritance), use relationships for PK propagation instead of manual PK copying:

```python
class ParentTable(Base):
    __table__ = Table("parent", Base.metadata, schema="s", autoload_with=engine)


class ChildTable(Base):
    __table__ = Table("child", Base.metadata, schema="s", autoload_with=engine)

    parent = relationship(
        "ParentTable",
        foreign_keys=[__table__.c.pk],
        lazy="joined",
    )

    @classmethod
    def create(cls, session, **required_fields):
        """Create a ChildTable with its ParentTable row."""
        parent = ParentTable(...)
        child = cls(parent=parent, **required_fields)
        session.add(child)   # Cascades to parent via save-update
        session.flush()       # Single flush materializes PKs
        return child
```

Do NOT do this:

```python
# Wrong — manually threading PKs with intermediate flushes
parent = ParentTable(...)
session.add(parent)
session.flush()             # Flush just to get parent.pk
child = ChildTable(pk=parent.pk, ...)  # Manual PK copy
session.add(child)
session.flush()
```

### Lookup Table Caching Pattern

For small reference/lookup tables, use the `@cached_lookup` class decorator from `base.py`:

```python
from project_core.db.models.base import Base, cached_lookup

@cached_lookup('label')
class LookupTable(Base):
    __table__ = Table("lookup", Base.metadata, schema="core", autoload_with=engine)
```

This automatically adds three classmethods:
- `LookupTable.from_label(session, value)` — cached lookup, raises `ValueError` if not found
- `LookupTable.invalidate_cache(value=None)` — clear one or all cache entries
- `LookupTable.warm_cache(session)` — preload all rows into cache

Decorator parameters:
- `column` (positional): database column to filter on (e.g. `'label'`, `'code'`, `'category_id'`)
- `method_name`: override the lookup method name (default: `from_{column}`)
- `maxsize`: maximum cache entries (default: 256)
- `ttl`: cache TTL in seconds (default: 600)

Examples:

```python
@cached_lookup('label')                                           # → .from_label(session, value)
@cached_lookup('label', maxsize=128)                              # → .from_label(session, value)
@cached_lookup('code', method_name='from_code')                   # → .from_code(session, value)
@cached_lookup('category_id', method_name='from_code', maxsize=1024)  # → .from_code(session, value)
```

The cache stores ORM objects keyed by `(value, id(session))` to avoid detached instance issues across sessions.

### create() Classmethod Pattern

Factory methods belong on the model class as classmethods. They should:
1. Accept only the minimum parameters needed for a valid row (NOT NULL columns)
2. Return the created object — callers set optional properties after
3. Use relationships, not raw FK integers, when the object is available
4. Call `session.flush()` once at the end (not after each `session.add()`)

```python
class MyModel(Base):
    __table__ = Table(...)

    @classmethod
    def create(cls, session, required_field_1, required_field_2) -> "MyModel":
        """Create a MyModel with required fields only.

        Set optional properties on the returned object:
            obj.optional_field = value
        """
        obj = cls(
            required_field_1=required_field_1,
            required_field_2=required_field_2,
        )
        session.add(obj)
        session.flush()
        return obj
```

### Base Class

All models inherit from a shared `DeclarativeBase`. The `base.py` module also provides the `cached_lookup` decorator:

```python
from sqlalchemy.orm import DeclarativeBase
from cachetools import TTLCache

class Base(DeclarativeBase):
    pass

def cached_lookup(column, *, method_name=None, maxsize=256, ttl=600):
    """Class decorator that adds cached lookup classmethods."""
    ...
```

### Database Connection

See `AI_DB_CONNECTION_PATTERN.md` in this repository for database connection wiring across the three-layer architecture (dm-dbcore, project-core, project apps).
