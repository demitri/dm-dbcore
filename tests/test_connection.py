"""End-to-end tests for DatabaseConnection, MetadataCache and session_scope.

SQLite ships with Python, so these are real: a real engine, a real connection,
real reflection, real transactions. Nothing here is stubbed -- when a test says
a row was committed, a row was committed and read back.

What SQLite cannot cover is called out where it applies: schema-hash staleness
detection is PostgreSQL- and MySQL-only, and the geometric adapters need a
PostgreSQL server (see tests/test_postgresql_roundtrip.py).
"""

import threading

import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.exc import IntegrityError

from dm_dbcore import (
    DatabaseConnection,
    DBTYPE_MYSQL,
    DBTYPE_POSTGRESQL,
    DBTYPE_SQLITE,
    MetadataCache,
    session_scope,
)


# --------------------------------------------------------------------------
# Connection string -> database type
#
# This is the guard the psycopg3 migration added: a bare `postgresql://` URL
# looks fine and silently resolves to the deprecated psycopg2 driver, so it is
# rejected rather than accepted. These call the real method; only the singleton
# construction is bypassed, because determining the type must not require a
# reachable server.
# --------------------------------------------------------------------------

def _detect(url):
    connection = object.__new__(DatabaseConnection)
    connection.database_connection_string = url
    return connection.determine_database_type()


@pytest.mark.parametrize(
    "url,expected",
    [
        pytest.param("postgresql+psycopg://u:p@h/db", DBTYPE_POSTGRESQL, id="psycopg3"),
        pytest.param("mysql+pymysql://u:p@h/db", DBTYPE_MYSQL, id="pymysql"),
        pytest.param("mysql://u:p@h/db", DBTYPE_MYSQL, id="bare-mysql-legacy"),
        pytest.param("sqlite:///path/to.db", DBTYPE_SQLITE, id="sqlite-file"),
        pytest.param("sqlite://", DBTYPE_SQLITE, id="sqlite-memory"),
    ],
)
def test_database_type_is_detected(url, expected):
    assert _detect(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("postgresql://u:p@h/db", id="bare-postgresql-resolves-to-psycopg2"),
        pytest.param("postgresql+psycopg2://u:p@h/db", id="explicit-psycopg2"),
    ],
)
def test_psycopg2_urls_are_rejected(url):
    """Rejected, not quietly accepted: psycopg2 is deprecated for this package."""
    with pytest.raises(ValueError) as excinfo:
        _detect(url)
    assert "psycopg" in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("oracle://u@h/db", id="unsupported-backend"),
        pytest.param("", id="empty"),
        pytest.param("not a url at all", id="garbage"),
    ],
)
def test_unrecognised_urls_raise_rather_than_defaulting(url):
    with pytest.raises(ValueError):
        _detect(url)


def test_rejection_message_names_the_accepted_forms():
    """The error has to be actionable -- it is the only thing the caller sees."""
    with pytest.raises(ValueError) as excinfo:
        _detect("postgresql://u@h/db")
    message = str(excinfo.value)
    for form in ("postgresql+psycopg://", "mysql+pymysql://", "sqlite://"):
        assert form in message


# --------------------------------------------------------------------------
# Singleton behaviour
# --------------------------------------------------------------------------

def test_first_call_requires_a_connection_string(reset_singleton):
    with pytest.raises(AssertionError):
        DatabaseConnection()


def test_later_calls_return_the_same_instance(sqlite_db):
    assert DatabaseConnection() is sqlite_db


def test_a_second_url_is_ignored_once_the_singleton_exists(sqlite_db, tmp_path):
    """Documented footgun: the FIRST caller's URL wins for the process lifetime.

    A later call passing a different URL does not open a second database and
    does not raise -- it silently returns the existing connection. Pinned here
    so a change in that behaviour is a deliberate one.
    """
    other = DatabaseConnection(f"sqlite:///{tmp_path / 'other.db'}")
    assert other is sqlite_db
    assert other.database_connection_string == sqlite_db.database_connection_string


# --------------------------------------------------------------------------
# A live connection
# --------------------------------------------------------------------------

def test_connection_exposes_engine_session_and_metadata(sqlite_db):
    assert sqlite_db.database_type == DBTYPE_SQLITE
    assert sqlite_db.engine is not None
    assert sqlite_db.Session is not None
    assert isinstance(sqlite_db.metadata, MetaData)


