# dm-dbcore

[![CI](https://github.com/demitri/dm-dbcore/actions/workflows/ci.yml/badge.svg)](https://github.com/demitri/dm-dbcore/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/demitri/dm-dbcore/python-coverage-comment-action-data/endpoint.json)](https://github.com/demitri/dm-dbcore/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)

A SQLAlchemy database connection wrapper with metadata caching, multi-database support (PostgreSQL, MySQL, SQLite), and custom type adapters.

## Features

- **Singleton connection management** - One database connection per application
- **Multi-database support** - Works with PostgreSQL, MySQL, and SQLite
- **Reflection-first models** - The database defines the schema; your classes reflect it
- **Custom type adapters** - NumPy arrays, PostgreSQL geometric types (Point, Polygon, Circle)
- **MySQL utilities** - Read credentials from `.my.cnf` files
- **Context managers** - Safe transactional operations with `session_scope()`
- **Metadata caching** - *experimental, off by default*; see
  [Metadata Caching](#metadata-caching-experimental) for what it does and does not cover

## Installation

### From PyPI

```bash
pip install dm-dbcore
```

### With database-specific drivers

```bash
# PostgreSQL
pip install dm-dbcore[postgresql]

# MySQL
pip install dm-dbcore[mysql]

# NumPy support
pip install dm-dbcore[numpy]

# Astronomy support (PostgreSQL geometric types with cornish)
pip install dm-dbcore[astronomy]

# All extras
pip install dm-dbcore[postgresql,mysql,numpy,astronomy]
```

### From source

```bash
git clone https://github.com/demitri/dm-dbcore.git
cd dm-dbcore
pip install -e .
```

## Quick Start

A complete, runnable program is in [`examples/quickstart.py`](examples/quickstart.py).
It uses SQLite in a temporary directory, so it needs no server and no
configuration, and it is executed by the test suite — if it stops working, CI
says so:

```bash
python examples/quickstart.py
```

### Basic Usage

```python
from dm_dbcore import DatabaseConnection, session_scope
from sqlalchemy import text

# Create connection (first time only, required on first call)
db = DatabaseConnection(
    database_connection_string='postgresql+psycopg://user:pass@localhost/mydb'
)

# Subsequent calls return the same instance (no parameters needed)
db = DatabaseConnection()

# Use the connection with a transactional scope
with session_scope(db) as session:
    result = session.execute(text("SELECT * FROM users"))
    for row in result:
        print(row)
```

### Database Types

```python
from dm_dbcore import DatabaseConnection, DBTYPE_POSTGRESQL, DBTYPE_MYSQL, DBTYPE_SQLITE

# PostgreSQL -- psycopg v3. A bare 'postgresql://' is REJECTED: SQLAlchemy
# silently resolves it to the deprecated psycopg2.
db = DatabaseConnection('postgresql+psycopg://user:pass@localhost/mydb')

# MySQL -- name the driver. A bare 'mysql://' resolves to mysqldb
# (mysqlclient), which this package does not install; the [mysql] extra
# installs pymysql.
db = DatabaseConnection('mysql+pymysql://user:pass@localhost/mydb')

# SQLite
db = DatabaseConnection('sqlite:///path/to/database.db')

# Check database type
print(db.database_type)  # 'postgresql', 'mysql', or 'sqlite'
```

### Using SQLAlchemy ORM Models

The database defines the schema; your model classes reflect it. Columns are
never declared in Python — `autoload_with=` reads them from the live database,
so the two can never drift apart:

```python
from dm_dbcore import DatabaseConnection, session_scope
from sqlalchemy import Table, select
from sqlalchemy.orm import DeclarativeBase

db = DatabaseConnection('postgresql+psycopg://user:pass@localhost/mydb')

class Base(DeclarativeBase):
    pass

class User(Base):
    """A person with an account."""
    __table__ = Table("users", Base.metadata, schema="myschema",
                      autoload_with=db.engine)

# Query using the ORM
with session_scope(db) as session:
    users = session.scalars(
        select(User).where(User.name.like('John%'))
    ).all()
    for user in users:
        print(f"{user.name}: {user.email}")
```

Always pass `schema=` explicitly (use `schema=None` for SQLite and MySQL, which
have no schemas). dm-dbcore clears the PostgreSQL `search_path` on every
connection, so an unqualified table name resolves to nothing rather than
silently reflecting the wrong table.

See [`STYLE_GUIDE.md`](STYLE_GUIDE.md) for the full conventions and
[`templates/`](templates/) for copy-and-edit starting points.

### Metadata Caching (experimental)

Passing `cache_name` pickles SQLAlchemy's table reflection data to
`~/.sqlalchemy_cache/`, so startup can skip re-reflecting the database:

```python
db = DatabaseConnection(
    database_connection_string='postgresql+psycopg://localhost/mydb',
    cache_name='myapp_metadata.pkl'
)
```

**Off by default, and worth understanding before you turn it on.** Three
caveats, all tracked in [`TODO.md`](TODO.md):

- **It may cache nothing useful.** The cache stores `db.metadata`, reflected
  from the database's *default* schema. dm-dbcore clears the PostgreSQL
  `search_path`, so for a project whose tables live in a named schema, that is
  empty. Model classes reflect through their own `Base.metadata`, which this
  cache does not cover.
- **Staleness detection is coarse.** The schema hash covers table and column
  names, broad types, and nullability. It will not notice `VARCHAR(100) →
  VARCHAR(200)`, a changed default, or an added constraint — so it can serve
  stale metadata. On MySQL the hash uses `TABLES.UPDATE_TIME`, which tracks data
  changes rather than schema changes.
- **Writes are strict.** If the cache cannot be written (read-only `$HOME`,
  containers, CI) the error propagates rather than being swallowed: you asked
  for a cache, so silently not making one would be a lie. Do not enable it where
  `$HOME` is not writable.

**SQLite**: no staleness detection at all — the cache is always treated as stale.

## Advanced Features

### Custom Context Manager

```python
from dm_dbcore import DatabaseConnection
from contextlib import contextmanager

db = DatabaseConnection('postgresql+psycopg://localhost/mydb')

@contextmanager
def my_session():
    session = db.Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# Use your custom context manager
with my_session() as session:
    # Your database operations
    pass
```

### NumPy Support (PostgreSQL/SQLite)

Installing with NumPy support lets you pass NumPy values straight to the
database. `DatabaseConnection` loads the adapters when it sees the URL, so
there is nothing to register:

```python
from dm_dbcore import DatabaseConnection
import numpy as np
from sqlalchemy import text

db = DatabaseConnection('postgresql+psycopg://localhost/mydb')

with db.engine.begin() as connection:
    connection.execute(
        text("INSERT INTO measurements (value, spectrum) VALUES (:v, :s)"),
        {"v": np.float64(1.5), "s": np.array([1.0, 2.5, 3.0])},
    )
```

**This is the write direction only.** The adapters registered here are psycopg
*dumpers*: they turn NumPy scalars and `ndarray`s into the literals PostgreSQL
expects (including `NaN`, `Infinity` and `-Infinity`, which `str()` gets
wrong). No loaders are registered, so reading a PostgreSQL array column back
gives you an ordinary Python `list`, not an `ndarray` — wrap it in
`np.array()` yourself if you need one.

**SQLite is narrower still:** the SQLite adapters convert NumPy *scalars*
(`np.int32`, `np.float64`, and so on) to the Python `int`/`float` that the
`sqlite3` module accepts. SQLite has no array type and this package adds no
array support for it.

The one array type that does round-trip in both directions is
`PGPolygon.points` — see below.

### MySQL Utilities

Read database credentials from `.my.cnf` files:

```python
from dm_dbcore.mysql import read_password_from_my_cnf, read_connection_options_from_my_cnf

# Read password for specific host/user
password = read_password_from_my_cnf(host='localhost', user='myuser')

# Read all connection options from .my.cnf
options = read_connection_options_from_my_cnf(section='client')
# Returns: {'host': '...', 'user': '...', 'password': '...', 'database': '...', 'port': ...}
```

### PostgreSQL Geometric Types

#### Standard Geometric Types

Nothing to register and nothing to declare. `DatabaseConnection` installs the
`point`, `polygon`, `circle`, `citext`, and `xml` adapters into the PostgreSQL
dialect as soon as it sees a PostgreSQL URL, so reflection picks them up on its
own:

```python
class Location(Base):
    """A place on a map."""
    __table__ = Table("locations", Base.metadata, schema="myschema",
                      autoload_with=db.engine)

# Reading returns adapter objects, with nothing declared above:
#   location.coordinates -> PGPoint((1.5, 2.5))     .x  .y
#   location.boundary    -> PGPolygon()             .points  (NumPy ndarray)
#   location.region      -> PGCircle((3.0, 4.0), 5.0)   .x  .y  .radius
```

These round-trip: a value read from the database can be assigned straight back
to a geometric column, and you can build new ones in Python
(`PGPoint((10.25, -3.5))`, `PGCircle((1, 2), 7.5)`) and insert them directly.

#### Astronomy-Specific Geometric Types

Requires the `cornish` library: `pip install dm-dbcore[astronomy]`

These are the one case that *does* need manual registration. dm-dbcore
auto-registers the plain `PGCircle` and `PGPolygon`; to get `cornish` objects
instead you must override those entries **before** your model classes are
imported, since reflection reads `ischema_names` at import time:

```python
from sqlalchemy.dialects.postgresql import base as pg
from dm_dbcore.adapters import PGASTCircle, PGASTPolygon

# Override the defaults dm-dbcore installed. Do this before importing models.
pg.ischema_names['circle'] = PGASTCircle
pg.ischema_names['polygon'] = PGASTPolygon

from myproject.db.models import AstronomicalObject  # noqa: E402

# object.search_region is now a cornish.ASTCircle, and object.footprint a
# cornish.ASTPolygon -- again reflected, not declared.
```

## Module Organization

```
dm_dbcore/
├── DatabaseConnection     # Main connection class
├── MetadataCache         # Metadata caching
├── session_scope         # Context manager
├── DBTYPE_*              # Database type constants
├── adapters/             # Custom type adapters
│   ├── postgresql/       # PostgreSQL adapters
│   │   ├── PGPoint       # PostgreSQL Point type
│   │   ├── PGPolygon     # PostgreSQL Polygon type (points are a NumPy ndarray)
│   │   ├── PGCircle      # PostgreSQL Circle type
│   │   ├── PGASTCircle   # Astronomy Circle (requires cornish)
│   │   ├── PGASTPolygon  # Astronomy Polygon (requires cornish)
│   │   ├── PGCIText      # PostgreSQL citext type
│   │   ├── PGXML         # PostgreSQL xml type
│   │   └── numpy_postgresql  # NumPy array adapters for PostgreSQL
│   └── sqlite/           # SQLite adapters
│       └── numpy_sqlite  # NumPy array adapters for SQLite
└── mysql/                # MySQL utilities
    ├── read_password_from_my_cnf
    └── read_connection_options_from_my_cnf
```

### Import Examples

```python
# Core functionality
from dm_dbcore import DatabaseConnection, session_scope
from dm_dbcore import DBTYPE_POSTGRESQL, DBTYPE_MYSQL, DBTYPE_SQLITE

# PostgreSQL geometric types
from dm_dbcore.adapters import PGPoint, PGPolygon, PGCircle
from dm_dbcore.adapters import PGCIText, PGXML

# Astronomy types (requires cornish)
from dm_dbcore.adapters import PGASTCircle, PGASTPolygon

# MySQL utilities
from dm_dbcore.mysql import read_password_from_my_cnf
from dm_dbcore.mysql import read_connection_options_from_my_cnf
```

## API Reference

### DatabaseConnection

**`DatabaseConnection(database_connection_string, cache_name=None)`**

Singleton class for managing database connections.

**Parameters:**
- `database_connection_string` (str, required on first call): SQLAlchemy connection string
- `cache_name` (str, optional): Filename for metadata cache (enables caching)

**Attributes:**
- `engine`: SQLAlchemy Engine object
- `Session`: SQLAlchemy Session factory (scoped)
- `metadata`: SQLAlchemy MetaData object, reflected on construction
- `database_type`: One of `DBTYPE_POSTGRESQL`, `DBTYPE_MYSQL`, `DBTYPE_SQLITE`
- `database_connection_string`: the URL this connection was built from

**Raises:**
- `AssertionError` if no connection string is given and no instance exists yet
- `ValueError` if the URL names no recognised backend — including a bare
  `postgresql://` or an explicit `postgresql+psycopg2://`, both of which are
  rejected rather than quietly resolved to the deprecated psycopg2 driver
- `RuntimeError` if the database cannot be reached; construction fails rather
  than handing back a half-built object

**Singleton caveat:** the *first* caller's URL wins for the lifetime of the
process. A later `DatabaseConnection('some://other/url')` does not open a
second database and does not raise — it returns the existing connection and
ignores the argument.

### session_scope

**`session_scope(db)`**

Context manager for transactional database operations.

**Parameters:**
- `db`: DatabaseConnection instance

**Usage:**
```python
with session_scope(db) as session:
    # Your database operations
    pass  # Automatic commit on success, rollback on exception
```

### MetadataCache

**`MetadataCache(dbc, filename, path='~/.sqlalchemy_cache')`**

Manages SQLAlchemy metadata caching. See
[Metadata Caching](#metadata-caching-experimental) for the caveats — this is
experimental and off unless you ask for it.

**Parameters:**
- `dbc`: the `DatabaseConnection` this cache belongs to
- `filename` (str, **required**): cache filename; omitting it raises
- `path` (str): directory for the cache, created if absent

**Methods:**
- `read()`: Load metadata from the cache. A stale cache is *deleted* and
  `metadata` is left as `None`.
- `write(metadata)`: Pickle the metadata, and for PostgreSQL/MySQL write the
  companion `.hash` file staleness detection needs. Failures propagate —
  caching is opt-in, so silently not doing it would be a lie.
- `cacheIsStale()`: Compare the stored schema hash against the database.
  Always `True` on SQLite, which has no staleness detection.

### MySQL Utilities

Both functions take **keyword arguments only**.

**`read_password_from_my_cnf(*, host=None, user=None, section=None, mycnf_path='~/.my.cnf')`**

Read a password from a MySQL option file.

**Parameters:**
- `host` (str, optional): Hostname to match. `localhost` and `127.0.0.1` are
  treated as the same host; surrounding whitespace is ignored. A group that
  names no host matches any host.
- `user` (str, optional): Username to match (exact)
- `section` (str, optional): Option group to check. If it does not exist, the
  search falls back to `client` and then every other group in file order.
- `mycnf_path` (str): Path to the option file

**Returns:** the password string, or `None` if the file is missing or nothing
matches. Both the `password` and `passwd` spellings are read.

**`read_connection_options_from_my_cnf(*, section=None, mycnf_path='~/.my.cnf')`**

Read connection options from a MySQL option file, with the same group fallback
rules.

**Returns:** a dictionary containing **only the keys that were found** — it is
not a fixed shape, and it is `{}` if the file is missing or has nothing usable.
Possible keys are `host`, `user`, `password`, `database` (also read from `db`
or `schema`), and `port`. Every value is a string; `port` is *not* converted to
an int.

## Development

```bash
pip install -e ".[postgresql,numpy,dev]"

python -m pytest                                            # the test suite
python scripts/check_style.py templates/ dm_dbcore/ examples/  # the STYLE_GUIDE gate
python examples/quickstart.py                               # the usage example
python -m pytest --cov --cov-report=term-missing            # with coverage
```

Most of the suite needs nothing but Python: SQLite is built in, and the type
adapters are checked against the exact text PostgreSQL sends and expects.

The tests that need a live PostgreSQL server are **skipped, not faked**, unless
you point them at one:

```bash
export DM_DBCORE_TEST_PG_URL='postgresql+psycopg://user:pass@localhost:5432/testdb'
python -m pytest -m postgresql
```

CI runs those against a PostgreSQL service container, which is the only place
the geometric and NumPy adapters are proven to round-trip. See
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

One constraint worth knowing: `scripts/check_style.py` needs Python 3.10+
(it inspects `match`-statement AST nodes). That is a limit on the developer
tool, not on the package — the gate is not part of the distribution, and the
package itself is tested across every version below.

## Requirements

- Python 3.8+
- SQLAlchemy 2.0+
- Database drivers:
  - PostgreSQL: `psycopg[binary]`
  - MySQL: `pymysql` or `mysqlclient`
  - SQLite: Built into Python
- Optional dependencies:
  - `numpy` - NumPy array support
  - `cornish` - Astronomy-specific geometric types

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

BSD 3-Clause License - see [LICENSE](LICENSE) file for details.

## Author

Demitri Muna

## Links

- GitHub: https://github.com/demitri/dm-dbcore
- PyPI: https://pypi.org/project/dm-dbcore/
- Issues: https://github.com/demitri/dm-dbcore/issues 
