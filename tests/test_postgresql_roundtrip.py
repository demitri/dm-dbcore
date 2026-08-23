"""Round-trip tests against a live PostgreSQL server.

Skipped unless ``DM_DBCORE_TEST_PG_URL`` names a reachable server. CI supplies
one from a service container; see .github/workflows/ci.yml. They are skipped
rather than stubbed on purpose -- an adapter that has never sent a value to
PostgreSQL and read it back has not been tested against PostgreSQL, and a
mocked driver would assert only that the mock behaves like the mock.

What these cover that the offline tests cannot:

  * ``DatabaseConnection`` installs the adapters into the dialect's
    ``ischema_names`` as soon as it sees a PostgreSQL URL, so reflection --
    not a declaration -- gives a column the right Python type.
  * The psycopg dumpers registered at import time are the ones psycopg
    actually reaches for when a value is bound. That registration was broken
    once already and nothing reported it until an INSERT failed.
  * PostgreSQL accepts the literal text these adapters emit.

Every table is created in the ``public`` schema and named explicitly.
dm-dbcore clears the ``search_path`` on every connection, so an unqualified
name resolves to nothing.
"""

import pytest
from sqlalchemy import MetaData, Table, select, text

from dm_dbcore import DatabaseConnection
from dm_dbcore.adapters.postgresql.pggeometry import PGCircle, PGPoint, PGPolygon

np = pytest.importorskip("numpy")

pytestmark = pytest.mark.postgresql


@pytest.fixture
def pg_db(reset_singleton, postgresql_url):
    """A DatabaseConnection against the live server named by the env var."""
    return DatabaseConnection(database_connection_string=postgresql_url)


@pytest.fixture
def pg_table(pg_db):
    """Create a table from raw DDL, reflect it, and drop it afterwards.

    Reflection is the point: the column types come from the database, so this
    exercises the ischema_names registration rather than a declaration.
    """
    created = []

    def _create(name, columns_ddl):
        with pg_db.engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS public.{name}"))
            connection.execute(text(f"CREATE TABLE public.{name} ({columns_ddl})"))
        created.append(name)
        return Table(name, MetaData(), schema="public", autoload_with=pg_db.engine)

    yield _create

    with pg_db.engine.begin() as connection:
        for name in created:
            connection.execute(text(f"DROP TABLE IF EXISTS public.{name}"))


def _round_trip(engine, table, value):
    """Insert one value into the table's `value` column and read it back."""
    with engine.begin() as connection:
        connection.execute(table.insert().values(value=value))
    with engine.connect() as connection:
        return connection.execute(select(table.c.value)).scalar()


# --------------------------------------------------------------------------
# Adapter installation
# --------------------------------------------------------------------------

def test_connecting_installs_the_adapters_into_the_dialect(pg_db):
    """Nothing to register by hand: seeing a PostgreSQL URL is enough."""
    from sqlalchemy.dialects.postgresql import base as pg
    from dm_dbcore.adapters.postgresql.pgcitext import PGCIText
    from dm_dbcore.adapters.postgresql.pgxml import PGXML

    assert pg.ischema_names["point"] is PGPoint
    assert pg.ischema_names["polygon"] is PGPolygon
    assert pg.ischema_names["circle"] is PGCircle
    assert pg.ischema_names["citext"] is PGCIText
    assert pg.ischema_names["xml"] is PGXML


def test_reflection_gives_geometric_columns_their_adapter_types(pg_table):
    table = pg_table("dm_dbcore_types", "pt POINT, circ CIRCLE, poly POLYGON")
    assert isinstance(table.c.pt.type, PGPoint)
    assert isinstance(table.c.circ.type, PGCircle)
    assert isinstance(table.c.poly.type, PGPolygon)


# --------------------------------------------------------------------------
# Round trips
# --------------------------------------------------------------------------

def test_point_round_trips(pg_db, pg_table):
    table = pg_table("dm_dbcore_point", "value POINT")
    result = _round_trip(pg_db.engine, table, PGPoint((1.5, -2.25)))

    assert isinstance(result, PGPoint)
    assert (result.x, result.y) == (1.5, -2.25)


def test_a_point_read_back_can_be_written_again(pg_db, pg_table):
    """The documented promise: a value from the database goes straight back in."""
    table = pg_table("dm_dbcore_point_again", "value POINT")
    first = _round_trip(pg_db.engine, table, PGPoint((3.0, 4.0)))

    with pg_db.engine.begin() as connection:
        connection.execute(table.insert().values(value=first))
    with pg_db.engine.connect() as connection:
        values = connection.execute(select(table.c.value)).scalars().all()

    assert len(values) == 2
    assert values[0] == values[1]


