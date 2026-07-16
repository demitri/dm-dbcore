#!/usr/bin/env python
"""
Connection diagnostic for dm-dbcore.

Answers one question: can this machine, as this user, reach that database and
see the tables it expects? If it prints a server version and a table list, the
environment is set up correctly and any failure after this is in your code, not
your credentials.

Two modes:

  URL mode     -- test a database directly, before any project code exists.
  MODULE mode  -- test a project's connection module (Layer 2 of the three-layer
                  pattern in STYLE_GUIDE.md section 1), which is what your
                  application will actually import.

Usage:

    # URL mode: pass the URL, or set DM_DBCORE_TEST_URL.
    python db_connection_test.py postgresql+psycopg://user@localhost:5432/mydb --schema core
    python db_connection_test.py sqlite:///local.sqlite

    # MODULE mode: name an importable module built from TEMPLATE_Connection.py.
    # It supplies its own URL and SCHEMA, so pass neither.
    python db_connection_test.py --module myproject.db.connections.LaptopDBConnection

Passwords belong in ~/.pgpass (PostgreSQL) or ~/.my.cnf (MySQL), not on the
command line -- omit the password from the URL and libpq supplies it.

Exit status is 0 when the connection works and the schema holds tables.
"""

import argparse
import os
import sys
from contextlib import contextmanager

# =============================================================================
# Connecting
# =============================================================================
#
# Both modes return the same three things -- the DatabaseConnection, the schema
# to inspect, and a no-argument context manager yielding a session -- so that
# report() below does not care which mode produced them.


def connect_from_url(url: str, schema):
    """Build a DatabaseConnection directly from a URL. Returns (db, schema, scope)."""
    from dm_dbcore import DatabaseConnection, session_scope

    # cache_name=None: a diagnostic must read the live database. A cached
    # reflection would report the schema as it was, which is the opposite of
    # what this script is for.
    db = DatabaseConnection(database_connection_string=url, cache_name=None)

    @contextmanager
    def scope():
        with session_scope(db) as session:
            yield session

    return db, schema, scope


def connect_from_module(module_name: str):
    """Import a project connection module and use what it exports. Returns (db, schema, scope)."""
    import importlib

    module = importlib.import_module(module_name)

    # The names TEMPLATE_Connection.py exports. A module missing them was not
    # built from the template (or predates it) -- say so plainly rather than
    # failing later with an AttributeError from somewhere less obvious.
    missing = [name for name in ("db", "SCHEMA", "session_scope") if not hasattr(module, name)]
    if missing:
        raise AttributeError(
            f"{module_name} does not export {', '.join(missing)}. "
            "Connection modules should be built from templates/TEMPLATE_Connection.py."
        )

    return module.db, module.SCHEMA, module.session_scope


# =============================================================================
# Reporting
# =============================================================================


def report(db, schema, scope) -> int:
    """Print what the connection reaches. Returns a process exit status."""
    from sqlalchemy import inspect, text

    from dm_dbcore import DBTYPE_MYSQL, DBTYPE_POSTGRESQL, DBTYPE_SQLITE

    print(f"database type : {db.database_type}")
    print(f"url           : {db.engine.url}")  # password is masked by SQLAlchemy
    print(f"schema        : {schema}")

    version_query = {
        DBTYPE_POSTGRESQL: "SELECT version()",
        DBTYPE_MYSQL: "SELECT VERSION()",
        DBTYPE_SQLITE: "SELECT sqlite_version()",
    }[db.database_type]

    with scope() as session:
        print(f"server        : {session.execute(text(version_query)).scalar()}")

    # Ask the server, not db.metadata. dm-dbcore reflects metadata at connect
    # time from the *default* schema, and on PostgreSQL it clears the
    # search_path first -- so db.metadata is legitimately empty for any project
    # whose tables live in a named schema. That is by design.
    tables = sorted(inspect(db.engine).get_table_names(schema=schema))
    print(f"tables in {schema or 'default'} : {len(tables)}")
    for name in tables:
        print(f"  - {name}")

    if not tables:
        print("  (none -- does the schema match the database, and can this user see it?)")
        return 1

    return 0


# =============================================================================
# Command line
# =============================================================================


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Test a dm-dbcore database connection.")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.environ.get("DM_DBCORE_TEST_URL"),
        help="SQLAlchemy URL, e.g. postgresql+psycopg://user@host/db (default: $DM_DBCORE_TEST_URL)",
    )
    parser.add_argument(
        "--schema",
        default=os.environ.get("DM_DBCORE_TEST_SCHEMA"),
        help="schema to inspect; omit for SQLite/MySQL (default: $DM_DBCORE_TEST_SCHEMA)",
    )
    parser.add_argument(
        "--module",
        help="import this connection module instead of using a URL (it supplies its own URL and SCHEMA)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Run the diagnostic. Returns a process exit status."""
    args = parse_args(argv)

    if args.module:
        if args.url or args.schema:
            print("--module supplies its own URL and schema; do not pass them too.", file=sys.stderr)
            return 2
        db, schema, scope = connect_from_module(args.module)
    elif args.url:
        db, schema, scope = connect_from_url(args.url, args.schema)
    else:
        print(
            "No database given. Pass a URL, set $DM_DBCORE_TEST_URL, or use --module.\n"
            "Try --help.",
            file=sys.stderr,
        )
        return 2

    return report(db, schema, scope)


if __name__ == "__main__":
    raise SystemExit(main())
