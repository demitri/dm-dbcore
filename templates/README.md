# dm-dbcore Templates

Starting points for a project built on `dm-dbcore`. Copy them into your project, edit the TODO checklist at the top of each, and run each file directly to check it against your live database.

They are a set, not a menu. `TEMPLATE_Connection.py` owns the connection; the model files import from it.

    application code
        |
        v
    TEMPLATE_ModelClasses*.py     model classes + relationships
        |  imports SCHEMA, engine, session_scope
        v
    TEMPLATE_Connection.py        Layer 2: URL, credentials, cache
        |
        v
    dm_dbcore.DatabaseConnection

## The idea

**The database defines the schema. The model file reflects it.**

Every table is reflected with `autoload_with=engine`. You never declare columns: doing so writes the schema down a second time, in a second language, where the copies drift.

```python
class User(Base):
    """A person with an account."""

    __table__ = Table("users", Base.metadata, schema=SCHEMA, autoload_with=engine)
```

Reflection gives you columns and foreign key **constraints**. It does not give you `relationship()` objects — those are a Python concept and are always hand-written. The database says `post.author_id` references `users.id`; whether that surfaces as `post.author` or `user.posts` is your decision, not the database's.

```python
# after every class exists
User.posts = relationship(Post, backref="author")
```

## Why `SCHEMA` lives in the connection module

`SCHEMA` is defined once, in the connection module, and imported by the model files. That one indirection is what makes a model file **byte-identical across backends**. The same `TEMPLATE_ModelClasses.py` runs unchanged against PostgreSQL and SQLite; only the connection module differs:

```python
# PostgreSQL connection module
SCHEMA = "myschema"
# -> postgresql+psycopg://user@localhost:5432/mydb

# SQLite connection module
SCHEMA = None
# -> sqlite:///myproject.sqlite
```

`SCHEMA` is a schema name for PostgreSQL, and `None` for MySQL and SQLite (neither has schemas). Either way it is **always passed** to `Table(...)`, even when the value is `None` — dm-dbcore clears the PostgreSQL `search_path`, so an omitted schema resolves to nothing. An omitted `schema=` is a style-gate violation; an explicit `schema=None` is not.

---

## Which template do I use?

| Situation | Template |
| --- | --- |
| Every project, first | `TEMPLATE_Connection.py` |
| Single schema, any backend | `TEMPLATE_ModelClasses.py` |
| PostgreSQL schemas, JSONB/ARRAY/UUID/geometric types | `TEMPLATE_ModelClasses_PostgreSQL.py` |
| MySQL / MariaDB | `TEMPLATE_ModelClasses_MySQL.py` |
| Foreign keys crossing schemas (or MySQL databases) | `TEMPLATE_CrossSchemaRelationships.py` |

The three ModelClasses templates are the same file with different notes. Start from the generic one unless you need what the specific one explains.

---

## The templates

### `TEMPLATE_Connection.py`

Layer 2 of the three-layer pattern in STYLE_GUIDE.md section 1: it owns the connection details so application code never builds URLs or reads password files.

Copy it once per target database or environment (`myproject/db/connections/LaptopDBConnection.py`). It builds the URL for PostgreSQL, MySQL, or SQLite, creates the `DatabaseConnection` singleton on import, and exports:

| Name | What it is |
| --- | --- |
| `db` | the `DatabaseConnection` singleton |
| `engine` | `db.engine` — hand this to `autoload_with=` |
| `Session` | session factory |
| `SCHEMA` | where your tables live (`None` for MySQL/SQLite) |
| `session_scope()` | transactional context manager; commits on success, rolls back on exception |
| `get_session()` | a bare session; you own commit/rollback/close |

```bash
cp TEMPLATE_Connection.py myproject/db/connections/MyDBConnection.py
python myproject/db/connections/MyDBConnection.py   # prints server version and the tables in SCHEMA
```

### `TEMPLATE_ModelClasses.py`

Model classes for any backend dm-dbcore supports. Reflected classes, a join table reflected as a plain `Table` for `secondary=`, and one-to-many / many-to-many / one-to-one / ambiguous-FK relationship patterns. Ends with `configure_mappers()` so a broken relationship raises at import rather than at the first query.

### `TEMPLATE_ModelClasses_PostgreSQL.py`

