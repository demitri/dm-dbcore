# Database Connection Pattern (AI Guide)

This document describes a repeatable pattern for wiring database connections
across three layers:

1) dm-dbcore (shared connection utilities)
2) project-core (shared library for a project; includes db wiring and other shared code)
3) project apps (admin, ingestion, viewer, scripts, etc.)

Goal: a project can define one or more connection modules, each of which
builds a SQLAlchemy URL from host/port/user/database/password, prefers a
password file (e.g., `~/.pgpass`) when no explicit password is provided,
and exposes a small stable API (`db`, `engine`, `Session`, `get_session`,
`session_scope`) for application code.

This pattern keeps connection logic out of application code and makes it easy
to swap connection targets by importing a different *Connection module.

## Layer 1: dm-dbcore (shared utilities)

dm-dbcore provides:
- `DatabaseConnection`: a singleton-ish connection wrapper that manages
  SQLAlchemy engine creation and metadata caching.
- `session_scope(db)`: a context manager for transactional sessions.
- Database type constants (PostgreSQL, MySQL, SQLite).

The key interface used by higher layers:
- `DatabaseConnection(database_connection_string=..., cache_name=...)`
- `DatabaseConnection()` (returns the existing singleton)
- `db.engine`, `db.metadata`, `db.Session`
- `session_scope(db)` (transactional scope)

## Layer 2: project-core (project shared library)

Each project creates a `connections/` package inside its core library and
places one file per target connection (e.g., `MacBookDBConnection.py`,
`ProdDBConnection.py`). The core library is not just a DB wrapper; it is the
shared codebase used by all project apps, and this pattern keeps DB wiring
in one place within that shared layer.

Each connection module:
- Defines default host/user/database/port.
- Reads overrides from environment variables.
- Reads a password from `~/.pgpass` when no password is explicitly set.
- Builds the SQLAlchemy URL.
- Instantiates `DatabaseConnection` once and exposes helpers.

Recommended module structure:

1) Defaults + env overrides
   - `_DEFAULT_DB_CONFIG` dict
   - `PROJECT_DB_*`-style environment variables (project-specific prefix)

2) Password resolution
   - If `DB_PASSWORD` is empty, read from `~/.pgpass`
   - Basic `pgpass` parser: split by unescaped `:`, match wildcards

3) URL creation
   - Use `sqlalchemy.engine.URL.create`
   - Prefer `postgresql+psycopg` for PostgreSQL

4) DatabaseConnection singleton
   - Try `DatabaseConnection()` to reuse existing
   - If not initialized, call `DatabaseConnection(database_connection_string=..., cache_name=...)`

5) Exports for application use
   - `db`, `engine`, `metadata`, `Session`
   - `get_session()`
   - `session_scope()` (wrap dm-dbcore `session_scope(db)`)

Example skeleton:

```python
from contextlib import contextmanager
from sqlalchemy.engine import URL
from dm_dbcore import DatabaseConnection, session_scope as _session_scope

# ... config loading and pgpass password lookup ...

database_connection_url = URL.create(
    "postgresql+psycopg",
    username=db_config["user"],
    password=db_config["password"] or None,
    host=db_config["host"],
    port=db_config["port"],
    database=db_config["database"],
)

database_connection_string = database_connection_url.render_as_string(
    hide_password=False
)

try:
    db = DatabaseConnection()
except AssertionError:
    db = DatabaseConnection(
        database_connection_string=database_connection_string,
        cache_name="project_metadata_cache.pickle",
    )

engine = db.engine
metadata = db.metadata
Session = db.Session

def get_session():
    return db.Session()

@contextmanager
def session_scope():
    with _session_scope(db) as session:
        yield session
```

Do not re-export connection modules in `project_core/db/__init__.py`. Keep
connections separate because there may be multiple targets. Apps should
import the specific connection module they need.

## Layer 3: project apps (admin, ingestion, viewers, scripts)

Apps import from the specific connection module:
- `from project_core.db.connections.SomeConnection import db, Session`

Apps should NOT construct URLs or read `.pgpass` directly. They only depend
on the connection module exported by project-core.

Minimal usage example (app code):

```python
from project_core.db.connections.SomeConnection import db, Session
from project_core.db.models import Star

session = Session()
star_count = session.query(Star).count()
print(f"rows: {star_count}")
```

## Environment variables

Use project-specific prefixes to avoid collisions:

```
PROJECT_DB_HOST=127.0.0.1
PROJECT_DB_PORT=5432
PROJECT_DB_USER=your_user
PROJECT_DB_DATABASE=your_db
PROJECT_DB_PASSWORD=            # empty -> use ~/.pgpass
PROJECT_DB_PGPASS=~/.pgpass     # optional override
```

If `PROJECT_DB_PASSWORD` is empty/missing, the connection module should
search `~/.pgpass` for a matching row. Wildcards in pgpass are supported.

## Why this pattern works

- Connection details are centralized per environment.
- All apps use a stable API (`session_scope`, `get_session`) without repeating
  connection logic.
- Metadata caching is consistent and controlled in one place.
- Adding a new database target means adding a new `*Connection.py` module,
  not editing multiple apps.

## Checklist for a new project

- Create `project_core/db/connections/` and one connection module.
- Expose `db`, `engine`, `metadata`, `Session`, `get_session`, `session_scope`.
- Update `project_core/db/__init__.py` to re-export.
- Remove any old `connection.py` to avoid duplicate paths.
- Update docs and scripts to use `PROJECT_DB_*` vars and `.pgpass`.