def test_search_path_callback_does_not_break_non_postgresql_connections(sqlite_db):
    """The pool `connect` listener issues a PostgreSQL-only SET search_path.

    It fires for every backend, so a regression there would break every SQLite
    and MySQL connection in the process. Opening a connection and running a
    query is the check.
    """
    with sqlite_db.engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1


def test_metadata_reflects_tables_that_exist(reset_singleton, tmp_path):
    """Reflection is the whole point: the database defines the schema."""
    url = f"sqlite:///{tmp_path / 'reflect.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE widget (id INTEGER PRIMARY KEY, name TEXT)"))
    engine.dispose()

    db = DatabaseConnection(database_connection_string=url)
    assert "widget" in db.metadata.tables
    assert {"id", "name"} <= set(db.metadata.tables["widget"].columns.keys())


def test_validate_connection_returns_true_for_a_reachable_database(sqlite_db):
    assert DatabaseConnection.validate_connection(sqlite_db.engine, DBTYPE_SQLITE) is True


def test_validate_connection_raises_runtime_error_when_unreachable():
    """Failures are re-raised as RuntimeError with the URL, not returned as False."""
    engine = create_engine("sqlite:////nonexistent-directory-xyzzy/db.sqlite")
    try:
        with pytest.raises(RuntimeError) as excinfo:
            DatabaseConnection.validate_connection(engine, DBTYPE_SQLITE)
        assert "nonexistent-directory-xyzzy" in str(excinfo.value)
    finally:
        engine.dispose()


def test_unreachable_database_fails_construction(reset_singleton):
    """Construction does not hand back a half-built object to fail later."""
    with pytest.raises(RuntimeError):
        DatabaseConnection(
            database_connection_string="sqlite:////nonexistent-directory-xyzzy/db.sqlite"
        )


# --------------------------------------------------------------------------
# session_scope
# --------------------------------------------------------------------------

@pytest.fixture
def widget_db(sqlite_db):
    with sqlite_db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE widget (id INTEGER PRIMARY KEY, name TEXT)"))
    return sqlite_db


def _widget_names(db):
    with db.engine.connect() as connection:
        return [row[0] for row in connection.execute(text("SELECT name FROM widget ORDER BY name"))]


def test_session_scope_commits_on_success(widget_db):
    with session_scope(widget_db) as session:
        session.execute(text("INSERT INTO widget (name) VALUES ('kept')"))

    assert _widget_names(widget_db) == ["kept"]


def test_session_scope_rolls_back_and_re_raises(widget_db):
    """The exception must propagate. A rollback that swallows it hides the bug."""
    with pytest.raises(RuntimeError, match="deliberate"):
        with session_scope(widget_db) as session:
            session.execute(text("INSERT INTO widget (name) VALUES ('discarded')"))
            raise RuntimeError("deliberate")

    assert _widget_names(widget_db) == []


def test_session_scope_rolls_back_on_a_database_error(widget_db):
    """A constraint violation rolls the whole block back, not just the bad statement."""
    with session_scope(widget_db) as session:
        session.execute(text("INSERT INTO widget (id, name) VALUES (1, 'first')"))

    # IntegrityError specifically, not Exception: a bare `raises(Exception)`
    # would pass just as happily if the test itself were broken and threw
    # something unrelated, certifying a rollback that never happened.
    with pytest.raises(IntegrityError):
        with session_scope(widget_db) as session:
            session.execute(text("INSERT INTO widget (name) VALUES ('second')"))
            session.execute(text("INSERT INTO widget (id, name) VALUES (1, 'duplicate')"))

    assert _widget_names(widget_db) == ["first"]


def test_session_scope_closes_the_session(widget_db):
    with session_scope(widget_db) as session:
        session.execute(text("SELECT 1"))
    assert not session.is_active or session.get_transaction() is None


# --------------------------------------------------------------------------
# MetadataCache
#
# The 2026-07 fix made this class strict: it used to wrap its whole write in a
# bare `except: pass`, so `cache_name` silently bought nothing. These pin both
# halves of the current contract -- what it writes, and that it raises.
# --------------------------------------------------------------------------

def test_cache_requires_a_filename(sqlite_db):
    with pytest.raises(Exception, match="filename"):
        MetadataCache(dbc=sqlite_db, filename=None)


def test_cache_path_joins_directory_and_filename(sqlite_db, tmp_path):
    cache = MetadataCache(dbc=sqlite_db, filename="app.pkl", path=str(tmp_path / "cachedir"))
    assert cache.cachePath == tmp_path / "cachedir" / "app.pkl"


