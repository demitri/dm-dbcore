"""
dm-dbcore
=========

SQLAlchemy database connection wrapper with metadata caching and multi-database support.

Main components:
- DatabaseConnection: Singleton connection manager with metadata caching
- MetadataCache: Automatic SQLAlchemy metadata caching for improved performance
- session_scope: Context manager for transactional database operations
- Database type constants: DBTYPE_POSTGRESQL, DBTYPE_MYSQL, DBTYPE_SQLITE
- MySQL utilities: read_password_from_my_cnf, read_connection_options_from_my_cnf

Example usage:
    >>> from dm_dbcore import DatabaseConnection, session_scope, DBTYPE_POSTGRESQL
    >>>
    >>> # Create connection (first time only)
    >>> db = DatabaseConnection(
    ...     database_connection_string='postgresql+psycopg://user:pass@localhost/mydb',
    ...     cache_name='myapp_cache.pkl'
    ... )
    >>>
    >>> # Subsequent calls return the same instance
    >>> db = DatabaseConnection()
    >>>
    >>> # Use in a transactional scope
    >>> with session_scope(db) as session:
    ...     results = session.execute(text("SELECT * FROM mytable"))
    ...     for row in results:
    ...         print(row)
    >>>
    >>> # MySQL utilities for reading credentials
    >>> from dm_dbcore.mysql import read_password_from_my_cnf
    >>> password = read_password_from_my_cnf(host='localhost', user='myuser')
"""

from .DatabaseConnection import (
    DatabaseConnection,
    MetadataCache,
    session_scope,
    DBTYPE_POSTGRESQL,
    DBTYPE_MYSQL,
    DBTYPE_SQLITE,
)

__version__ = "0.1.0"
__author__ = "Demitri Muna"

__all__ = [
    "DatabaseConnection",
    "MetadataCache",
    "session_scope",
    "DBTYPE_POSTGRESQL",
    "DBTYPE_MYSQL",
    "DBTYPE_SQLITE",
]
