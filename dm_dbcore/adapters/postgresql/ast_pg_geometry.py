#!/usr/bin/env python
'''
Astronomy-flavoured PostgreSQL geometric types, backed by the `cornish` library.

Same two PostgreSQL column types as ``pggeometry`` -- circle and polygon -- but
reading one returns a ``cornish.ASTCircle`` / ``cornish.ASTPolygon`` on an ICRS
frame rather than a plain PGCircle / PGPolygon.

These are the one case that needs manual registration. ``DatabaseConnection``
auto-registers the plain types, so to get these instead you must override the
``ischema_names`` entries BEFORE your model classes are imported (reflection
reads that mapping at import time). See the USAGE block below.

Requires the astronomy extra: ``pip install dm-dbcore[astronomy]``. Without
numpy and cornish the module still imports -- so a downstream
``from dm_dbcore.adapters import PGASTCircle`` does not explode on a machine
that lacks them -- but instantiating either class raises ImportError naming
what to install.

USAGE:

* PGASTCircle and PGASTPolygon are to be used to map columns in the database of those types.

-----------------------------------------

Example usage, e.g. at the top of a ModelClasses file:

from sqlalchemy.dialects.postgresql import base as pg
from dm_dbcore.adapters.postgresql.ast_pg_geometry import PGASTCircle, PGASTPolygon
pg.ischema_names['circle'] = PGASTCircle
pg.ischema_names['polygon'] = PGASTPolygon

This will assign the PGASTCircle/PGASTPolygon object types for all fields of those types.

For illustrative purposes in the comments below, assume a column defined as:
CREATE TABLE some_table (
	circ circle,
	poly polygon
);

DEPENDENCIES:

This module requires:
- numpy
- cornish (astronomy library)

If these dependencies are not available, the classes can still be imported but will
raise an error when instantiated.
'''

__author__ = "Demitri Muna"

import ast  # Abstract Syntax Trees / https://docs.python.org/3.7/library/ast.html
import sqlalchemy.types as types

# Try to import dependencies - fail silently if not available
try:
	import numpy as np
	from cornish import ASTCircle, ASTPolygon, ASTICRSFrame
	_DEPENDENCIES_AVAILABLE = True
except ImportError:
	_DEPENDENCIES_AVAILABLE = False
	# Create placeholder classes that will raise helpful errors if used
	class ASTCircle:
		pass
	class ASTPolygon:
		pass
	class ASTICRSFrame:
		pass
	class np:
		@staticmethod
		def array(*args, **kwargs):
			raise ImportError("numpy is required for PGASTPolygon")
		
class PGASTCircle(types.UserDefinedType):
	'''
	Class to represent PostgreSQL "circle" datatype with astronomical coordinate support.

	https://www.postgresql.org/docs/current/datatype-geometric.html#DATATYPE-CIRCLE

	Requires: numpy, cornish
	'''
	def __init__(self):
		if not _DEPENDENCIES_AVAILABLE:
			raise ImportError(
				"PGASTCircle requires 'numpy' and 'cornish' packages. "
				"Install with: pip install numpy cornish"
			)
		super().__init__()

	def bind_processor(self, dialect):
		'''
		Return a function that performs the conversion from the
		provided object to a form that PostgreSQL can understand.
		
		To insert a value into a 'circle' field:
			INSERT INTO some_table (pt) VALUES (CIRCLE(POINT(1,2),3));
		'''
		def process(value):
			if value is None:
				return value
			#xy, radius = value.split(",")
			# value is an ASTCircle object
			return "CIRCLE(POINT({0[0]},{0[1]}),{1})".format(value.center, value.radius)
		return process
		
	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that comes from the
		database to a Python object.
		'''
		def process(value):
			if value is None:
				return None
			#
			# value from db will be a string of the form (without the quotes):
			#
			#   "<(82.66287263711133,2.1669098446685364),0.13926999141057494>"
			#
			for c in "<>()":
				value = value.replace(c, "")
			x, y, radius = [float(x) for x in value.split(",")]
			return ASTCircle(frame=ASTICRSFrame(), center=[x, y], radius=radius)
		return process

class PGASTPolygon(types.UserDefinedType):
	'''
	Class to represent PostgreSQL "polygon" datatype with astronomical coordinate support.

	https://www.postgresql.org/docs/current/datatype-geometric.html#DATATYPE-POLYGON

	Requires: numpy, cornish
	'''
	def __init__(self):
		if not _DEPENDENCIES_AVAILABLE:
			raise ImportError(
				"PGASTPolygon requires 'numpy' and 'cornish' packages. "
				"Install with: pip install numpy cornish"
			)
		super().__init__()

	def get_col_spec(self):
		return "POLYGON"

	def bind_processor(self, dialect):
		'''
		Return a function that performs the conversion from the
		provided object to a form that PostgreSQL can understand.
		
		To insert a value into a 'polygon' field:
			INSERT INTO some_table (pt) VALUES (POLYGON('((0,0),(0,1),(1,1),(0,1))'));
		'''
		def process(value):
			if value is None:
				return value
			# value is an ASTPolygon object
			return "'{}'::POLYGON".format(str(value.tolist()).replace("[", "(").replace("]", ")"))
		return process
		
	def result_processor(self, dialect, coltype):
		'''
		Return a function that converts the value that comes from the
		database to a Python object.
		'''
		def process(value):
			if value is None:
				return None
			#
			# value from db will be a string of the form (without the quotes):
			#
			#   "'((0,0),(0,1),(1,1),(1,0))'"
			#
			points = np.array(ast.literal_eval(value))
			return ASTPolygon(frame=ASTICRSFrame(), points=points)
		return process
		
	
	
