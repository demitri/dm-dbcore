#!/usr/bin/env python
"""
Guided demo of dm-dbcore, run against a live database.

NOTE: despite the name, this is a demonstration script, not a pytest suite.
Importing it does nothing -- every step below runs only from main().

It walks the four things a project built on dm-dbcore does, in order, and prints
what each one produced:

    1. Connect          -- DatabaseConnection, the singleton every module shares.
    2. Metadata cache   -- reflection is slow; the cache makes startup fast.
    3. session_scope    -- the transactional block: commit on success, roll back
                           on exception.
    4. Model classes    -- a class whose columns are REFLECTED from the database
                           rather than declared. This is the pattern; see
                           STYLE_GUIDE.md section 3 and templates/.

Step 4 builds a real model class against a real table, so what it prints is
proof the pattern works here, not an illustration of it.

Usage:

    python test_dm_dbcore.py postgresql+psycopg://user@localhost:5432/mydb --schema core
    python test_dm_dbcore.py sqlite:///local.sqlite --table users

    DM_DBCORE_TEST_URL=sqlite:///local.sqlite python test_dm_dbcore.py

Options:

    --schema S   schema holding the tables; omit for SQLite/MySQL
    --table T    table to reflect in step 4 (default: the first one found)

Passwords belong in ~/.pgpass or ~/.my.cnf, not on the command line -- omit the
password from the URL and the driver's password file supplies it.

For a plain connection check with none of this narration, use
scripts/db_connection_test.py instead.
"""

import argparse
import os
import sys

CACHE_NAME = "dm_dbcore_demo_metadata.pkl"


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# =============================================================================
# 1. Connect
# =============================================================================


def demo_connection(url: str):
    """Create the DatabaseConnection singleton. Returns the db object."""
    banner("1. CONNECTION")

    from dm_dbcore import DatabaseConnection

    # The first call needs the URL; every later DatabaseConnection() call
    # anywhere in the process returns this same object. That is why a project
    # has one connection module that everything else imports from.
    db = DatabaseConnection(database_connection_string=url, cache_name=CACHE_NAME)

    print(f"database type : {db.database_type}")
    print(f"url           : {db.engine.url}")  # password is masked by SQLAlchemy
    print("The same object is returned by any later DatabaseConnection() call.")
    return db


# =============================================================================
# 2. Metadata cache
# =============================================================================


def demo_metadata_cache(db) -> None:
    """Report the reflected metadata and where it is cached."""
    banner("2. METADATA CACHE")

    import datetime
    import pathlib

    tables = sorted(db.metadata.tables) if db.metadata is not None else []
    print(f"tables reflected into db.metadata : {len(tables)}")
    for name in tables[:5]:
        print(f"  - {name}")
    if len(tables) > 5:
        print(f"  ... and {len(tables) - 5} more")
    if not tables:
        # Not a failure. dm-dbcore reflects the DEFAULT schema at connect time
        # and clears the PostgreSQL search_path first, so a project whose tables
        # live in a named schema legitimately sees nothing here. Step 4 reflects
        # from the named schema explicitly, which is how models do it.
        print("  (empty -- expected when the tables live in a named schema; see step 4)")

    cache_file = pathlib.Path.home() / ".sqlalchemy_cache" / CACHE_NAME
    print(f"\ncache file : {cache_file}")
    if cache_file.exists():
        mtime = datetime.datetime.fromtimestamp(cache_file.stat().st_mtime)
        print(f"  written {mtime}. Startup reuses it; a schema change invalidates it.")
    else:
        print("  not written yet.")


# =============================================================================
# 3. session_scope
# =============================================================================


