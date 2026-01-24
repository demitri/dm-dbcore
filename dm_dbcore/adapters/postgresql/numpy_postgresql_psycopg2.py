#!/usr/bin/python

"""
Backup of the psycopg2-based NumPy PostgreSQL adapter.

This file preserves the pre-psycopg3 implementation for reference.
The active adapter is now in numpy_postgresql.py (psycopg v3).
"""

'''
This module translates NumPy values to values that psycopg2 can understand.
By default, psycopg2 doesn't know about NumPy data types; this allows one
to use NumPy values as database inputs.

See:
http://rehalcon.blogspot.com/2010/03/sqlalchemy-programmingerror-cant-adapt.html
and
http://initd.org/psycopg/docs/advanced.html#adapting-new-python-types-to-sql-syntax
and
http://pyopengl.sourceforge.net/pydoc/numpy.core.numerictypes.html

http://numpy.sourceforge.net/numdoc/HTML/numdoc.htm

NumPy data types:

int8 int16 int32 int64 int128
uint8 uint16 uint32 uint64 uint128
float16 float32 float64 float96 float128 float256
complex32 complex64 complex128 complex192 complex256 complex512
'''

import io

numpy_available = False
using_psycopg2 = False

try:
	import numpy
	numpy_available = True
except ImportError:
	pass
	
try:
	import psycopg2
	from psycopg2.extensions import register_adapter, AsIs, Float
	using_psycopg2 = True
except ImportError:
	pass

if using_psycopg2 and numpy_available:
	def adapt_numpy_int8(numpy_int8):
		return AsIs(numpy_int8)
	register_adapter(numpy.int8, adapt_numpy_int8)

	def adapt_numpy_int16(numpy_int16):
		return AsIs(numpy_int16)
	register_adapter(numpy.int16, adapt_numpy_int16)

	def adapt_numpy_int32(numpy_int32):
		return AsIs(numpy_int32)
	register_adapter(numpy.int32, adapt_numpy_int32)

	def adapt_numpy_int64(numpy_int64):
		return AsIs(numpy_int64)
	register_adapter(numpy.int64, adapt_numpy_int64)

	#def adapt_numpy_int128(numpy_int128):
	#	return AsIs(numpy_int128)
	#register_adapter(numpy.int128, adapt_numpy_int128)

	def adapt_numpy_uint8(numpy_uint8):
		return AsIs(numpy_uint8)
	register_adapter(numpy.uint8, adapt_numpy_uint8)

	def adapt_numpy_uint16(numpy_uint16):
		return AsIs(numpy_uint16)
	register_adapter(numpy.uint16, adapt_numpy_uint16)

	def adapt_numpy_uint32(numpy_uint32):
		return AsIs(numpy_uint32)
	register_adapter(numpy.uint32, adapt_numpy_uint32)

	def adapt_numpy_uint64(numpy_uint64):
		return AsIs(numpy_uint64)
	register_adapter(numpy.uint64, adapt_numpy_uint64)

	#def adapt_numpy_uint128(numpy_uint128):
	#	return AsIs(numpy_uint128)
	#register_adapter(numpy.uint128, adapt_numpy_uint128)

	#def adapt_numpy_float16(numpy_float16):
	#	return AsIs(numpy_float16)
	#register_adapter(numpy.float16, adapt_numpy_float16)

	def adapt_numpy_float32(numpy_float32):
		return AsIs(numpy_float32)
	register_adapter(numpy.float32, adapt_numpy_float32)

	def adapt_numpy_float64(numpy_float64):
		return AsIs(numpy_float64)
	register_adapter(numpy.float64, adapt_numpy_float64)

	#def adapt_numpy_float96(numpy_float96):
	#	return AsIs(numpy_float96)
	#register_adapter(numpy.float96, adapt_numpy_float96)

	#def adapt_numpy_float128(numpy_float128):
	#	return AsIs(numpy_float128)
	#register_adapter(numpy.float128, adapt_numpy_float128)

	#def adapt_numpy_float256(numpy_float256):
	#	return AsIs(numpy_float256)
	#register_adapter(numpy.float256, adapt_numpy_float256)

	# def adapt_numpy_complex32(numpy_complex32):
	# 	return AsIs(numpy_complex32)
	# register_adapter(numpy.complex32, adapt_numpy_complex32)
	# 
	# def adapt_numpy_complex64(numpy_complex64):
	# 	return AsIs(numpy_complex64)
	# register_adapter(numpy.complex64, adapt_numpy_complex64)

	#def adapt_numpy_complex128(numpy_complex128):
	#	return AsIs(numpy_complex128)
	#register_adapter(numpy.complex128, adapt_numpy_complex128)

	#def adapt_numpy_complex192(numpy_complex192):
	#	return AsIs(numpy_complex192)
	#register_adapter(numpy.complex192, adapt_numpy_complex192)

	#def adapt_numpy_complex256(numpy_complex256):
	#	return AsIs(numpy_complex256)
	#register_adapter(numpy.complex256, adapt_numpy_complex256)

	#def adapt_numpy_complex512(numpy_complex512):
	#	return AsIs(numpy_complex512)
	#register_adapter(numpy.complex512, adapt_numpy_complex512)

	def adapt_numpy_nan(numpy_nan):
		return "'NaN'"
	register_adapter(numpy.nan, adapt_numpy_nan)

# 	def nan_to_null(f,
# 					_NULL=AsIs('NULL'),
# 					_NaN=numpy.NaN,
# 					_Float=Float):
# 		if f is not _NaN:
# 			return _Float(f)
# 		return _NULL
# 	register_adapter(float, nan_to_null)
	
	def adapt_numpy_inf(numpy_inf):
		return "'Infinity'"
	register_adapter(numpy.inf, adapt_numpy_inf)

	def adapt_numpy_ndarray(numpy_ndarray):
		return AsIs(numpy_ndarray.tolist())
	register_adapter(numpy.ndarray, adapt_numpy_ndarray)
	
# 	def adapt_numpy_array(numpy_ndarray):
# 		''' Convert np.array for into a Binary object for insertion into PostgreSQL. '''
# 		out = io.BytesIO()
# 		np.save(out, numpy_ndarray) # save an array ("numpy_ndarray") to a binary file ("out") in NumPy .npy format
# 		out.seek(0) # reset stream position to beginning
# 		return psycopg2.Binary(out.read())
# 	psycopg2.extensions.register_adapter(np.ndarray, adapt_numpy_array)
	
# 	def typecast_numpy_array(string_representation, cursor):
# 		''' Typecast the string representation returned from the database to a Numpy array. '''
# 		if string_representation is None:
# 			return None
# 		data = psycopg2.BINARY(string_representation, cursor) # http://initd.org/psycopg/docs/module.html?highlight=binary#psycopg2.BINARY
# 		bdata = io.BytesIO(data)
# 		bdata.seek(0)
# 		return np.load(bdata)
# 	type_numpy_array = psycopg2.extensions.new_type(psycopg2.BINARY.values, "numpy array", typecast_numpy_array)
# 	psycopg2.extensions.register_type(type_nunpy_array)
