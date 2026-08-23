#!/usr/bin/env python
'''
PostgreSQL geometric types (POINT, CIRCLE, POLYGON) for SQLAlchemy.

SQLAlchemy has no native support for these, so each is both a SQLAlchemy
column type and the Python value read out of that column:

    PGPoint((1.5, 2.5))         .x  .y
    PGCircle((3.0, 4.0), 5.0)   .x  .y  .radius
    PGPolygon(ndarray)          .points   -- shape (n, 2), requires NumPy

Nothing needs registering by hand. ``DatabaseConnection`` installs these into
``sqlalchemy.dialects.postgresql.base.ischema_names`` as soon as it sees a
PostgreSQL URL, so a reflected POINT column comes back as a PGPoint with
nothing declared in Python. To override that -- for instance to get `cornish`
objects from ``ast_pg_geometry`` instead -- reassign ``ischema_names`` BEFORE
your model classes are imported, since reflection reads it at import time:

    from sqlalchemy.dialects.postgresql import base as pg
    from dm_dbcore.adapters import PGPoint, PGPolygon
    pg.ischema_names['point'] = PGPoint
    pg.ischema_names['polygon'] = PGPolygon

Values round-trip: one read from the database can be assigned straight back to
a geometric column, and new ones built in Python can be inserted directly. The
write direction goes through the psycopg dumpers registered at the bottom of
this file, which is a module import side effect -- if this module is never
imported, binding one of these values raises "cannot adapt type".

NumPy and psycopg are both optional. Their absence is handled; a wrong name in
this file is not, and fails loudly.

For illustrative purposes in the comments below, assume a column defined as:
CREATE TABLE some_table (
	pt POINT,
	pg POLYGON
);
'''

__author__ = "Demitri Muna"

import ast  # Abstract Syntax Trees / https://docs.python.org/3.7/library/ast.html
from typing import Iterable

import sqlalchemy.types as types

# Optional dependencies - fail gracefully if not available
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
	# Deliberately NOT wrapped in try/except. If psycopg is installed but these
	# names are wrong, that is a bug in THIS file, not a missing dependency, and
	# it must fail loudly. Catching it here previously set _PSYCOPG_AVAILABLE to
	# False and silently disabled every dumper in this module -- the adapters
	# looked present but never registered, and nothing reported it.
	from psycopg.adapt import Dumper
	from psycopg import pq
	_PSYCOPG_AVAILABLE = True

