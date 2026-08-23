"""Tests for the PostgreSQL geometric type adapters (no database required).

These types do two jobs, and both are pure string handling:

  * READ  -- ``result_processor()`` turns the text PostgreSQL sends
             (``'(1.5,2.5)'``, ``'<(3,4),5>'``, ``'((1,2),(3,4))'``) into a
             Python object.
  * WRITE -- the psycopg dumpers and ``bind_processor()`` turn that object back
             into the text PostgreSQL expects.

Both directions are exercised here against literals in exactly the form the
server uses, so no connection is needed. What is NOT proven without a server is
that PostgreSQL accepts what we emit; ``tests/test_postgresql_roundtrip.py``
covers that when one is available.

Note: ``str()`` on these classes returns the compiled SQL type name (``POINT``)
because they are SQLAlchemy ``UserDefinedType`` subclasses as well as values.
Tests therefore assert on attributes and ``repr()``, never ``str()``.
"""

import pytest

from dm_dbcore.adapters.postgresql.pggeometry import (
    _NUMPY_AVAILABLE,
    _PSYCOPG_AVAILABLE,
    _polygon_literal,
    PGCircle,
    PGPoint,
    PGPolygon,
)
from dm_dbcore.adapters.postgresql.pgcitext import PGCIText
from dm_dbcore.adapters.postgresql.pgxml import PGXML

np = pytest.importorskip("numpy") if _NUMPY_AVAILABLE else None

# PGPolygon holds its points in an ndarray, so the polygon tests that build or
# read one genuinely need NumPy -- which the [postgresql] extra does not pull
# in. Without these markers `np` is None and those tests died on
# "'NoneType' object has no attribute 'array'", which says nothing about what
# is actually missing. Everything else in this file -- points, circles, citext,
# xml, and the polygon paths that do not touch an array -- runs either way.
requires_numpy = pytest.mark.skipif(
    not _NUMPY_AVAILABLE, reason="numpy not installed (pip install dm-dbcore[numpy])"
)

# The mirror image: these pin what happens when NumPy is *absent*. The library
# is written to raise a RuntimeError naming the missing package rather than
# fail obscurely, and that promise was untested until CI grew a job with no
# optional dependencies installed.
without_numpy = pytest.mark.skipif(
    _NUMPY_AVAILABLE, reason="numpy is installed; these pin the behaviour when it is not"
)


# --------------------------------------------------------------------------
# PGPoint
# --------------------------------------------------------------------------

def test_point_no_args_is_a_bare_column_type():
    """SQLAlchemy builds the column type with no arguments; that must work."""
    point = PGPoint()
    assert point.x is None
    assert point.y is None
    assert point.get_col_spec() == "POINT"


def test_point_from_pair():
    point = PGPoint((1.5, 2.5))
    assert (point.x, point.y) == (1.5, 2.5)
    assert repr(point) == "PGPoint((1.5, 2.5))"
    assert point.sql_string == "POINT(1.5,2.5)"


def test_point_coerces_integers_to_float():
    point = PGPoint([1, 2])
    assert (point.x, point.y) == (1.0, 2.0)
    assert isinstance(point.x, float)


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param((1,), id="too-short"),
        pytest.param(5, id="not-iterable"),
        pytest.param({"a": 1}, id="dict-without-0-1-keys"),
        pytest.param(("a", "b"), id="non-numeric"),
        pytest.param((None, None), id="none-elements"),
    ],
)
def test_point_rejects_bad_input(bad):
    """Bad input raises ValueError -- it is never quietly turned into a null point."""
    with pytest.raises(ValueError):
        PGPoint(bad)


def test_point_equality_and_hash():
    assert PGPoint((1, 2)) == PGPoint((1.0, 2.0))
    assert PGPoint((1, 2)) != PGPoint((1, 3))
    assert hash(PGPoint((1, 2))) == hash(PGPoint((1.0, 2.0)))
    assert len({PGPoint((1, 2)), PGPoint((1.0, 2.0))}) == 1


def test_point_not_equal_to_other_types():
    """__eq__ returns NotImplemented for foreign types, so Python falls back."""
    assert PGPoint((1, 2)) != (1, 2)
    assert PGPoint((1, 2)) != "POINT(1,2)"


def test_point_reads_postgresql_text():
    process = PGPoint().result_processor(dialect=None, coltype=None)
    assert process("(1.5,2.5)") == PGPoint((1.5, 2.5))
    assert process(None) is None


