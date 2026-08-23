#!/usr/bin/env python
"""
The smallest complete dm-dbcore program, runnable with no setup.

    python examples/quickstart.py

It uses SQLite in a temporary directory, so it needs no server, no credentials
and no configuration -- and it is run in CI, so what it prints is what the code
currently does rather than what a README once said it did.

The four steps are the four things any project built on dm-dbcore does:

    1. Connect            -- DatabaseConnection, the singleton every module shares.
    2. Reflect            -- the database defines the schema; nothing is declared.
    3. session_scope      -- a transactional block: commit on success, roll back
                             on any exception.
    4. Model classes      -- a class whose columns come from the database.

For PostgreSQL, change the URL to 'postgresql+psycopg://user@host/db' and pass
schema='your_schema' to Table(). Everything else is identical. Note that
dm-dbcore clears the PostgreSQL search_path on every connection, so the schema
must be named explicitly -- see STYLE_GUIDE.md section 3.
"""

import tempfile
from pathlib import Path

from sqlalchemy import Table, select, text
from sqlalchemy.orm import DeclarativeBase

from dm_dbcore import DatabaseConnection, session_scope


def main() -> int:
    with tempfile.TemporaryDirectory() as workspace:
        database_path = Path(workspace) / "quickstart.db"

        # ------------------------------------------------------------------
        # 0. A database with something in it. In a real project this exists
        #    already -- dm-dbcore reflects databases, it does not create them.
        # ------------------------------------------------------------------
        from sqlalchemy import create_engine

        setup_engine = create_engine(f"sqlite:///{database_path}")
        with setup_engine.begin() as connection:
            connection.execute(
                text(
                    # NOT NULL on the primary key is not decoration. SQLite
                    # reflects a bare `pk INTEGER PRIMARY KEY` as nullable,
                    # and SQLAlchemy then refuses a multi-row INSERT: it wants
                    # a sentinel column that is either NOT NULL or has a
                    # default. Reflection surfaces what the database actually
                    # says, quirks included -- that is the point of it.
                    "CREATE TABLE person ("
                    "  pk INTEGER NOT NULL PRIMARY KEY,"
                    "  name TEXT NOT NULL,"
                    "  email TEXT"
                    ")"
                )
            )
        setup_engine.dispose()

        # ------------------------------------------------------------------
        # 1. Connect. The first call needs the URL; every later call anywhere
        #    in the program is DatabaseConnection() with no arguments.
        # ------------------------------------------------------------------
        db = DatabaseConnection(database_connection_string=f"sqlite:///{database_path}")
        print(f"1. connected      : database_type={db.database_type!r}")
        print(f"                    DatabaseConnection() is db -> {DatabaseConnection() is db}")

        # ------------------------------------------------------------------
        # 2. Reflect. The connection reflected the database on construction.
        # ------------------------------------------------------------------
        print(f"2. reflected      : tables={sorted(db.metadata.tables)}")

        # ------------------------------------------------------------------
        # 3. Model classes. Columns are NEVER declared -- autoload_with reads
        #    them from the live database, so the two cannot drift apart.
        #    schema=None here because SQLite has no schemas; PostgreSQL needs
        #    a real schema name.
        # ------------------------------------------------------------------
        class Base(DeclarativeBase):
            pass

        class Person(Base):
            """Someone with an account."""

            __table__ = Table(
                "person", Base.metadata, schema=None, autoload_with=db.engine
            )

        print(f"3. model class    : Person columns={[c.name for c in Person.__table__.columns]}")

        # ------------------------------------------------------------------
        # 4. session_scope: commit on success...
        # ------------------------------------------------------------------
        with session_scope(db) as session:
            session.add(Person(name="Ada Lovelace", email="ada@example.org"))
            session.add(Person(name="Alan Turing", email="alan@example.org"))

        with session_scope(db) as session:
            people = session.scalars(select(Person).order_by(Person.name)).all()
            print(f"4. committed      : {[p.name for p in people]}")

        # ------------------------------------------------------------------
        #    ...and roll back on any exception, re-raising it. The write below
        #    is discarded; the exception is NOT swallowed.
        # ------------------------------------------------------------------
        try:
            with session_scope(db) as session:
                session.add(Person(name="Never Committed"))
                raise RuntimeError("something went wrong mid-transaction")
        except RuntimeError as exc:
            print(f"5. rolled back    : {exc}")

        with session_scope(db) as session:
            names = session.scalars(select(Person.name).order_by(Person.name)).all()
            print(f"                    still in the database: {list(names)}")

        assert "Never Committed" not in names, "rollback did not roll back"

        db.engine.dispose()

    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
