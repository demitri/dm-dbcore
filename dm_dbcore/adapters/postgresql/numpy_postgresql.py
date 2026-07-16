#!/usr/bin/python

"""
NumPy adapters for PostgreSQL using psycopg v3.

Registers dumpers so NumPy scalar types and ndarrays can be passed directly
to psycopg without manual conversion.
"""

import math
from typing import Any

try:
	import numpy as np
	_NUMPY_AVAILABLE = True
except ImportError:
	_NUMPY_AVAILABLE = False
	np = None

try:
	import psycopg
except ImportError:
	# psycopg is an optional dependency (pip install dm-dbcore[postgresql]).
	# Its absence is legitimate; the dumpers below are simply not registered.
	_PSYCOPG_AVAILABLE = False
	psycopg = None
	Dumper = None
	pq = None
else:
	# Deliberately NOT wrapped in try/except -- see the same note in
	# pggeometry.py. A wrong name here is a bug, not a missing dependency, and
	# swallowing it silently disabled every NumPy dumper in this module.
	from psycopg.adapt import Dumper
	from psycopg import pq
	_PSYCOPG_AVAILABLE = True


def _format_pg_array(value: Any) -> str:
	"""Render a Python list/tuple into a PostgreSQL array literal."""
	if isinstance(value, (list, tuple)):
		return "{" + ",".join(_format_pg_array(item) for item in value) + "}"

	if value is None:
		return "NULL"

	if _NUMPY_AVAILABLE and isinstance(value, np.floating):
		if np.isnan(value):
			return "NaN"
		if np.isposinf(value):
			return "Infinity"
		if np.isneginf(value):
			return "-Infinity"

	if isinstance(value, float):
		if math.isnan(value):
			return "NaN"
		if math.isinf(value):
			return "Infinity" if value > 0 else "-Infinity"

	if isinstance(value, str):
		escaped = value.replace("\\", "\\\\").replace('"', '\\"')
		return f'"{escaped}"'

	return str(value)


if _PSYCOPG_AVAILABLE and _NUMPY_AVAILABLE:
	class _NumpyScalarDumper(Dumper):
		format = pq.Format.TEXT

		def dump(self, obj):
			if isinstance(obj, np.floating):
				if np.isnan(obj):
					return b"NaN"
				if np.isposinf(obj):
					return b"Infinity"
				if np.isneginf(obj):
					return b"-Infinity"
			return str(obj).encode()

	class _NumpyArrayDumper(Dumper):
		format = pq.Format.TEXT

		def dump(self, obj):
			return _format_pg_array(obj.tolist()).encode()

	_numpy_types = [
		"int8",
		"int16",
		"int32",
		"int64",
		"uint8",
		"uint16",
		"uint32",
		"uint64",
		"float16",
		"float32",
		"float64",
	]

	# Global registration. Note this is psycopg.adapters.register_dumper --
	# there is no psycopg.adapt.register_dumper in psycopg v3.
	for type_name in _numpy_types:
		numpy_type = getattr(np, type_name, None)
		if numpy_type is not None:
			psycopg.adapters.register_dumper(numpy_type, _NumpyScalarDumper)

	psycopg.adapters.register_dumper(np.integer, _NumpyScalarDumper)
	psycopg.adapters.register_dumper(np.floating, _NumpyScalarDumper)
	psycopg.adapters.register_dumper(np.ndarray, _NumpyArrayDumper)













