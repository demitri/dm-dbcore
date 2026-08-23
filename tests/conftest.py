"""Shared fixtures for the dm-dbcore test suite.

The tests here are split by what they need to run:

  * Offline tests (the bulk) need nothing but Python. Adapter value handling,
    ``.my.cnf`` parsing, and PostgreSQL literal formatting are all pure Python
    -- the strings the adapters produce and consume are the contract, and they
    can be checked without a server.

  * SQLite tests exercise the real ``DatabaseConnection`` end to end: a real
    engine, a real connection, real reflection, real transactions. SQLite ships
    with Python, so these are still offline.

  * PostgreSQL tests (``tests/test_postgresql_roundtrip.py``) need a live
    server and are skipped unless ``DM_DBCORE_TEST_PG_URL`` names one. They are
    skipped, never faked: an adapter that is never asked to round-trip a value
    through PostgreSQL has not been tested against PostgreSQL.
"""

import os
import sys

import pytest

from dm_dbcore import DatabaseConnection


# tests/test_check_style.py exercises scripts/check_style.py, which inspects
# `match`-statement AST nodes (ast.MatchAs, ast.MatchStar, ast.MatchMapping).
# Those classes arrived in Python 3.10, but the package itself supports 3.8+,
# so on 3.8/3.9 that module cannot even be collected -- and the plain
# `python -m pytest` the README documents therefore failed outright for anyone
# developing on a supported interpreter. CI sidesteps this with an explicit
# --ignore; this makes the same decision for local runs.
#
# This is a deliberate, visible skip of a test whose *tool* needs a newer
# interpreter, not of a test that fails: the gate is a development tool and
# CLAUDE.md already records that 3.10+ is a limit on the tool, not the package.
# It runs for real on every interpreter that can load it, and CI's style-gate
# job runs it on 3.12 unconditionally.
collect_ignore = []
if sys.version_info < (3, 10):
    collect_ignore.append("test_check_style.py")


@pytest.fixture
def reset_singleton():
    """Clear the DatabaseConnection singleton around a test.

    ``DatabaseConnection`` caches one instance per class in
    ``_singletons``, keyed by the class itself, and the first caller's
    connection string wins for the life of the process. Without this, the
    first test to build a connection would silently decide the database for
    every test after it.
    """
    DatabaseConnection._singletons.clear()
    yield
    instance = DatabaseConnection._singletons.get(DatabaseConnection)
    engine = getattr(instance, "engine", None)
    if engine is not None:
        engine.dispose()
    DatabaseConnection._singletons.clear()


@pytest.fixture
def sqlite_url(tmp_path):
    """A file-backed SQLite URL in a per-test directory."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def sqlite_db(reset_singleton, sqlite_url):
    """A live DatabaseConnection against an empty on-disk SQLite database."""
    return DatabaseConnection(database_connection_string=sqlite_url)


@pytest.fixture(scope="session")
def postgresql_url():
    """URL of a live PostgreSQL server, or skip.

    Set ``DM_DBCORE_TEST_PG_URL`` to run the PostgreSQL round-trip tests. CI
    sets it from a service container; see .github/workflows/ci.yml.
    """
    url = os.environ.get("DM_DBCORE_TEST_PG_URL")
    if not url:
        pytest.skip(
            "no PostgreSQL server: set DM_DBCORE_TEST_PG_URL to a "
            "'postgresql+psycopg://...' URL to run these tests"
        )
    return url