def test_cache_write_creates_the_directory_and_the_pickle(sqlite_db, tmp_path):
    directory = tmp_path / "does" / "not" / "exist" / "yet"
    cache = MetadataCache(dbc=sqlite_db, filename="app.pkl", path=str(directory))
    cache.write(sqlite_db.metadata)
    assert (directory / "app.pkl").is_file()


def test_sqlite_gets_no_hash_file(sqlite_db, tmp_path):
    """SQLite has no staleness detection, so it writes no companion hash."""
    cache = MetadataCache(dbc=sqlite_db, filename="app.pkl", path=str(tmp_path))
    cache.write(sqlite_db.metadata)
    assert not (tmp_path / "app.hash").exists()


def test_sqlite_cache_is_always_stale(sqlite_db, tmp_path):
    """Documented: with no way to detect DDL changes, SQLite never trusts a cache."""
    cache = MetadataCache(dbc=sqlite_db, filename="app.pkl", path=str(tmp_path))
    cache.write(sqlite_db.metadata)
    assert cache.cacheIsStale() is True


def test_reading_a_stale_cache_deletes_it_and_yields_nothing(sqlite_db, tmp_path):
    cache = MetadataCache(dbc=sqlite_db, filename="app.pkl", path=str(tmp_path))
    cache.write(sqlite_db.metadata)
    assert cache.cachePath.exists()

    cache.read()
    assert cache.metadata is None
    assert not cache.cachePath.exists(), "a stale cache must be removed, not left to be re-read"


def test_reading_an_absent_cache_is_not_an_error(sqlite_db, tmp_path):
    cache = MetadataCache(dbc=sqlite_db, filename="absent.pkl", path=str(tmp_path))
    cache.read()
    assert cache.metadata is None


def test_write_failure_propagates(sqlite_db, tmp_path):
    """Caching is opt-in, so failing to cache is an error, not a silent no-op.

    Here the cache directory path is occupied by a regular file, so it cannot
    be created. The previous implementation swallowed this and every startup
    silently re-reflected the database.
    """
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    cache = MetadataCache(dbc=sqlite_db, filename="app.pkl", path=str(blocker / "cache"))

    with pytest.raises(OSError):
        cache.write(sqlite_db.metadata)


# --------------------------------------------------------------------------
# Failed construction must leave no singleton behind
#
# The instance used to be registered in `_singletons` before the connection was
# validated or the schema reflected, so any failure below that point installed
# a half-built object permanently. The caller saw the real error once; every
# later call got the wreck back and failed elsewhere with an AttributeError.
# --------------------------------------------------------------------------

def test_failed_construction_leaves_no_singleton(reset_singleton, tmp_path):
    bad_url = f"sqlite:///{tmp_path / 'no-such-directory' / 'test.db'}"

    with pytest.raises(RuntimeError):
        DatabaseConnection(database_connection_string=bad_url)

    assert DatabaseConnection not in DatabaseConnection._singletons, (
        "a construction that raised must not register a half-built instance"
    )


def test_a_good_connection_works_after_a_failed_one(reset_singleton, tmp_path, sqlite_url):
    """The retry that the poisoned singleton used to make impossible."""
    bad_url = f"sqlite:///{tmp_path / 'no-such-directory' / 'test.db'}"

    with pytest.raises(RuntimeError):
        DatabaseConnection(database_connection_string=bad_url)

    db = DatabaseConnection(database_connection_string=sqlite_url)

    assert db.database_connection_string == sqlite_url
    assert db.metadata is not None, "the retry must be fully built, not the failed instance"
    assert db.Session is not None

    # And it is genuinely usable, not merely populated.
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).fetchone()[0] == 1


def test_concurrent_first_callers_get_the_same_instance(reset_singleton, sqlite_url):
    """Two threads racing to build the first instance must share one object.

    Construction validates the connection and reflects the schema, both of
    which do I/O and release the GIL. An unsynchronized check/build/register
    let both threads see an empty registry and build a complete object each,
    so two callers held two different "singletons" -- two engines, two session
    registries -- and only the second was ever stored. Work done through the
    other one went to an object nothing else in the process could reach.
    """
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def build():
        try:
            barrier.wait(timeout=10)
            results.append(DatabaseConnection(database_connection_string=sqlite_url))
        except BaseException as exc:  # noqa: BLE001 -- recorded and re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=build) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "construction deadlocked"

    assert not errors, f"construction raised: {errors}"
    assert len(results) == 2
    assert results[0] is results[1], "the two threads built two different singletons"
    assert results[0] is DatabaseConnection._singletons[DatabaseConnection], (
        "the instance handed to callers is not the one that was registered"
    )