class PGPoint(types.UserDefinedType):
	'''
	Class to represent the PostgreSQL "POINT" datatype.

	https://www.postgresql.org/docs/current/datatype-geometric.html#id-1.5.7.16.5

	Reading a POINT column returns a PGPoint object; its coordinates are
	available as the `.x` and `.y` attributes. Assigning a PGPoint to a POINT
	column writes it back, via the psycopg dumper registered at the bottom of
	this file, so a value read from the database can be written straight back
	without conversion.
	'''
	# The instances SQLAlchemy uses as *column types* are always constructed
	# with no arguments, so the type carries no state that could vary a cache
	# key. Without this, SQLAlchemy emits a performance warning per query.
	cache_ok = True

	def __init__(self, point:Iterable=None):

		if point is None:
			# SQLAlchemy constructs the column type with no arguments.
			self.x = None
			self.y = None
			return

		try:
			x, y = point[0], point[1]
		except (IndexError, KeyError, TypeError):
			raise ValueError(f"The point value (x, y) should be provided as a two element iterable, e.g. list, tuple, array, etc.; received '{point!r}'.")

		try:
			self.x = float(x)
			self.y = float(y)
		except (TypeError, ValueError):
			raise ValueError(f"Both elements provided must be numeric, received '{type(x).__name__}' and '{type(y).__name__}'.")

	def get_col_spec(self, **kw):
		return "POINT"

	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that comes from the
		database to a Python object.
		'''
		def process(value):
			if value is None:
				return None
			# The value from the database is a string of the form '(1.5,2.5)'.
			return PGPoint(ast.literal_eval(value))
		return process

	@property
	def sql_string(self):
		'''
		The PostgreSQL string representation of this point value.
		'''
		return f"POINT({self.x},{self.y})"

	def __repr__(self):
		return f"PGPoint(({self.x}, {self.y}))"

	def __eq__(self, other):
		if not isinstance(other, PGPoint):
			return NotImplemented
		return (self.x, self.y) == (other.x, other.y)

	def __hash__(self):
		return hash((self.x, self.y))


class PGCircle(types.UserDefinedType):
	'''
	Class to represent the PostgreSQL "CIRCLE" datatype (flat geometry).

	https://www.postgresql.org/docs/current/datatype-geometric.html#DATATYPE-CIRCLE

	A circle is a centre point and a radius. Reading a CIRCLE column returns a
	PGCircle object exposing `.x`, `.y`, and `.radius`; assigning a PGCircle to
	a CIRCLE column writes it back via the registered psycopg dumper.
	'''
	cache_ok = True

	def __init__(self, center:Iterable=None, radius=None):

		if center is None and radius is None:
			# SQLAlchemy constructs the column type with no arguments.
			self.x = None
			self.y = None
			self.radius = None
			return

		if center is None or radius is None:
			raise ValueError("A circle requires both a centre (x, y) and a radius.")

		try:
			x, y = center[0], center[1]
		except (IndexError, KeyError, TypeError):
			raise ValueError(f"The centre should be provided as a two element iterable, e.g. list, tuple, array, etc.; received '{center!r}'.")

		try:
			self.x = float(x)
			self.y = float(y)
			self.radius = float(radius)
		except (TypeError, ValueError):
			raise ValueError(f"The centre coordinates and radius must all be numeric; received '{center!r}' and '{radius!r}'.")

	def get_col_spec(self, **kw):
		return "CIRCLE"

	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that comes from the
		database to a Python object.
		'''
		def process(value):
			if value is None:
				return None
			# PostgreSQL renders a circle as '<(3,4),5>'. That is not valid
			# Python, so strip the angle brackets first, leaving '(3,4),5'
			# which evaluates to ((3, 4), 5).
			center, radius = ast.literal_eval(value.strip("<>"))
			return PGCircle(center, radius)
		return process

	@property
	def sql_string(self):
		'''
		The PostgreSQL string representation of this circle value.
		'''
		return f"<({self.x},{self.y}),{self.radius}>"

	def __repr__(self):
		return f"PGCircle(({self.x}, {self.y}), {self.radius})"

	def __eq__(self, other):
		if not isinstance(other, PGCircle):
			return NotImplemented
		return (self.x, self.y, self.radius) == (other.x, other.y, other.radius)

	def __hash__(self):
		return hash((self.x, self.y, self.radius))