def test_circle_round_trips(pg_db, pg_table):
    table = pg_table("dm_dbcore_circle", "value CIRCLE")
    result = _round_trip(pg_db.engine, table, PGCircle((3.0, 4.0), 5.0))

    assert isinstance(result, PGCircle)
    assert (result.x, result.y, result.radius) == (3.0, 4.0, 5.0)


def test_polygon_round_trips(pg_db, pg_table):
    table = pg_table("dm_dbcore_polygon", "value POLYGON")
    points = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0]])
    result = _round_trip(pg_db.engine, table, PGPolygon(points))

    assert isinstance(result, PGPolygon)
    assert np.allclose(result.points, points)


def test_null_geometry_stays_null(pg_db, pg_table):
    table = pg_table("dm_dbcore_null_geom", "value POINT")
    assert _round_trip(pg_db.engine, table, None) is None


def test_numpy_scalars_can_be_bound(pg_db, pg_table):
    """psycopg cannot adapt NumPy scalars without the registered dumpers."""
    table = pg_table("dm_dbcore_numpy_scalar", "value DOUBLE PRECISION")
    assert _round_trip(pg_db.engine, table, np.float64(1.5)) == 1.5


def test_numpy_arrays_can_be_bound(pg_db, pg_table):
    table = pg_table("dm_dbcore_numpy_array", "value DOUBLE PRECISION[]")
    result = _round_trip(pg_db.engine, table, np.array([1.0, 2.5, 3.0]))
    assert list(result) == [1.0, 2.5, 3.0]


def test_xml_round_trips(pg_db, pg_table):
    """PGXML is a pass-through: PostgreSQL stores and returns the document text.

    The INSERT casts explicitly because an XML column will not take a bare text
    parameter; the read side is what PGXML is responsible for.
    """
    table = pg_table("dm_dbcore_xml", "value XML")
    document = "<root><child>text</child></root>"
    with pg_db.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO public.dm_dbcore_xml (value) VALUES (CAST(:doc AS xml))"),
            {"doc": document},
        )
    with pg_db.engine.connect() as connection:
        assert connection.execute(select(table.c.value)).scalar() == document


def test_citext_compares_case_insensitively(pg_db, pg_table):
    """citext is a contrib extension, so ask whether it is available first.

    Deliberately no try/except around CREATE EXTENSION. Wrapping it would turn
    every failure into the same skip -- including a dropped connection or a
    privilege problem, which are real failures wearing a skip's clothes. A
    plain SELECT against pg_available_extensions answers the only question that
    justifies skipping; anything else that goes wrong here should fail the test.
    """
    with pg_db.engine.connect() as connection:
        available = connection.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'citext'")
        ).scalar()
    if not available:
        pytest.skip("the citext extension is not installed on this PostgreSQL server")

    with pg_db.engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))

    table = pg_table("dm_dbcore_citext", "value CITEXT")
    with pg_db.engine.begin() as connection:
        connection.execute(table.insert().values(value="MixedCase"))
    with pg_db.engine.connect() as connection:
        found = connection.execute(
            select(table.c.value).where(table.c.value == "mixedcase")
        ).scalar()

    assert found == "MixedCase"


# --------------------------------------------------------------------------
# Metadata cache staleness -- PostgreSQL is one of the two backends that has it
# --------------------------------------------------------------------------

def test_schema_hash_changes_when_the_schema_does(pg_db, pg_table):
    """The hash must notice DDL. It once hashed an empty set and never changed.

    The cause was `WHERE table_schema = current_schema()`, and dm-dbcore clears
    the search_path, so current_schema() was NULL and the query matched no rows
    -- an identical constant hash for every database and every schema.
    """
    from dm_dbcore import MetadataCache

    cache = MetadataCache(dbc=pg_db, filename="unused.pkl")
    before = cache._compute_postgresql_schema_hash()

    pg_table("dm_dbcore_hash_probe", "a INTEGER, b TEXT")
    after = cache._compute_postgresql_schema_hash()

    assert before != after, "adding a table must change the schema hash"


def test_schema_hash_is_stable_without_ddl(pg_db):
    from dm_dbcore import MetadataCache

    cache = MetadataCache(dbc=pg_db, filename="unused.pkl")
    assert cache._compute_postgresql_schema_hash() == cache._compute_postgresql_schema_hash()


def test_cache_write_creates_a_hash_file(pg_db, tmp_path):
    """PostgreSQL writes the companion .hash file; without it the cache is
    considered stale forever and caching silently never happens."""
    from dm_dbcore import MetadataCache

    cache = MetadataCache(dbc=pg_db, filename="app.pkl", path=str(tmp_path))
    cache.write(pg_db.metadata)

    assert (tmp_path / "app.pkl").is_file()
    assert (tmp_path / "app.hash").is_file()
    assert cache.cacheIsStale() is False