Everything in the generic template, plus what is particular to PostgreSQL: schemas (`server -> database -> schema -> table`), and the column types the other backends lack.

JSONB, ARRAY, UUID, TSVECTOR and the geometric types arrive through reflection **already typed** — nothing to declare, nothing to import. A JSONB column hands you a dict and an ARRAY column a list. dm-dbcore registers its adapters (`PGPoint`, `PGPolygon`, `PGCircle`, `PGCIText`, `PGXML`) into the dialect automatically when `DatabaseConnection` sees a PostgreSQL URL. Importing your connection module is the whole setup.

The geometric types hand you their adapter object, not a raw tuple:

| Column | Returns | Access |
|---|---|---|
| `POINT` | `PGPoint` | `.x` `.y` |
| `CIRCLE` | `PGCircle` | `.x` `.y` `.radius` |
| `POLYGON` | `PGPolygon` | `.points` — a NumPy ndarray, so needs `dm-dbcore[numpy]` |

All three round-trip: assign one straight back, or build a new one (`PGPoint((10.25, -3.5))`) and insert it.

Also includes `get_schema_info(session)`, which asks the server what is actually in `SCHEMA` — the useful counterpart to reflection, since it lists tables you have *not* written classes for.

### `TEMPLATE_ModelClasses_MySQL.py`

Everything in the generic template, plus the one thing that trips up everyone arriving from PostgreSQL:

    PostgreSQL:  server -> database -> schema -> table
    MySQL:       server -> database ->           table

A MySQL "database" occupies the slot PostgreSQL gives to a schema. So `SCHEMA` is `None`, and the database name moves into the URL, where it is **not optional**:

    mysql+pymysql://user:pass@host:3306/database
                                       ^^^^^^^^

Storage engine and charset are DDL — properties of the table that already exists — so reflection reads them and this file does not restate them. Set them in your `CREATE TABLE`:

    ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci

InnoDB is not optional if you want relationships: MyISAM parses `FOREIGN KEY` and silently ignores it, so the constraint never exists, reflection finds nothing, and every relationship must be spelled out by hand with `foreign_keys=`. Use `utf8mb4`, not MySQL's `utf8`, which is 3-byte and cannot store emoji or much of CJK.

### `TEMPLATE_CrossSchemaRelationships.py`

For a foreign key that crosses schemas: `content.post.author_id` -> `people.user.id`. There is less to do than you expect — the constraint already exists and reflection reads it, so this file adds only `relationship()` objects, same as any model file. Two rules:

1. **One `Base`, one `MetaData`, for every schema.** Tables that reference each other must share a `MetaData` or SQLAlchemy cannot resolve the foreign key across them. Never a `Base` per schema.
2. **Always pass `schema=` explicitly.**

Once both tables are reflected into the same `MetaData`, a cross-schema relationship is written exactly like any other — nothing in the relationship mentions a schema. The template's `main()` prints the reflected foreign keys and marks the ones that cross.

On MySQL, substitute "database" for "schema" throughout: `schema="otherdb"`. The connecting user needs privileges on both, and both must be on the same server.

---

## The style gate

`scripts/check_style.py` enforces the mechanically-checkable rules in STYLE_GUIDE.md. Run it on the templates, or on the files you derived from them:

```bash
python scripts/check_style.py templates/
python scripts/check_style.py ../myproject/source/myproject/db/
```

Exit status 0 clean, 1 on any violation. It catches: `declarative_base()` / mapper registries / `sqlalchemy.ext.declarative`, `@mapper_registry.mapped`, `Table(...)` missing `autoload_with=` or `schema=`, the removed `autoload=` kwarg, `__tablename__` on a model class, manual `Column()` / `mapped_column()`, missing model docstrings, and `postgresql://` or `postgresql+psycopg2://` URLs. An unparseable file is reported as a violation, not skipped.

It cannot see whether a relationship is *semantically* right, or whether the table exists in the database. Only running the file does that — which is what every template's `main()` is for.

---

## Workflow

```bash
mkdir -p myproject/db/connections myproject/db/models

cp templates/TEMPLATE_Connection.py myproject/db/connections/MyDBConnection.py
# edit: DB_HOST/DB_PORT/DB_DATABASE/DB_USER, SCHEMA, CACHE_NAME; delete unused DB blocks
python myproject/db/connections/MyDBConnection.py

cp templates/TEMPLATE_ModelClasses_PostgreSQL.py myproject/db/models/myschema.py
# edit: fix the import, replace the example classes, define relationships at the bottom
python myproject/db/models/myschema.py

python scripts/check_style.py myproject/db/
```

