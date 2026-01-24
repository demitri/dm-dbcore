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

```python
from dm_dbcore import DatabaseConnection, session_scope
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    email = Column(String(100))

# Create connection with metadata
db = DatabaseConnection('postgresql+psycopg://user:pass@localhost/mydb')

# Bind models to the connection's metadata
Base.metadata.bind = db.engine

# Query using ORM
with session_scope(db) as session:
    users = session.query(User).filter(User.name.like('John%')).all()
    for user in users:
        print(f"{user.name}: {user.email}")
```

### Metadata Caching

Metadata caching dramatically improves application startup time by storing SQLAlchemy's table reflection data:

```python
# Enable caching by providing a cache filename
db = DatabaseConnection(
    database_connection_string='postgresql+psycopg://localhost/mydb',
    cache_name='myapp_metadata.pkl'
)

# Cache is automatically stored in ~/.sqlalchemy_cache/
# Cache is invalidated automatically when schema changes are detected
```

**PostgreSQL**: Uses `information_schema.columns` to compute schema hash (no manual setup required)

**MySQL**: Uses `information_schema.TABLES` to compute schema hash (no manual setup required)

**SQLite**: Cache is always considered stale (no automatic detection)

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

```python
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import base as pg
from dm_dbcore.adapters import PGPoint, PGPolygon

# Register types with SQLAlchemy
pg.ischema_names['point'] = PGPoint
pg.ischema_names['polygon'] = PGPolygon

# Use in your models
class Location(Base):
    __tablename__ = 'locations'
    id = Column(Integer, primary_key=True)
    coordinates = Column(PGPoint)  # Stores (x, y) tuples
    boundary = Column(PGPolygon)   # Stores list of (x, y) tuples
```

#### Astronomy-Specific Geometric Types

Requires `cornish` library: `pip install dm-dbcore[astronomy]`

```python
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import base as pg
from dm_dbcore.adapters import PGASTCircle, PGASTPolygon

# Register astronomy types
pg.ischema_names['circle'] = PGASTCircle
pg.ischema_names['polygon'] = PGASTPolygon

# Use with astronomical coordinate systems
class AstronomicalObject(Base):
    __tablename__ = 'objects'
    id = Column(Integer, primary_key=True)
    search_region = Column(PGASTCircle)   # Uses cornish.ASTCircle
    footprint = Column(PGASTPolygon)      # Uses cornish.ASTPolygon
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
│   │   ├── PGCitext      # PostgreSQL citext type
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
