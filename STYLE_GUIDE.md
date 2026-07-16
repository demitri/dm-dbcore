# dm-dbcore Style Guide

This guide describes the conventions and patterns for projects built on top of `dm-dbcore`. It covers database connections, SQLAlchemy model class definitions, relationships, and common patterns. Follow these conventions for consistency across projects.

Both human developers and AI agents should follow this guide when writing or modifying code that uses `dm-dbcore`.

---

## Table of Contents

1. [Database Connections](#1-database-connections)
2. [Base Class and Declarative Setup](#2-base-class-and-declarative-setup)
3. [Model Class Definitions](#3-model-class-definitions)
4. [Relationships](#4-relationships)
5. [Lookup Tables and Caching](#5-lookup-tables-and-caching)
6. [Factory Methods (`create` classmethods)](#6-factory-methods-create-classmethods)
7. [Custom `__init__` and Validation](#7-custom-__init__-and-validation)
8. [Sessions and Queries](#8-sessions-and-queries)
9. [File and Module Organization](#9-file-and-module-organization)
10. [Common Mistakes](#10-common-mistakes)

---

## 1. Database Connections

### Three-Layer Architecture

Database connections follow a three-layer pattern:

1. **dm-dbcore** provides `DatabaseConnection` (singleton), `session_scope`, and adapters.
2. **project-core** creates connection modules (`*Connection.py`) that build the SQLAlchemy URL, read credentials from `~/.pgpass` or environment variables, and expose `db`, `engine`, `Session`, `get_session`, and `session_scope`.
3. **Application code** imports from the project-core connection module. Applications never construct URLs or read password files directly.

### Connection Strings

Use the `psycopg` (v3) driver for PostgreSQL:

```python
# Correct
"postgresql+psycopg://user@localhost:5432/mydb"

# Deprecated — do not use psycopg2 for new projects
"postgresql+psycopg2://user@localhost:5432/mydb"
```

### Singleton Pattern

`DatabaseConnection` is a singleton. The first call requires the connection string; subsequent calls return the existing instance:

```python
from dm_dbcore import DatabaseConnection

# First call — initializes the connection
db = DatabaseConnection(
    database_connection_string="postgresql+psycopg://user@localhost/mydb",
    cache_name="myproject_metadata.pkl",
)

# All subsequent calls — returns the same instance
db = DatabaseConnection()
```

### Session Usage

Use `session_scope` for transactional blocks. It commits on success and rolls back on exception:

```python
from project_core.db.connections.MyConnection import db, session_scope

with session_scope() as session:
    results = session.execute(text("SELECT count(*) FROM core.document"))
```

For non-transactional or long-lived sessions, use `Session()` directly and manage commit/rollback yourself.

---

## 2. Base Class and Declarative Setup

### Use `DeclarativeBase` (SQLAlchemy 2.x)

Define a single `Base` class per project using SQLAlchemy 2.x style:

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### Do Not Use Legacy APIs

The following are SQLAlchemy 1.x patterns. Do not use them in new code:

```python
# WRONG — legacy 1.x declarative_base function
from sqlalchemy.orm import declarative_base
Base = declarative_base()

# WRONG — legacy 1.x registry
from sqlalchemy.orm import registry
mapper_registry = registry()

# WRONG — legacy 1.x ext import
from sqlalchemy.ext.declarative import declarative_base
```

### Do Not Use `@mapper_registry.mapped`

The `@mapper_registry.mapped` decorator is a legacy SQLAlchemy pattern. All model classes should inherit from `Base` instead:

```python
# WRONG
@mapper_registry.mapped
class MyTable:
    __table__ = Table(...)

# CORRECT
class MyTable(Base):
    __table__ = Table(...)
```

---

## 3. Model Class Definitions

### Use Database Reflection

All model classes **must** use table reflection to populate columns. Do not manually declare columns with `mapped_column()` or `Column()`.

```python
from sqlalchemy import Table
from project_core.db.models.base import Base
from project_core.db import get_engine

engine = get_engine()


class Document(Base):
    """Root document table representing the conceptual work."""

    __table__ = Table("document", Base.metadata, schema="core", autoload_with=engine)
```

### Always Specify the Schema

Every `Table(...)` call must include an explicit `schema=` argument:

```python
# CORRECT
__table__ = Table("my_table", Base.metadata, schema="core", autoload_with=engine)

# WRONG — relies on search_path
__table__ = Table("my_table", Base.metadata, autoload_with=engine)
```

This is especially important because `dm-dbcore` clears the PostgreSQL `search_path` on every connection to prevent cross-schema ambiguity.

### Do Not Declare Columns Manually

Reflected tables already have all columns. Do not duplicate them:

```python
# WRONG — manual column declarations duplicate the schema
class MyTable(Base):
    __tablename__ = "my_table"
    __table_args__ = {"schema": "core"}

    pk: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
```

### Do Not Use `__tablename__` with `autoload`

Use `__table__ = Table(...)` with `autoload_with=`, not `__tablename__` with `__table_args__`:

```python
# WRONG — legacy autoload pattern
class MyTable(Base):
    __tablename__ = "my_table"
    __table_args__ = {"schema": "core", "autoload": True}
    id = Column(Integer, primary_key=True)

# CORRECT — explicit Table reflection
class MyTable(Base):
    __table__ = Table("my_table", Base.metadata, schema="core", autoload_with=engine)
```

### Class Docstrings

Every model class should have a brief one-line docstring describing what the table represents:

```python
class AnnotationType(Base):
    """Types of annotations (description, generated_question, etc.)."""

    __table__ = Table(...)
```

### Section Comments

Group related model classes under section headers:

```python
# =============================================================================
# Documents
# =============================================================================

class Document(Base):
    ...

class DocumentVersion(Base):
    ...
```

### Suppress Reflection Warnings

At the top of model class files, suppress harmless SQLAlchemy reflection warnings:

```python
import warnings
warnings.filterwarnings(action="ignore", message="Skipped unsupported reflection")
```

---

## 4. Relationships

### Define Relationships After All Classes

Define relationships at the bottom of the model file, after all classes are declared. This avoids forward-reference issues and keeps class bodies focused on table reflection:

```python
# --- Model classes ---

class Document(Base):
    """Root document table."""
    __table__ = Table("document", Base.metadata, schema="core", autoload_with=engine)


class DocumentType(Base):
    """Types of documents."""
    __table__ = Table("document_type", Base.metadata, schema="core", autoload_with=engine)


# --- Relationships ---

Document.document_type = relationship(DocumentType, backref="documents")
```

### Use `back_populates` for New Code

Prefer `back_populates` over `backref`. The `back_populates` pattern is explicit and easier to follow:

```python
# PREFERRED — explicit on both sides
class Parent(Base):
    __table__ = Table("parent", Base.metadata, schema="core", autoload_with=engine)
    children = relationship("Child", back_populates="parent")


class Child(Base):
    __table__ = Table("child", Base.metadata, schema="core", autoload_with=engine)
    parent = relationship("Parent", back_populates="children",
                          foreign_keys=[__table__.c.parent_pk])
```

`backref` is acceptable in existing code and when defining relationships outside the class body (the post-class pattern), where it is more concise:

```python
# Acceptable — post-class relationship definition
Document.document_type = relationship(DocumentType, backref="documents")
```

### Specify `foreign_keys` When Ambiguous

If a table has multiple foreign keys to the same target, you must specify `foreign_keys`:

```python
AnnotationRun.large_language_model = relationship(
    LargeLanguageModel,
    backref="annotation_runs",
    foreign_keys=[AnnotationRun.__table__.c.large_language_model_pk],
)
```

### Self-Referential Relationships

Use `remote_side` for self-referential (tree) relationships:

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

### Many-to-Many Relationships

Use the `secondary` parameter with the join table's `__table__` attribute:

```python
DocumentVersion.authors = relationship(
    Author,
    secondary=DocumentVersionToAuthor.__table__,
    backref="document_versions",
)
```

### Use `enable_typechecks=False` with Concrete Inheritance

When using PostgreSQL concrete table inheritance (e.g., subtypes that use `INHERITS`), add `enable_typechecks=False` to relationships that touch those tables:

```python
Document.versions = relationship(
    DocumentVersion,
    backref=backref("document", enable_typechecks=False),
    enable_typechecks=False,
    passive_deletes=True,
)
```

### Assign Relationships, Not Raw FK Integers

When creating objects, prefer setting the relationship attribute over the raw FK column:

```python
# CORRECT — use the relationship
component.section = abstract_section

# AVOID — directly assigning FK integers
component.document_section_pk = abstract_section.pk
```

---

## 5. Lookup Tables and Caching

### Use `@cached_lookup` for Small Reference Tables

The `cached_lookup` decorator adds a cached classmethod for looking up rows by a column value:

```python
from project_core.db.models.base import Base, cached_lookup

@cached_lookup('short_name')
class DocumentType(Base):
    """Types of documents (arxiv-paper, textbook, etc.)."""

    __table__ = Table("document_type", Base.metadata, schema="core", autoload_with=engine)
```

This adds:
- `DocumentType.from_short_name(session, value)` — cached lookup, raises `ValueError` if not found
- `DocumentType.invalidate_cache(value=None)` — clear one or all cache entries
- `DocumentType.warm_cache(session)` — preload all rows

### Decorator Parameters

```python
@cached_lookup('label')                           # -> .from_label(session, value)
@cached_lookup('code', method_name='from_code')   # -> .from_code(session, value)
@cached_lookup('short_name', maxsize=128)          # smaller cache
@cached_lookup('label', maxsize=1024, ttl=300)     # larger cache, 5-minute TTL
```

### Module-Level Constants for Common Lookup Values

Define constants for frequently used lookup values at the top of the module:

```python
DOCUMENT_TYPE_ARXIV_PAPER = "arxiv-paper"
DOCUMENT_TYPE_USPTO_PATENT = "uspto-patent"
DOCUMENT_TYPE_TEXTBOOK = "textbook"
```

---

## 6. Factory Methods (`create` Classmethods)

### Pattern

Factory methods belong on the model class as `@classmethod` methods named `create`. They should:

1. Accept only the minimum parameters needed for a valid row (NOT NULL columns without defaults).
2. Return the created object so callers can set optional properties after.
3. Use relationships, not raw FK integers.
4. Call `session.flush()` once at the end.

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

### Joined-Table Inheritance (FK-as-PK)

When a child table's PK is also a FK to a parent table, use relationship assignment for PK propagation. Do not manually copy PKs with intermediate flushes:

```python
# CORRECT — single flush, PK propagates via relationship
@classmethod
def create(cls, session, **fields):
    parent = ParentTable(...)
    child = cls(parent=parent, **fields)
    session.add(child)
    session.flush()
    return child

# WRONG — manual PK threading with intermediate flushes
parent = ParentTable(...)
session.add(parent)
session.flush()          # flush just to get parent.pk
child = ChildTable(pk=parent.pk, ...)
```

---

## 7. Custom `__init__` and Validation

### Custom `__init__`

Use custom `__init__` methods when a model requires validation or computed fields at creation time. Always call `super().__init__()`:

```python
class DocumentKeyword(Base):
    __table__ = Table("document_keyword", Base.metadata, schema="core", autoload_with=engine)

    def __init__(self, keyword: str):
        if not keyword or not keyword.strip():
            raise ValueError("keyword is required")
        super().__init__(keyword=keyword.strip())
```

### Use `@validates` for Derived Fields

Use SQLAlchemy's `@validates` decorator to auto-compute derived columns when a source column is set:

```python
from sqlalchemy.orm import validates

class DocumentSource(Base):
    __table__ = Table("document_source", Base.metadata, schema="core", autoload_with=engine)

    @validates('source_text')
    def _set_derived_from_source_text(self, key, value):
        """Auto-compute source_hash and char_count when source_text is set."""
        if value is None:
            raise ValueError("source_text is required")
        self.source_hash = hashlib.sha256(value.encode("utf-8")).digest()
        self.char_count = len(value)
        return value
```

---

## 8. Sessions and Queries

### Use SQLAlchemy 2.x Query Style

Use `session.execute(select(...))` instead of the legacy `session.query(...)`:

```python
from sqlalchemy import select

# CORRECT — 2.x style
stmt = select(Document).where(Document.__table__.c.pk == 42)
doc = session.execute(stmt).scalar_one()

# LEGACY — still works, but not preferred for new code
doc = session.query(Document).filter_by(pk=42).one()
```

### Use `session.scalars()` for Collections

```python
docs = session.scalars(select(Document)).all()
```

### Use `session.get()` for Primary Key Lookups

```python
doc = session.get(Document, 42)
```

---

## 9. File and Module Organization

### Standard Model File Structure

```python
"""Docstring describing the schema and what it contains."""

import warnings
from sqlalchemy import Table
from sqlalchemy.orm import relationship, backref
from project_core.db.models.base import Base, cached_lookup
from project_core.db import get_engine

warnings.filterwarnings(action="ignore", message="Skipped unsupported reflection")

engine = get_engine()

# =============================================================================
# Section: Group Name
# =============================================================================

class ModelA(Base):
    """What ModelA represents."""
    __table__ = Table("model_a", Base.metadata, schema="myschema", autoload_with=engine)


class ModelB(Base):
    """What ModelB represents."""
    __table__ = Table("model_b", Base.metadata, schema="myschema", autoload_with=engine)


# =============================================================================
# Relationships
# =============================================================================

ModelA.model_bs = relationship(ModelB, backref="model_a")
```

### One File Per Schema

Organize model classes into one Python file per database schema. If a schema is very large, split into logical sub-modules but keep all relationships for that schema together.

### Cross-Schema Relationships

When models in different schemas relate to each other, define those relationships in a separate module that imports from both schema files. Always use fully-qualified schema names in `ForeignKey` references:

```python
ForeignKey("other_schema.other_table.pk")  # schema-qualified
```

### Connection Modules

Place connection modules in `project_core/db/connections/`. One file per target database or environment. Do not re-export connection modules from `__init__.py` if there are multiple targets.

---

## 10. Common Mistakes

### Declaring Columns Manually

Reflection handles all columns. Manual `mapped_column()` or `Column()` declarations duplicate the schema and can drift from the database.

### Forgetting `schema=` in Table Reflection

Every `Table(...)` call must include `schema=`. Without it, SQLAlchemy relies on `search_path`, which `dm-dbcore` clears.

### Using `__tablename__` + `autoload`

The `__tablename__` / `__table_args__` / `autoload` pattern is legacy. Use `__table__ = Table(..., autoload_with=engine)` instead.

### Using `declarative_base()` Instead of `DeclarativeBase`

The function `declarative_base()` is SQLAlchemy 1.x. Use the `DeclarativeBase` class for 2.x.

### Using `@mapper_registry.mapped`

This decorator is a legacy mapping pattern. Inherit from `Base` instead.

### Manually Threading PKs with Multiple Flushes

When a child table's PK is a FK to a parent, use relationship assignment and a single `session.flush()`. Do not flush the parent separately just to read its PK.

### Using `session.query()` in New Code

Prefer `session.execute(select(...))` for new code. The `session.query()` API is legacy 1.x style.

### Assigning Raw FK Integers

When the related object is available, assign via the relationship attribute rather than the integer FK column.

---

## Summary of Imports

```python
# dm-dbcore
from dm_dbcore import DatabaseConnection, session_scope
from dm_dbcore import DBTYPE_POSTGRESQL, DBTYPE_MYSQL, DBTYPE_SQLITE

# SQLAlchemy 2.x
from sqlalchemy import Table, select, func, text
from sqlalchemy.orm import DeclarativeBase, relationship, backref, validates, Session

# Project base
from project_core.db.models.base import Base, cached_lookup
from project_core.db import get_engine
```
