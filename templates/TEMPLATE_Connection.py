#!/usr/bin/python
#
# TEMPLATE: Database Connection Module
#
# This template provides a starting point for creating a database connection
# module for your project using the dm-dbcore package.
#
# =============================================================================
# TODO CHECKLIST - Update these items before using this file:
# =============================================================================
# [ ] 1. Replace 'MYPROJECT' with your actual project name
# [ ] 2. Update database connection parameters (host, database, user, etc.)
# [ ] 3. Choose password method: hardcode, environment variable, or password file
# [ ] 4. Update metadata cache filename
# [ ] 5. Test connection with test_connection() function
# [ ] 6. Remove example code and comments when ready for production
# =============================================================================

import os
import logging
from dm_dbcore import DatabaseConnection, session_scope, DBTYPE_POSTGRESQL, DBTYPE_MYSQL, DBTYPE_SQLITE

logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE CONNECTION CONFIGURATION
# =============================================================================

# TODO: Update these values for your database
DB_HOST = 'localhost'
DB_PORT = 5432              # PostgreSQL: 5432, MySQL: 3306
DB_DATABASE = 'myproject_db'
DB_USER = 'myproject_user'

# =============================================================================
# PASSWORD CONFIGURATION
# =============================================================================
# Choose ONE of these methods for handling database passwords:

# METHOD 1: Environment variable (recommended for development/containers)
DB_PASSWORD = os.environ.get('MYPROJECT_DB_PASSWORD', '')

# METHOD 2: Hardcoded (NOT recommended for production!)
# DB_PASSWORD = 'my_secret_password'

# METHOD 3: Password file (recommended for production)
# PostgreSQL uses ~/.pgpass format: hostname:port:database:username:password
# MySQL uses ~/.my.cnf format: [client] section with user/password
# Leave empty string to use password file
# DB_PASSWORD = ''

# =============================================================================
# DATABASE TYPE SELECTION
# =============================================================================
# Choose your database type (uncomment one):

DATABASE_TYPE = DBTYPE_POSTGRESQL
# DATABASE_TYPE = DBTYPE_MYSQL
# DATABASE_TYPE = DBTYPE_SQLITE

# =============================================================================
# METADATA CACHE CONFIGURATION
# =============================================================================
# Metadata caching dramatically improves startup time
# Cache files are stored in ~/.sqlalchemy_cache/

# TODO: Update with your project name
METADATA_CACHE_FILENAME = 'MYPROJECT_metadata.pkl'

# Set to False to disable caching (useful for development when schema changes frequently)
USE_METADATA_CACHE = True

# =============================================================================
# BUILD CONNECTION STRING
# =============================================================================

def build_connection_string():
    """
    Build SQLAlchemy connection string based on database type.

    Returns:
        str: SQLAlchemy connection string
    """
    if DATABASE_TYPE == DBTYPE_POSTGRESQL:
        # PostgreSQL connection string
        if DB_PASSWORD:
            return f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}'
        else:
            # Use ~/.pgpass for password
            return f'postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}'

    elif DATABASE_TYPE == DBTYPE_MYSQL:
        # MySQL connection string
        if DB_PASSWORD:
            return f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}'
        else:
            # Use ~/.my.cnf for password
            return f'mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}'

    elif DATABASE_TYPE == DBTYPE_SQLITE:
        # SQLite connection string (file-based, no user/password)
        # TODO: Update with your SQLite database path
        db_path = '/path/to/your/database.db'
        return f'sqlite:///{db_path}'

    else:
        raise ValueError(f"Unknown database type: {DATABASE_TYPE}")

# =============================================================================
# CONNECTION FACTORY FUNCTIONS
# =============================================================================

def get_database_connection():
    """
    Get or create database connection (singleton pattern).

    On first call, creates the connection with connection string and cache.
    Subsequent calls return the existing connection.

    Returns:
        DatabaseConnection: Database connection instance

    Example:
        >>> db = get_database_connection()
        >>> print(f"Connected to {db.database_type} database")
    """
    connection_string = build_connection_string()

    # First call: create connection with parameters
    # Subsequent calls: return existing singleton (parameters ignored)
    if USE_METADATA_CACHE:
        db = DatabaseConnection(
            database_connection_string=connection_string,
            cache_name=METADATA_CACHE_FILENAME
        )
    else:
        db = DatabaseConnection(
            database_connection_string=connection_string
        )

    return db


def get_session():
    """
    Get a new database session.

    Use this for quick queries or when you want to manage the session manually.
    For transactional operations, prefer using session_scope() context manager.

    Returns:
        Session: SQLAlchemy session

    Example:
        >>> session = get_session()
        >>> try:
        >>>     results = session.query(MyTable).all()
        >>>     session.commit()
        >>> except:
        >>>     session.rollback()
        >>>     raise
        >>> finally:
        >>>     session.close()
    """
    db = get_database_connection()
    return db.Session()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
#
# NOTE: Model classes are configured automatically when imported.
# No explicit loading function is needed. Simply import your model classes:
#
#   from myproject_models import User, Post
#
# The mapper registry and relationships are configured on import via
# @mapper_registry.mapped decorator and configure_mappers() call in the
# model class file.
#
# =============================================================================

def test_connection():
    """
    Test database connection and return basic info.

    Returns:
        dict: Connection information including database type, version, etc.

    Example:
        >>> info = test_connection()
        >>> print(f"Database type: {info['database_type']}")
    """
    db = get_database_connection()

    from sqlalchemy import text

    info = {
        'database_type': db.database_type,
        'connected': False,
        'version': None,
        'error': None
    }

    try:
        with session_scope(db) as session:
            if db.database_type == DBTYPE_POSTGRESQL:
                result = session.execute(text("SELECT version()"))
                info['version'] = result.scalar()
            elif db.database_type == DBTYPE_MYSQL:
                result = session.execute(text("SELECT VERSION()"))
                info['version'] = result.scalar()
            elif db.database_type == DBTYPE_SQLITE:
                result = session.execute(text("SELECT sqlite_version()"))
                info['version'] = result.scalar()

            info['connected'] = True

    except Exception as e:
        info['error'] = str(e)

    return info


def clear_metadata_cache():
    """
    Delete the metadata cache file to force reload on next startup.

    This is useful when the database schema has changed and you want to
    ensure the cache is rebuilt.

    Returns:
        bool: True if cache was deleted or didn't exist
    """
    import pathlib

    cache_dir = pathlib.Path.home() / '.sqlalchemy_cache'
    cache_file = cache_dir / METADATA_CACHE_FILENAME
    hash_file = cache_file.with_suffix('.hash')  # MySQL only

    deleted = False

    if cache_file.exists():
        cache_file.unlink()
        logger.info(f"Deleted metadata cache: {cache_file}")
        deleted = True

    if hash_file.exists():
        hash_file.unlink()
        logger.info(f"Deleted hash file: {hash_file}")
        deleted = True

    if not deleted:
        logger.info("No cache file found to delete")

    return True
