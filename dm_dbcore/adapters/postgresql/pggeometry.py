#!/usr/bin/env python

__author__ = "Demitri Muna"

'''
Classes to add support for PostrgeSQL geometric data types that SQLAlchemy doesn't natively support.

USAGE:

* PGPoint and PGPolygon are to be used to map columns in the database of those types.

-----------------------------------------

Example usage, e.g. at the top of a ModelClasses file:

from sqlalchemy.dialects.postgresql import base as pg
from dm_dbcore.adapters import PGPoint, PGPolygon
pg.ischema_names['point'] = PGPoint
pg.ischema_names['polygon'] = PGPolygon

This will assign the PGPoint/PGPolygon object types for all fields of those types.

For illustrative purposes in the comments below, assume a column defined as:
CREATE TABLE some_table (
	pt POINT,
	pg POLYGON
);
'''
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
	from psycopg.adapt import Dumper, register_dumper
	from psycopg import pq
	_PSYCOPG_AVAILABLE = True
except ImportError:
	_PSYCOPG_AVAILABLE = False
	register_dumper = None
	Dumper = None
	pq = None

class PGPoint(types.UserDefinedType):
	'''
	Class to represent the PostgreSQL "POINT" datatype.

	https://www.postgresql.org/docs/current/datatype-geometric.html#id-1.5.7.16.5

	Using this datatype definition, tuples of float values can be provided
	to point columns, and tuples of float values will be returned.
	'''
	def __init__(self, point:Iterable=None):

		if point is None:
			return

		try:
			self.x = point[0]
			self.y = point[1]
		except IndexError:
			raise ValueError(f"The point value (x, y) should be provided as two element interable, e.g. list, tuple, array, etc.")

		try:
			float(self.x)
			float(self.y)
		except ValueError:
			raise ValueError(f"Both elements provided must be numeric, received '{type(self.x)}' and '{type(self.x)}'.")

	def get_col_spec(self, **kw):
		return "POINT"


class PGCircle(types.UserDefinedType):
	'''
	Class to represent the PostgreSQL "CIRCLE" datatype (flat geometry).

	https://www.postgresql.org/docs/current/datatype-geometric.html#DATATYPE-CIRCLE
	'''
	def get_col_spec(self, **kw):
		return "CIRCLE"

	def bind_processor(self, dialect):
		'''
		Return a function that performs the conversion from the
		provided object to a form that PostgreSQL can understand.

		To insert a value into a 'point' field:
			INSERT INTO some_table (pt) VALUES ('1,2');
		'''
		def process(value):
			if value is None:
				return value
			else:
				items = value.split(",")
				return "{0[0]},{0[1]}".format(value.split(","))
		return process

	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that comes from the
		database to a Python object.
		'''
		def process(value):
			if value is None:
				return None
			else:
				# value from db will be a string of the form (without the quotes): '1,2'
				#point_values = value.split(",") # not sure if there will be surrounding quotes
				#return (float(point_values[0]), float(point_values[1]))
				return np.array(ast.literal_eval(value))
		return process

	@property
	def sql_string(self):
		'''
		The PostgreSQL string representation of this point value.
		'''
		return f"POINT({self.x},{self.y})"

class PGPolygon(types.UserDefinedType):
	'''
	Class to represent PostgreSQL "POLYGON" datatype.

	Ref: https://www.postgresql.org/docs/current/datatype-geometric.html#DATATYPE-POLYGON

	Using this datatype definition, tuples of float values can be provided
	to point columns, and tuples of float values will be returned.

	:param polygon: points of a polygon in a NumPy `ndarray`, shape (n,2)
	'''
	def __init__(self, points=None):
		if isinstance(points, np.ndarray):
			self.points = points
		elif isinstance(points, str):
			self.points = np.array(points)
		elif points is None:
			return
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
		'''
		def process(value):
			''' Return a string. '''
			if value is None:
				return None
			if isinstance(value, np.ndarray):
				return "'{}'::POLYGON".format(str(value.tolist()).replace("[","(").replace("]",")"))
			else:
				# assuming some combination of tuples/lists
				return "'{}'::POLYGON".format(str(value).replace("[","(").replace("]",")"))
		return process

	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that
		comes from the database to a Python object.
		'''
		def process(value):
			''' Return a Python object. '''
			#print("-------------------------------- polygon being created ----")
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

	register_dumper(PGPoint, _PGPointDumper)
	register_dumper(PGPolygon, _PGPolygonDumper)