def demo_session_scope(db) -> None:
    """Run a query inside the transactional context manager."""
    banner("3. SESSION SCOPE")

    from sqlalchemy import text

    from dm_dbcore import DBTYPE_MYSQL, DBTYPE_POSTGRESQL, DBTYPE_SQLITE, session_scope

    version_query = {
        DBTYPE_POSTGRESQL: "SELECT version()",
        DBTYPE_MYSQL: "SELECT VERSION()",
        DBTYPE_SQLITE: "SELECT sqlite_version()",
    }[db.database_type]

    # session_scope commits on exit, rolls back if the block raises, and always
    # closes. Project connection modules wrap this into a no-argument
    # session_scope() so callers never handle the db object.
    with session_scope(db) as session:
        print(f"server : {session.execute(text(version_query)).scalar()}")

    print("Session committed and closed on exit from the with-block.")


# =============================================================================
# 4. Model classes -- reflection, not declaration
# =============================================================================


def demo_model_class(db, schema, table_name) -> int:
    """Build a model class by reflecting a real table. Returns an exit status."""
    banner("4. MODEL CLASSES")

    import warnings

    from sqlalchemy import Table, func, inspect, select
    from sqlalchemy.orm import DeclarativeBase, configure_mappers

    from dm_dbcore import session_scope

    # Reflection warns about column types it cannot map to a specialised Python
    # type. Harmless: the column is still reflected.
    warnings.filterwarnings(action="ignore", message="Skipped unsupported reflection")

    available = sorted(inspect(db.engine).get_table_names(schema=schema))
    if not available:
        print(f"No tables in schema {schema or 'default'} -- nothing to reflect.")
        print("Does the schema match the database, and can this user see it?")
        return 1

    if table_name is None:
        table_name = available[0]
        print(f"No --table given; using the first table found: {table_name}")
    elif table_name not in available:
        print(f"Table {table_name!r} is not in schema {schema or 'default'}.")
        print(f"Available: {', '.join(available)}")
        return 1

    class Base(DeclarativeBase):
        """Declarative base for this demo's model classes."""

    class Reflected(Base):
        """The table named on the command line, mapped by reflection."""

        __table__ = Table(table_name, Base.metadata, schema=schema, autoload_with=db.engine)

    # Validate every mapping now rather than at the first query.
    configure_mappers()

    print(f"\nclass Reflected(Base):  ->  {schema or 'default'}.{table_name}")
    print("Its columns were never typed out; the database supplied them:\n")
    for column in Reflected.__table__.columns:
        flags = []
        if column.primary_key:
            flags.append("primary key")
        if column.foreign_keys:
            flags.append("-> " + ", ".join(str(fk.target_fullname) for fk in column.foreign_keys))
        suffix = f"  ({'; '.join(flags)})" if flags else ""
        print(f"  {column.name:24s} {str(column.type):20s}{suffix}")

    with session_scope(db) as session:
        count = session.execute(select(func.count()).select_from(Reflected.__table__)).scalar()
        print(f"\nrows : {count}")
        first = session.scalars(select(Reflected)).first()
        if first is not None:
            print(f"first row maps to : {first!r}")

    print(
        "\nWhat reflection does NOT supply is relationship() -- 'student.city' vs\n"
        "'city.students' is a Python decision, not a database one. Write those by\n"
        "hand at the bottom of the model file; see templates/TEMPLATE_ModelClasses.py."
    )
    return 0


# =============================================================================
# Command line
# =============================================================================


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Demonstrate dm-dbcore against a live database.")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.environ.get("DM_DBCORE_TEST_URL"),
        help="SQLAlchemy URL, e.g. postgresql+psycopg://user@host/db (default: $DM_DBCORE_TEST_URL)",
    )
    parser.add_argument(
        "--schema",
        default=os.environ.get("DM_DBCORE_TEST_SCHEMA"),
        help="schema holding the tables; omit for SQLite/MySQL (default: $DM_DBCORE_TEST_SCHEMA)",
    )
    parser.add_argument("--table", help="table to reflect in step 4 (default: the first one found)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Run every step in order. Returns a process exit status."""
    args = parse_args(argv)

    if not args.url:
        print(
            "No database given. Pass a URL or set $DM_DBCORE_TEST_URL.\nTry --help.",
            file=sys.stderr,
        )
        return 2

    db = demo_connection(args.url)
    demo_metadata_cache(db)
    demo_session_scope(db)
    return demo_model_class(db, args.schema, args.table)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