def test_point_read_then_write_round_trips():
    """A value read from the database can go straight back into a column."""
    read = PGPoint().result_processor(None, None)("(1.5,-2.25)")
    assert read.sql_string == "POINT(1.5,-2.25)"


# --------------------------------------------------------------------------
# PGCircle
# --------------------------------------------------------------------------

def test_circle_no_args_is_a_bare_column_type():
    circle = PGCircle()
    assert (circle.x, circle.y, circle.radius) == (None, None, None)
    assert circle.get_col_spec() == "CIRCLE"


def test_circle_from_center_and_radius():
    circle = PGCircle((3, 4), 5)
    assert (circle.x, circle.y, circle.radius) == (3.0, 4.0, 5.0)
    assert repr(circle) == "PGCircle((3.0, 4.0), 5.0)"
    assert circle.sql_string == "<(3.0,4.0),5.0>"


@pytest.mark.parametrize(
    "center,radius",
    [
        pytest.param((1, 2), None, id="centre-without-radius"),
        pytest.param(None, 5, id="radius-without-centre"),
        pytest.param((1,), 5, id="short-centre"),
        pytest.param(("a", "b"), 5, id="non-numeric-centre"),
        pytest.param((1, 2), "big", id="non-numeric-radius"),
    ],
)
def test_circle_rejects_incomplete_or_bad_input(center, radius):
    with pytest.raises(ValueError):
        PGCircle(center, radius)


def test_circle_equality_and_hash():
    assert PGCircle((3, 4), 5) == PGCircle((3.0, 4.0), 5.0)
    assert PGCircle((3, 4), 5) != PGCircle((3, 4), 6)
    assert len({PGCircle((3, 4), 5), PGCircle((3.0, 4.0), 5.0)}) == 1


def test_circle_reads_postgresql_angle_bracket_text():
    """PostgreSQL renders a circle as '<(3,4),5>', which is not valid Python."""
    process = PGCircle().result_processor(None, None)
    assert process("<(3,4),5>") == PGCircle((3, 4), 5)
    assert process(None) is None


def test_circle_read_then_write_round_trips():
    read = PGCircle().result_processor(None, None)("<(3,4),5>")
    assert read.sql_string == "<(3.0,4.0),5.0>"


# --------------------------------------------------------------------------
# PGPolygon
# --------------------------------------------------------------------------

def test_polygon_no_args_needs_no_numpy():
    """Reflecting a POLYGON column must not require the optional NumPy extra."""
    polygon = PGPolygon()
    assert polygon.points is None
    assert polygon.get_col_spec() == "POLYGON"


@requires_numpy
def test_polygon_rejects_unhandled_types():
    with pytest.raises(ValueError):
        PGPolygon(points=[(1, 2), (3, 4)])


@requires_numpy
def test_polygon_reads_postgresql_text():
    polygon = PGPolygon().result_processor(None, None)("((1,2),(3,4),(4,5))")
    assert np.array_equal(polygon.points, np.array([[1, 2], [3, 4], [4, 5]]))
    assert len(polygon) == 3


@requires_numpy
def test_polygon_result_processor_passes_null_through():
    assert PGPolygon().result_processor(None, None)(None) is None


@requires_numpy
def test_polygon_binds_a_data_literal_not_sql():
    """The bound value is DATA: no quotes, no ::POLYGON cast.

    A bound parameter is sent to the server as a value, so SQL punctuation in
    it would be taken literally rather than parsed.
    """
    process = PGPolygon().bind_processor(dialect=None)
    literal = process(PGPolygon(np.array([[1, 2], [3, 4]])))
    assert literal == "((1,2),(3,4))"
    assert "'" not in literal
    assert "::" not in literal


@requires_numpy
def test_polygon_bind_accepts_a_raw_ndarray():
    """The value need not already be wrapped in a PGPolygon."""
    process = PGPolygon().bind_processor(None)
    assert process(np.array([[1, 2], [3, 4]])) == "((1,2),(3,4))"


def test_polygon_bind_passes_null_through():
    process = PGPolygon().bind_processor(None)
    assert process(None) is None
    assert process(PGPolygon()) is None


