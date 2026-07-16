# dm-dbcore

A SQLAlchemy database connection wrapper with metadata caching, multi-database support (PostgreSQL, MySQL, SQLite), and custom type adapters.

## Features

- **Singleton connection management** - One database connection per application
- **Metadata caching** - Automatic SQLAlchemy metadata caching for faster startup
- **Multi-database support** - Works with PostgreSQL, MySQL, and SQLite
- **Custom type adapters** - NumPy arrays, PostgreSQL geometric types (Point, Polygon, Circle)
- **MySQL utilities** - Read credentials from `.my.cnf` files
- **Automatic staleness detection** - Cache invalidation when schema changes
- **Context managers** - Safe transactional operations with `session_scope()`

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

### Basic Usage

```python
from dm_dbcore import DatabaseConnection, session_scope
from sqlalchemy import text

# Create connection (first time only, required on first call)
db = DatabaseConnection(
    database_connection_string='postgresql+psycopg://user:pass@localhost/mydb',
    cache_name='myapp_cache.pkl'  # Optional: enables metadata caching
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

# PostgreSQL
db = DatabaseConnection('postgresql+psycopg://user:pass@localhost/mydb')

# MySQL
db = DatabaseConnection('mysql://user:pass@localhost/mydb')

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

### NumPy Array Support (PostgreSQL/SQLite)

When you install with NumPy support, you can store/retrieve NumPy arrays:

```python
from dm_dbcore import DatabaseConnection
import numpy as np

db = DatabaseConnection('postgresql+psycopg://localhost/mydb')
# NumPy adapters are automatically loaded for PostgreSQL

# Arrays are automatically converted to/from database format
```

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
│   │   ├── PGPolygon     # PostgreSQL Polygon type
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
from dm_dbcore.adapters import PGPoint, PGPolygon

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
- `metadata`: SQLAlchemy MetaData object
- `database_type`: One of `DBTYPE_POSTGRESQL`, `DBTYPE_MYSQL`, `DBTYPE_SQLITE`

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

**`MetadataCache(dbc, filename, path=None)`**

Manages SQLAlchemy metadata caching.

**Methods:**
- `read()`: Load metadata from cache
- `write(metadata)`: Save metadata to cache
- `cacheIsStale()`: Check if cache needs refresh

### MySQL Utilities

**`read_password_from_my_cnf(host=None, user=None, section=None, mycnf_path='~/.my.cnf')`**

Read password from MySQL configuration file.

**Parameters:**
- `host` (str, optional): Hostname to match (case-sensitive)
- `user` (str, optional): Username to match
- `section` (str, optional): Option group to check (defaults to 'client')
- `mycnf_path` (str): Path to .my.cnf file

**Returns:** Password string or None

**`read_connection_options_from_my_cnf(section=None, mycnf_path='~/.my.cnf')`**

Read all connection options from MySQL configuration file.

**Parameters:**
- `section` (str, optional): Option group to check (defaults to 'client')
- `mycnf_path` (str): Path to .my.cnf file

**Returns:** Dictionary with keys: `host`, `user`, `password`, `database`, `port`

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

MIT License - see LICENSE file for details.

## Author

Demitri Muna

## Links

- GitHub: https://github.com/demitri/dm-dbcore
- PyPI: https://pypi.org/project/dm-dbcore/
- Issues: https://github.com/demitri/dm-dbcore/issues 
