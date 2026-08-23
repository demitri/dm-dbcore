"""Tests for the NumPy -> PostgreSQL adapters (no database required).

``_format_pg_array`` renders a Python list into a PostgreSQL array literal, and
the registered psycopg dumpers turn NumPy scalars and ndarrays into the bytes
psycopg sends. Both are pure functions of their input, so both are checked here
against the literal forms PostgreSQL accepts.

The special values matter more than the ordinary ones: PostgreSQL spells them
``NaN``, ``Infinity``, ``-Infinity`` and ``NULL``, none of which are what
``str()`` produces for the Python or NumPy equivalents. Getting those wrong
fails at insert time, not at import time.
"""

import math

import pytest

np = pytest.importorskip("numpy")
psycopg = pytest.importorskip("psycopg")

from psycopg.abc import PyFormat  # noqa: E402  (after importorskip)

# Importing the module is what registers the dumpers.
from dm_dbcore.adapters.postgresql import numpy_postgresql  # noqa: E402
from dm_dbcore.adapters.postgresql.numpy_postgresql import _format_pg_array  # noqa: E402


# --------------------------------------------------------------------------
# Array literal formatting
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param([1, 2, 3], "{1,2,3}", id="flat-ints"),
        pytest.param([[1, 2], [3, 4]], "{{1,2},{3,4}}", id="nested"),
        pytest.param((1, 2), "{1,2}", id="tuple"),
        pytest.param([], "{}", id="empty"),
        pytest.param([1.5, -2.25], "{1.5,-2.25}", id="floats"),
        pytest.param([True, False], "{True,False}", id="bools"),
    ],
)
def test_format_pg_array(value, expected):
    assert _format_pg_array(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param(None, "NULL", id="none"),
        pytest.param(float("nan"), "NaN", id="python-nan"),
        pytest.param(float("inf"), "Infinity", id="python-inf"),
        pytest.param(float("-inf"), "-Infinity", id="python-negative-inf"),
        pytest.param(np.float64("nan"), "NaN", id="numpy-nan"),
        pytest.param(np.float32("inf"), "Infinity", id="numpy-inf"),
        pytest.param(np.float64("-inf"), "-Infinity", id="numpy-negative-inf"),
    ],
)
def test_format_pg_array_special_values(value, expected):
    """PostgreSQL's spellings, not Python's -- 'nan' and 'None' are rejected by the server."""
    assert _format_pg_array([value]) == "{" + expected + "}"


def test_format_pg_array_quotes_and_escapes_strings():
    """Embedded quotes and backslashes must survive the array literal."""
    assert _format_pg_array(['plain']) == '{"plain"}'
    assert _format_pg_array(['a"b']) == '{"a\\"b"}'
    assert _format_pg_array(['c\\d']) == '{"c\\\\d"}'


def test_format_pg_array_mixes_nulls_and_values():
    assert _format_pg_array([1, None, 3]) == "{1,NULL,3}"


# --------------------------------------------------------------------------
# Dumper registration
#
# Registration happens as an import side effect, which fails silently: nothing
# reports an adapter that was never installed until a query raises "cannot
# adapt type". These assert the registration is actually in place.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "numpy_type",
    ["int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
     "float16", "float32", "float64"],
)
def test_scalar_dumper_registered_for_each_numpy_type(numpy_type):
    dtype = getattr(np, numpy_type)
    dumper = psycopg.adapters.get_dumper(dtype, PyFormat.TEXT)
    assert dumper is numpy_postgresql._NumpyScalarDumper


@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param(np.int64(7), b"7", id="int"),
        pytest.param(np.float64(1.5), b"1.5", id="float"),
        pytest.param(np.float64("nan"), b"NaN", id="nan"),
        pytest.param(np.float32("inf"), b"Infinity", id="inf"),
        pytest.param(np.float64("-inf"), b"-Infinity", id="negative-inf"),
    ],
)
def test_scalar_dumper_output(value, expected):
    dumper = psycopg.adapters.get_dumper(type(value), PyFormat.TEXT)
    assert dumper(type(value), None).dump(value) == expected


def test_ndarray_dumper_registered_and_renders_array_literal():
    dumper = psycopg.adapters.get_dumper(np.ndarray, PyFormat.TEXT)
    assert dumper is numpy_postgresql._NumpyArrayDumper
    assert dumper(np.ndarray, None).dump(np.array([1, 2, 3])) == b"{1,2,3}"


def test_ndarray_dumper_handles_2d_and_special_values():
    dumper = psycopg.adapters.get_dumper(np.ndarray, PyFormat.TEXT)
    instance = dumper(np.ndarray, None)
    assert instance.dump(np.array([[1, 2], [3, 4]])) == b"{{1,2},{3,4}}"
    assert instance.dump(np.array([1.0, np.nan, np.inf])) == b"{1.0,NaN,Infinity}"


def test_numpy_sqlite_adapters_convert_scalars():
    """The SQLite adapters register converters on the stdlib sqlite3 module.

    Without them sqlite3 raises InterfaceError on a NumPy scalar. This inserts
    real NumPy values into a real (in-memory) SQLite database and reads back
    the Python types SQLite stored.
    """
    import sqlite3

    from dm_dbcore.adapters.sqlite import numpy_sqlite  # noqa: F401  (registers adapters)

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE t (i INTEGER, f REAL)")
        connection.execute(
            "INSERT INTO t (i, f) VALUES (?, ?)", (np.int32(42), np.float32(1.5))
        )
        row = connection.execute("SELECT i, f FROM t").fetchone()
    finally:
        connection.close()

    assert row[0] == 42
    assert isinstance(row[0], int)
    assert math.isclose(row[1], 1.5)