Then, in your application:

```python
from myproject.db.connections.MyDBConnection import session_scope
from myproject.db.models.myschema import User          # mappings configure on import
from sqlalchemy import select

with session_scope() as session:
    users = session.scalars(select(User)).all()
```

One model file per schema. Keep all of a schema's relationships together; put relationships that cross schemas in their own module that imports from both.

---

## Database-specific notes

### PostgreSQL

- **Driver.** `postgresql+psycopg://` (psycopg v3). A bare `postgresql://` silently selects psycopg2; dm-dbcore rejects anything that is not `postgresql+psycopg://` with a `ValueError`.
- **Passwords.** Put them in `~/.pgpass` (mode 0600), one line per target: `hostname:port:database:username:password`. libpq reads it automatically whenever the URL carries no password. There is nothing to parse and nothing to configure — leave the password empty and it works.
- **search_path.** dm-dbcore clears it on every connection, deliberately. An implicit search_path is what lets `users` mean `core.users` on your laptop and `public.users` in production, silently. Cleared, an unqualified name resolves to nothing and reflection raises `NoSuchTableError` instead of reflecting the wrong table.
- **`db.metadata` is empty for a named schema, by design.** dm-dbcore reflects it at connect time from the *default* schema, with the search_path already cleared. Use `inspect(engine).get_table_names(schema=SCHEMA)`, as `TEMPLATE_Connection.main()` does.
- **Cache staleness.** Detected automatically via `information_schema.columns`; no setup.

### MySQL

- **No schemas.** `SCHEMA = None`; the database name lives in the URL and is required.
- **Passwords.** pymysql does **not** read `~/.my.cnf` the way libpq reads `~/.pgpass`. dm-dbcore supplies the reader:
  ```python
  from dm_dbcore.mysql import read_password_from_my_cnf
  DB_PASSWORD = read_password_from_my_cnf(host=DB_HOST, user=DB_USER)
  ```
- **Cache staleness.** Detected automatically via `information_schema.TABLES`.

### SQLite

- **A file, not a server:** `sqlite:///path/to/database.db`. No host, user, or password.
- **No schemas.** `SCHEMA = None`.
- **No staleness detection.** SQLite caches are always treated as stale.

---

## Common pitfalls

**Declaring columns.** Reflection supplies every column. `Column()` / `mapped_column()` in a model class duplicates the schema and drifts from it.

**Omitting `schema=`.** Required on every `Table(...)`, including `schema=None`. The search_path is cleared; an omitted schema resolves to nothing.

**`autoload=True`.** Removed in SQLAlchemy 2.0 — it raises `TypeError`. The pattern is `__table__ = Table("name", Base.metadata, schema=SCHEMA, autoload_with=engine)`.

**`@mapper_registry.mapped` / `declarative_base()`.** Legacy SQLAlchemy 1.x. Use `class Base(DeclarativeBase)` and inherit from it.

**A bare `postgresql://` URL.** Silently means psycopg2. dm-dbcore raises `ValueError`.

**Ambiguous foreign keys.** Two FKs from one table to the same target and SQLAlchemy cannot guess which one a relationship means — `AmbiguousForeignKeysError`. Name the column:

```python
Comment.author = relationship(
    User,
    backref="comments",
    foreign_keys=[Comment.__table__.c.author_id],
)
```

This is the most common failure in cross-schema models, because a table that reaches into another schema usually also reaches within its own.

**A `Base` per schema.** Cross-schema foreign keys cannot resolve across separate `MetaData` objects. One `Base` per project.

**Declaring `ForeignKey(...)` in Python.** The constraint is already in the database. Write the `relationship()` half only.

**Reflecting a table that does not exist.** Reflection reads; it does not create. `NoSuchTableError` names the table.

---

## Further reading

- `STYLE_GUIDE.md` — the authoritative conventions these templates follow
- `README.md` (repository root) — dm-dbcore itself
- SQLAlchemy: https://docs.sqlalchemy.org/
- PostgreSQL schemas: https://www.postgresql.org/docs/current/ddl-schemas.html
