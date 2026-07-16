#!/usr/bin/env python
"""
TEMPLATE: Database connection module.

Copy this to your project as one file per target database or environment, e.g.
`myproject/db/connections/LaptopDBConnection.py`. This is Layer 2 of the
three-layer pattern described in STYLE_GUIDE.md section 1: it owns the
connection details so that application code never builds URLs or reads password
files itself.

    project code  ->  this module  ->  dm_dbcore.DatabaseConnection

=============================================================================
TODO CHECKLIST
=============================================================================
[ ] 1. Rename the file for the target it connects to (e.g. SalmonDBConnection.py)
[ ] 2. Set DB_HOST / DB_PORT / DB_DATABASE / DB_USER below
[ ] 3. Set SCHEMA to the schema holding your tables (None for SQLite/MySQL)
[ ] 4. Set CACHE_NAME to something unique to this project
[ ] 5. Delete the database blocks you do not use
[ ] 6. Run this file directly to test the connection: python ThisFile.py
=============================================================================
"""

import os
from contextlib import contextmanager

from sqlalchemy.engine import URL

from dm_dbcore import (
    DatabaseConnection,
    DBTYPE_MYSQL,
    DBTYPE_POSTGRESQL,
    DBTYPE_SQLITE,
    session_scope as _session_scope,
)

# =============================================================================
# Configuration
# =============================================================================

# TODO: pick the database this module connects to.
DATABASE_TYPE = DBTYPE_POSTGRESQL

# TODO: update for your database. Environment variables let you point the same
# code at a different server without editing it -- use a project-specific
# prefix so different projects do not collide.
DB_HOST = os.environ.get("MYPROJECT_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("MYPROJECT_DB_PORT", 5432))  # PostgreSQL 5432, MySQL 3306
DB_DATABASE = os.environ.get("MYPROJECT_DB_DATABASE", "myproject_db")
DB_USER = os.environ.get("MYPROJECT_DB_USER", "myproject_user")

# Password. Leave this empty to use a password file, which is the recommended
# route -- see "Passwords" below.
DB_PASSWORD = os.environ.get("MYPROJECT_DB_PASSWORD", "")

# SQLite only: path to the database file.
SQLITE_PATH = os.environ.get("MYPROJECT_SQLITE_PATH", "myproject.sqlite")

# The schema holding your tables. Model classes import this and pass it to
# every Table(...) call, so a project that moves schemas changes one line here.
#
#   PostgreSQL: the schema name, e.g. "core". dm-dbcore clears the PostgreSQL
#               search_path on every connection, so this must be explicit.
#   MySQL:      None. MySQL has no schemas; the database name in the URL
#               plays that role.
#   SQLite:     None. SQLite has no schemas.
SCHEMA = "myschema"

# Metadata cache filename, or None to disable. Default: disabled.
#
# Off by default deliberately, on two grounds:
#
#  1. It would not help. The cache stores `db.metadata`, which DatabaseConnection
#     reflects from the database's DEFAULT schema at connect time. On PostgreSQL
#     the search_path is cleared, so the default schema is empty and there is
#     nothing to cache. Your model classes reflect through `Base.metadata` with
#     autoload_with=, which this cache does not cover. See TODO.md: unifying
#     db.metadata, Base.metadata and SCHEMA is a pending design decision.
#
#  2. Enabling it can turn a working connection into a failure. Cache writes are
#     strict -- filesystem and pickle errors propagate rather than being
#     swallowed -- so if $HOME is read-only (containers, CI, shared hosts), asking
#     for a cache you cannot write is an error, by design.
#
# The machinery itself is correct: staleness is detected from a schema hash and
# the cache is rebuilt when the schema changes. Turn it on only once it covers
# metadata you actually use, and only where $HOME is writable.
CACHE_NAME = None

# =============================================================================
# Passwords
# =============================================================================
#
# Do not hardcode passwords. Both supported servers have a password file:
#
# PostgreSQL -- ~/.pgpass, mode 0600, one line per target:
#
#     hostname:port:database:username:password
#
#   libpq reads this automatically whenever the URL carries no password, so
#   this module simply omits it. There is nothing to parse and nothing to
#   configure: leave DB_PASSWORD empty and it works.
#
# MySQL -- ~/.my.cnf. pymysql does NOT read it automatically, so dm-dbcore
#   provides a reader:
#
#     from dm_dbcore.mysql import read_password_from_my_cnf
#     DB_PASSWORD = read_password_from_my_cnf(host=DB_HOST, user=DB_USER)
#
# =============================================================================


def build_connection_url() -> str:
    """Build the SQLAlchemy connection URL for the configured database."""
    if DATABASE_TYPE == DBTYPE_SQLITE:
        # SQLite is a file: no host, user, or password.
        return f"sqlite:///{SQLITE_PATH}"

    if DATABASE_TYPE == DBTYPE_POSTGRESQL:
        # psycopg v3. Do NOT use "postgresql://" -- it silently selects the
        # deprecated psycopg2 driver, which dm-dbcore rejects.
        drivername = "postgresql+psycopg"
    elif DATABASE_TYPE == DBTYPE_MYSQL:
        drivername = "mysql+pymysql"
    else:
        raise ValueError(f"Unsupported database type: {DATABASE_TYPE!r}")

    url = URL.create(
        drivername,
        username=DB_USER,
        password=DB_PASSWORD or None,  # None -> let ~/.pgpass supply it
        host=DB_HOST,
        port=DB_PORT,
        database=DB_DATABASE,
    )
    return url.render_as_string(hide_password=False)


# =============================================================================
# The connection
# =============================================================================
#
# DatabaseConnection is a singleton: the first call builds it, later calls
# return the same object. Calling it with no argument before it exists raises
# AssertionError, so this module creates it on import and every other module
# just imports `db` / `Session` from here.

db = DatabaseConnection(
    database_connection_string=build_connection_url(),
    cache_name=CACHE_NAME,
)

engine = db.engine
metadata = db.metadata
Session = db.Session


def get_session():
    """Return a new session. The caller owns commit/rollback/close."""
    return db.Session()


@contextmanager
def session_scope():
    """Transactional scope: commits on success, rolls back on exception.

    Usage:
        from myproject.db.connections.ThisModule import session_scope

        with session_scope() as session:
            session.add(thing)
    """
    with _session_scope(db) as session:
        yield session


# =============================================================================
# Connection test
# =============================================================================


def main() -> int:
    """Report what this module connects to. Run this file directly to test."""
    from sqlalchemy import inspect, text

    print(f"database type : {db.database_type}")
    print(f"url           : {engine.url}")  # password is masked by SQLAlchemy
    print(f"schema        : {SCHEMA}")

    version_query = {
        DBTYPE_POSTGRESQL: "SELECT version()",
        DBTYPE_MYSQL: "SELECT VERSION()",
        DBTYPE_SQLITE: "SELECT sqlite_version()",
    }[db.database_type]

    with session_scope() as session:
        print(f"server        : {session.execute(text(version_query)).scalar()}")

    # Ask the server what is in SCHEMA. Do NOT use db.metadata here: dm-dbcore
    # reflects it at connect time from the *default* schema, and on PostgreSQL
    # it clears the search_path first -- so db.metadata is legitimately empty
    # for any project that puts its tables in a named schema. That is by
    # design, not a misconfiguration.
    tables = sorted(inspect(engine).get_table_names(schema=SCHEMA))
    print(f"tables in {SCHEMA or 'default'} : {len(tables)}")
    for name in tables:
        print(f"  - {name}")
    if not tables:
        print("  (none -- does SCHEMA match the database, and can this user see it?)")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