@requires_numpy
def test_polygon_read_then_write_round_trips():
    """The exact bug class the psycopg3 port fixed: read a value, write it back."""
    text_from_db = "((1,2),(3,4),(4,5))"
    value = PGPolygon().result_processor(None, None)(text_from_db)
    assert PGPolygon().bind_processor(None)(value) == text_from_db


def test_polygon_literal_accepts_a_list_of_pairs():
    """The list path needs no NumPy, so it is checked on its own."""
    assert _polygon_literal([(1, 2), (3, 4)]) == "((1,2),(3,4))"


@requires_numpy
def test_polygon_literal_accepts_an_ndarray():
    assert _polygon_literal(np.array([[1, 2], [3, 4]])) == "((1,2),(3,4))"


# --------------------------------------------------------------------------
# PGPolygon without NumPy
#
# NumPy is optional and the [postgresql] extra does not pull it in, so this is
# a configuration real users will have. The library promises to say what is
# missing rather than fail on an obscure TypeError or AttributeError; these
# tests hold it to that. They run only in the minimal-install CI job, which
# exists precisely so these paths are executed somewhere.
# --------------------------------------------------------------------------

@without_numpy
def test_constructing_a_polygon_with_points_without_numpy_names_numpy():
    with pytest.raises(RuntimeError, match="NumPy"):
        PGPolygon(points=[(1, 2), (3, 4)])


@without_numpy
def test_reading_a_polygon_column_without_numpy_names_numpy():
    with pytest.raises(RuntimeError, match="NumPy"):
        PGPolygon().result_processor(None, None)


@without_numpy
def test_a_polygon_column_can_still_be_reflected_without_numpy():
    """The guard must not spread: declaring the column type still works."""
    assert PGPolygon().get_col_spec() == "POLYGON"


@without_numpy
def test_polygon_literal_still_handles_lists_without_numpy():
    assert _polygon_literal([(1, 2), (3, 4)]) == "((1,2),(3,4))"


# --------------------------------------------------------------------------
# psycopg dumper registration
#
# These pin the 2026-07 fix: the dumpers exist but were never registered, so
# assigning a PGPoint to a column raised "cannot adapt type". Registration is a
# module import side effect, which is exactly the kind of thing that breaks
# silently.
# --------------------------------------------------------------------------

pytestmark_psycopg = pytest.mark.skipif(
    not _PSYCOPG_AVAILABLE, reason="psycopg not installed (pip install dm-dbcore[postgresql])"
)


@pytestmark_psycopg
@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param(PGPoint((1.5, 2.5)), b"(1.5,2.5)", id="point"),
        pytest.param(PGCircle((3, 4), 5), b"<(3.0,4.0),5.0>", id="circle"),
    ],
)
def test_dumper_is_registered_and_emits_postgresql_text(value, expected):
    import psycopg
    from psycopg.abc import PyFormat

    dumper = psycopg.adapters.get_dumper(type(value), PyFormat.TEXT)
    assert dumper(type(value), None).dump(value) == expected


@pytestmark_psycopg
@requires_numpy
def test_polygon_dumper_is_registered():
    import psycopg
    from psycopg.abc import PyFormat

    value = PGPolygon(np.array([[1, 2], [3, 4]]))
    dumper = psycopg.adapters.get_dumper(PGPolygon, PyFormat.TEXT)
    assert dumper(PGPolygon, None).dump(value) == b"((1,2),(3,4))"


# --------------------------------------------------------------------------
# PGCIText / PGXML
#
# These are pass-through types: PostgreSQL hands back plain text and takes
# plain text. The processors returning None is the contract -- it tells
# SQLAlchemy "no conversion needed" -- so it is asserted rather than assumed.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cls,col_spec",
    [pytest.param(PGCIText, "citext", id="citext"), pytest.param(PGXML, "xml", id="xml")],
)
def test_passthrough_types(cls, col_spec):
    instance = cls()
    assert instance.get_col_spec() == col_spec
    assert instance.bind_processor(dialect=None) is None
    assert instance.result_processor(dialect=None, coltype=None) is None


@pytest.mark.parametrize("cls", [PGPoint, PGCircle, PGPolygon, PGCIText, PGXML])
def test_types_are_cache_safe(cls):
    """cache_ok=True: these carry no state that could vary a query cache key.

    Without it SQLAlchemy emits a performance warning on every query using the
    type, which is noise loud enough that people turn warnings off.
    """
    assert cls.cache_ok is True