class PGPolygon(types.UserDefinedType):
	'''
	Class to represent PostgreSQL "POLYGON" datatype.

	Ref: https://www.postgresql.org/docs/current/datatype-geometric.html#DATATYPE-POLYGON

	Reading a POLYGON column returns a PGPolygon object whose `.points` are a
	NumPy `ndarray` of shape (n,2). Assigning a PGPolygon to a POLYGON column
	writes it back, via the psycopg dumper registered at the bottom of this
	file.

	Unlike PGPoint and PGCircle, this type requires NumPy
	(pip install dm-dbcore[numpy]).

	:param points: points of a polygon in a NumPy `ndarray`, shape (n,2)
	'''
	# See the note on PGPoint.cache_ok. Matches PGCIText and PGXML, which
	# already set this.
	cache_ok = True

	def __init__(self, points=None):
		if points is None:
			# SQLAlchemy constructs the column type with no arguments. This must
			# work without NumPy, so it is checked before the NumPy guard below:
			# merely reflecting a POLYGON column should not require NumPy.
			self.points = None
			return

		# Checked here, before any use of `np`. NumPy is an optional dependency,
		# so `np` may be None -- in which case `isinstance(points, np.ndarray)`
		# would raise a confusing "isinstance() arg 2 must be a type" TypeError
		# instead of naming the real problem.
		if not _NUMPY_AVAILABLE:
			raise RuntimeError(
				"PGPolygon requires NumPy to hold its points, but NumPy is not "
				"installed. Install it with: pip install dm-dbcore[numpy]"
			)

		if isinstance(points, np.ndarray):
			self.points = points
		elif isinstance(points, str):
			self.points = np.array(points)
		else:
			raise ValueError(f"The type {type(points)} is not handled to initialize a PGPolygon.")

	def get_col_spec(self, **kw):
		return "POLYGON"

	def bind_processor(self, dialect):
		'''
		Return a function that performs the conversion from the
		provided object to a form that PostgreSQL can understand.

		To insert a value into a 'polygon' field:
			INSERT INTO some_table (pg) VALUES ('((1,2),(3,4),(4,5))');

		The value produced is DATA, not SQL: it carries no quotes and no
		'::POLYGON' cast. A bound parameter is sent to the server as a value,
		so any SQL punctuation in it would be taken literally.
		'''
		def process(value):
			''' Return a string. '''
			if value is None:
				return None

			# `value` may be a PGPolygon -- this class doubles as both the
			# SQLAlchemy type and the Python value -- or a raw ndarray or
			# sequence of (x, y) pairs. It must NOT be str()'d: PGPolygon is a
			# SQLAlchemy type, so str() returns the compiled type name
			# ('POLYGON'), not the points.
			points = value.points if isinstance(value, PGPolygon) else value
			if points is None:
				return None
			return _polygon_literal(points)
		return process

	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that
		comes from the database to a Python object.

		Requires NumPy: the points are held in an ndarray. NumPy is NOT pulled
		in by the [postgresql] extra, so reading a POLYGON column without it
		must say so rather than fail on `np` being None.
		'''
		if not _NUMPY_AVAILABLE:
			raise RuntimeError(
				"Reading a POLYGON column requires NumPy, which is not installed. "
				"Install it with: pip install dm-dbcore[numpy]"
			)

		def process(value):
			''' Return a Python object. '''
			if value is None:
				return None
			# Value from db will be a string of the form (without quotes): '((1,2),(3,4),(4,5))'.
			# Convert to a Python object.
			#
			p = PGPolygon()
			p.points = np.array(ast.literal_eval(value))
			return p
		return process

	def __len__(self):
		return len(self.points)

	@property
	def sql_string(self):
		'''
		The PostgreSQL string representation of this polygon value.
		'''
		return "'{}'::POLYGON".format(self.points.tolist()).replace("[","(").replace("]",")")

'''
The code below is needed to support the creation of the user types directly in user code, e.g.

p = PGPolygon(points)

Now, "p" can be passed directly to psycopg as a PostgreSQL POLYGON value.
'''
def _polygon_literal(points) -> str:
	"""Return the PostgreSQL text literal for a polygon."""
	if _NUMPY_AVAILABLE and isinstance(points, np.ndarray):
		points_iter = points.tolist()
	else:
		points_iter = points

	return "(" + ",".join(f"({x},{y})" for x, y in points_iter) + ")"


if _PSYCOPG_AVAILABLE:
	class _PGPointDumper(Dumper):
		format = pq.Format.TEXT

		def dump(self, obj):
			return f"({obj.x},{obj.y})".encode()

	class _PGPolygonDumper(Dumper):
		format = pq.Format.TEXT

		def dump(self, obj):
			return _polygon_literal(obj.points).encode()

	class _PGCircleDumper(Dumper):
		format = pq.Format.TEXT

		def dump(self, obj):
			return f"<({obj.x},{obj.y}),{obj.radius}>".encode()

	# Global registration. Note this is psycopg.adapters.register_dumper --
	# there is no psycopg.adapt.register_dumper in psycopg v3.
	psycopg.adapters.register_dumper(PGPoint, _PGPointDumper)
	psycopg.adapters.register_dumper(PGPolygon, _PGPolygonDumper)
	psycopg.adapters.register_dumper(PGCircle, _PGCircleDumper)
