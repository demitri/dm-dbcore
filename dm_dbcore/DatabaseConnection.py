#!/usr/bin/python
#

import os
import pickle
import pathlib
import logging
from datetime import datetime
from contextlib import contextmanager

import sqlalchemy
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import registry
from sqlalchemy.event import listens_for
from sqlalchemy.pool import Pool
#from sqlalchemy.ext.automap import automap_base

logger = logging.getLogger("DatabaseConnection logger")

# Database type constants
DBTYPE_POSTGRESQL = "postgresql"
DBTYPE_MYSQL = "mysql"
DBTYPE_SQLITE = "sqlite"

@listens_for(Pool, 'connect')
def clearSearchPathCallback(dbapi_con, connection_record):
    '''
    When creating relationships across schema, SQLAlchemy
    has problems when you explicitly declare the schema in
    ModelClasses and it is found in search_path.

    The solution is to set the search_path to "$user" for
    the life of any connection to the database. Since there
    is no (or shouldn't be!) schema with the same name
    as the user, this effectively makes it blank.

    This callback function is called for every database connection.
    It only executes for PostgreSQL databases (detected by trying
    the SET search_path command, which is PostgreSQL-specific).

    For the full details of this issue, see:
    http://groups.google.com/group/sqlalchemy/browse_thread/thread/88b5cc5c12246220

    dbapi_con - database connection object
    connection_record - type: sqlalchemy.pool._ConnectionRecord
    '''
    # Only execute SET search_path for PostgreSQL databases
    # MySQL and other databases don't support this command
    try:
        cursor = dbapi_con.cursor()
        cursor.execute('SET search_path TO theres_no_schema_by_this_name_no_sir')
        dbapi_con.commit()
    except Exception:
        # Not a PostgreSQL database or command not supported - silently skip
        pass

@contextmanager
def session_scope(db):
	"""Provide a transactional scope around a series of operations."""
	session = db.Session()
	try:
		yield session
		session.commit()
	except:
		session.rollback()
		raise
	finally:
		session.close()

class MetadataCache():
	'''
	This is a custom object used to write/read SQLAlchemy metadata to save time setting up 'autoload'ed tables.

	Each model classes file will define a filename for the cached metadata. If that file is found it will be
	loaded. If a schema.table being defined matches one found in the cache, it will be set to that class which
	will avoid the autoload. Otherwise, the cache will be set to 'None'. At the end of the file if the cache
	was 'None', the metadata will be written.

	Multiple model classes are supported, however, all MUST share the same metadata cache file if there
	are relationships between schemas. The metadata will be overwritten at the end of each file, but it will
	be the cumulative metadata gathered. If multiple files are written for the same database (e.g. one per
	schema), any relationships between schemas will not be properly defined if reloaded individually.

	No true anymore, but needs longer term testing. --> IMPORTANT NOTE!! The metadata is never compared to the database schema. Any time the database schema is updated,
	the caches must be deleted manually.

	A corresponding schema and table are required in the database for the check to see if the cache is stale.
	This is detailed at the bottom of this file.

	:param dbc: the `DatabaseConnection` object
	:param filename: the filename to be used for the cache
	:param path: the location to save the path, defaults to $HOME/.sqlalchemy_cache
	'''
	#def __init__(self, dbc:DatabaseConnection=None, filename:str=None, path=os.path.join(os.path.expanduser("~"),
	def __init__(self, dbc=None, filename:str=None, path=os.path.join(os.path.expanduser("~"), ".sqlalchemy_cache")):
		if filename is None:
			raise Exception("Please specify a filename for the metadata cache.")
		self.filename = filename
		self.cache_directory = path
		self.metadata = None
		self.databaseConnection = dbc

	@property
	def cachePath(self):
		''' Return the full filename and path of the cache. '''
		#return os.path.join(self.cache_directory, self.filename)
		return pathlib.Path(self.cache_directory) / self.filename

	def _compute_mysql_schema_hash(self):
		'''
		Compute MD5 hash of MySQL schema based on table names and UPDATE_TIME values.
		Returns hash string.
		'''
		import hashlib

		with self.databaseConnection.engine.connect() as connection:
			# Get database name from connection
			db_name = connection.execute(text("SELECT DATABASE()")).scalar()

			# Get all table update times, sorted for consistent hashing
			query = text("""
				SELECT TABLE_NAME, UPDATE_TIME
				FROM information_schema.TABLES
				WHERE TABLE_SCHEMA = :db_name
				ORDER BY TABLE_NAME
			""")
			results = connection.execute(query, {"db_name": db_name})

			# Create hash of table names and update times
			hash_input = ""
			for row in results:
				table_name = row[0]
				update_time = row[1] or "NULL"  # Some tables may have NULL UPDATE_TIME
				hash_input += f"{table_name}:{update_time}|"

			return hashlib.md5(hash_input.encode()).hexdigest()

	def _compute_postgresql_schema_hash(self):
		'''
		Compute MD5 hash of PostgreSQL schema based on table structure.
		Uses information_schema.columns to detect schema changes (DDL).
		No manual setup required - alternative to metadata.schema_metadata table.
		Returns hash string.
		'''
		import hashlib

		with self.databaseConnection.engine.connect() as connection:
			# Get current schema (or use specific schema if needed)
			schema = connection.execute(text("SELECT current_schema()")).scalar()

			# Hash table names + column definitions
			query = text("""
				SELECT table_name, column_name, data_type, is_nullable
				FROM information_schema.columns
				WHERE table_schema = :schema
				ORDER BY table_name, ordinal_position
			""")
			results = connection.execute(query, {"schema": schema})

			# Create hash of table structure
			hash_input = ""
			for row in results:
				hash_input += "|".join(str(v) for v in row) + "|"

			return hashlib.md5(hash_input.encode()).hexdigest()

	def read(self):
		'''
		Read the cached metadata for this database connection.
		'''
		cache_path = self.cachePath

		if cache_path.exists(): #os.path.exists(cache_path):

			if self.cacheIsStale():
				self.cachePath.unlink()
				self.metadata = None
			else:
				try:
					with open(cache_path, 'rb') as cache_file:
						self.metadata = pickle.load(file=cache_file)
						logger.info(f"Metadata cache read: {self.metadata.tables.keys()}")
				except IOError:
					return

	def cacheIsStale(self):
		'''
		Check if the schema has been modified since this cache was made.

		PostgreSQL: Uses hash of information_schema.columns (no manual setup required)
		MySQL: Uses hash of information_schema.TABLES update times
		'''
		file_timestamp = datetime.fromtimestamp(self.cachePath.stat().st_mtime)

		if self.databaseConnection.database_type == DBTYPE_POSTGRESQL:
			# PostgreSQL: compute hash of schema structure from information_schema
			try:
				current_hash = self._compute_postgresql_schema_hash()

				# Store/retrieve hash alongside cache file
				hash_file = self.cachePath.with_suffix('.hash')

				if hash_file.exists():
					with open(hash_file, 'r') as f:
						cached_hash = f.read().strip()

					if current_hash != cached_hash:
						logger.info("Metadata cache is stale (schema hash changed).")
						return True
					else:
						logger.info("Metadata cache is current.")
						return False
				else:
					# No hash file exists, consider stale
					logger.info("Metadata cache is stale (no hash file).")
					return True
			except Exception as e:
				logger.warning(f"Could not check PostgreSQL metadata staleness: {e}")
				return True

		elif self.databaseConnection.database_type == DBTYPE_MYSQL:
			# MySQL: compute hash of all table UPDATE_TIME values
			try:
				current_hash = self._compute_mysql_schema_hash()

				# Store/retrieve hash alongside cache file
				hash_file = self.cachePath.with_suffix('.hash')

				if hash_file.exists():
					with open(hash_file, 'r') as f:
						cached_hash = f.read().strip()

					if current_hash != cached_hash:
						logger.info("Metadata cache is stale (schema hash changed).")
						return True
					else:
						logger.info("Metadata cache is current.")
						return False
				else:
					# No hash file exists, consider stale
					logger.info("Metadata cache is stale (no hash file).")
					return True
			except Exception as e:
				logger.warning(f"Could not check MySQL metadata staleness: {e}")
				return True

		# Unknown database type or SQLite - consider stale to be safe
		return True

	def write(self, metadata=None):
		'''
		Write the SQLAlchemy metadata to a pickle file.
		For PostgreSQL and MySQL, also writes a hash file to track schema changes.
		:param metadata:
		'''
		try:
			cache_dir = os.path.join(os.path.expanduser("~"), ".sqlalchemy_cache")
			if not os.path.exists(cache_dir):
				os.makedirs(cache_dir)

			# Write pickle file
			with open(os.path.join(cache_dir, self.filename), 'wb') as cache_file:
				pickle.dump(metadata, cache_file)
			logger.info("Metadata cache written.")

			# For PostgreSQL and MySQL, write hash file
			if self.databaseConnection.database_type == DBTYPE_POSTGRESQL:
				try:
					current_hash = self._compute_postgresql_schema_hash()
					hash_file = self.cachePath.with_suffix('.hash')
					with open(hash_file, 'w') as f:
						f.write(current_hash)
					logger.info("PostgreSQL schema hash written.")
				except Exception as e:
					logger.warning(f"Could not write PostgreSQL schema hash: {e}")

			elif self.databaseConnection.database_type == DBTYPE_MYSQL:
				try:
					current_hash = self._compute_mysql_schema_hash()
					hash_file = self.cachePath.with_suffix('.hash')
					with open(hash_file, 'w') as f:
						f.write(current_hash)
					logger.info("MySQL schema hash written.")
				except Exception as e:
					logger.warning(f"Could not write MySQL schema hash: {e}")

			for t in metadata.tables.keys():
				logger.debug(f"    - {t}")
		except:
			# couldn't write the file for some reason
			pass


class DatabaseConnection(object):
	'''This class defines an object that makes a connection to a database.
	   The "DatabaseConnection" object takes as its parameter the SQLAlchemy
	   database connection string.

	   This class is best called from another class that contains the
	   actual connection information (so that it can be reused for different
	   connections).

	   This class implements the singleton design pattern. The first time the
	   object is created, it *requires* a valid database connection string.
	   Every time it is called via:

	   db = DatabaseConnection()

	   the same object is returned and contains the connection information.
	'''
	_singletons = dict()

	def determine_database_type(self):
		'''
		Determine the database type from the connection string.

		:return: One of the DBTYPE_* constants
		:raises ValueError: if database type cannot be determined from connection string
		'''
		if self.database_connection_string.startswith('postgresql+psycopg://'):
			return DBTYPE_POSTGRESQL
		elif self.database_connection_string.startswith('mysql://'):
			return DBTYPE_MYSQL
		elif self.database_connection_string.startswith('sqlite://'):
			return DBTYPE_SQLITE
		else:
			raise ValueError(
				f"Unable to determine database type from connection string: '{self.database_connection_string}'. "
				f"Connection string must start with one of: 'postgresql+psycopg://', 'mysql://', or 'sqlite://'"
			)

	@staticmethod
	def validate_connection(engine, database_type=None):
		'''
		Validate database connection with a simple query.

		This is a lightweight, stateless test that doesn't create any objects
		or store state. It performs a basic connectivity check appropriate for
		the database type.

		:param engine: SQLAlchemy engine to test
		:param database_type: One of DBTYPE_* constants (auto-detected if None)
		:return: True if connection successful
		:raises RuntimeError: with detailed error message if connection fails
		'''
		try:
			with engine.connect() as conn:
				# Use a simple query that works on all databases
				result = conn.execute(text('SELECT 1'))
				result.fetchone()

				# For informational purposes, try to get database name and user
				# This helps identify which database we're actually connected to
				try:
					if database_type == DBTYPE_POSTGRESQL:
						db_result = conn.execute(text('SELECT current_user, current_database()'))
						row = db_result.fetchone()
						db_user = row[0]
						db_name = row[1]
					elif database_type == DBTYPE_MYSQL:
						db_result = conn.execute(text('SELECT USER(), DATABASE()'))
						row = db_result.fetchone()
						db_user = row[0].split('@')[0] if row[0] else 'unknown'  # Extract user from 'user@host'
						db_name = row[1]
					elif database_type == DBTYPE_SQLITE:
						# SQLite doesn't have a database name query
						db_user = 'sqlite'
						db_name = 'sqlite'
					else:
						db_user = 'unknown'
						db_name = 'unknown'

					logger.info(f"Database connection validated successfully: connected to '{db_user}@{db_name}'")
				except Exception:
					# If we can't get the DB name, that's OK - we're already connected
					logger.info("Database connection validated successfully")

			return True

		except sqlalchemy.exc.OperationalError as e:
			error_msg = str(e)

			# Provide helpful error messages for common issues
			if 'Access denied' in error_msg or '1045' in error_msg:
				raise RuntimeError(
					f"Database authentication failed. Possible causes:\n"
					f"  1. Incorrect username or password in connection string\n"
					f"  2. User account exists but password has changed\n"
					f"  3. User lacks connection privileges from this host\n"
					f"  4. Database server security settings blocking the connection\n"
					f"Connection string: {engine.url}\n"
					f"Original error: {error_msg}"
				) from e
			elif 'Unknown database' in error_msg or '1049' in error_msg:
				raise RuntimeError(
					f"Database does not exist. The specified database was not found on the server.\n"
					f"Connection string: {engine.url}\n"
					f"Original error: {error_msg}"
				) from e
			elif 'Can\'t connect' in error_msg or 'Connection refused' in error_msg or '2002' in error_msg or '2003' in error_msg:
				raise RuntimeError(
					f"Cannot connect to database server. Possible causes:\n"
					f"  1. Database server is not running\n"
					f"  2. Wrong host or port in connection string\n"
					f"  3. Firewall blocking the connection\n"
					f"  4. Network connectivity issues\n"
					f"Connection string: {engine.url}\n"
					f"Original error: {error_msg}"
				) from e
			else:
				raise RuntimeError(
					f"Database connection failed with unexpected error:\n"
					f"Connection string: {engine.url}\n"
					f"Error: {error_msg}"
				) from e
		except Exception as e:
			raise RuntimeError(
				f"Unexpected error while validating database connection:\n"
				f"Connection string: {engine.url}\n"
				f"Error: {e}"
			) from e

	@staticmethod
	def load_postgresql_database_adapters():
		'''
		Load PostgreSQL-specific database adapters.

		This includes NumPy adapters and custom geometric types (POINT, POLYGON).
		'''
		from .adapters.postgresql import numpy_postgresql
		from .adapters.postgresql.pggeometry import PGPoint, PGPolygon, PGCircle
		from .adapters.postgresql.pgcitext import PGCitext
		from sqlalchemy.dialects.postgresql import base as pg

		# Register PostgreSQL custom types
		pg.ischema_names['point'] = PGPoint
		pg.ischema_names['polygon'] = PGPolygon
		pg.ischema_names['circle'] = PGCircle
		pg.ischema_names['citext'] = PGCitext
		pg.ischema_names['core.citext'] = PGCitext

	@staticmethod
	def load_mysql_database_adapters():
		'''
		Load MySQL-specific database adapters.

		Currently MySQL does not require any custom adapters.
		'''
		pass

	@staticmethod
	def load_sqlite_database_adapters():
		'''
		Load SQLite-specific database adapters.
		'''
		from .adapters.sqlite import numpy_sqlite

	def __new__(cls, database_connection_string=None, cache_name=None):
		"""This overrides the object's usual creation mechanism."""

		if not cls in cls._singletons:
			assert database_connection_string is not None, "A database connection string must be specified!"
			cls._singletons[cls] = object.__new__(cls)

			# ------------------------------------------------
			# This is the custom initialization
			# ------------------------------------------------
			me = cls._singletons[cls] # just for convenience (think "self")

			me.database_connection_string = database_connection_string

			# Determine database type from connection string.
			me.database_type = me.determine_database_type()

			# Load database-specific adapters
			if me.database_type == DBTYPE_POSTGRESQL:
				cls.load_postgresql_database_adapters()
			elif me.database_type == DBTYPE_MYSQL:
				cls.load_mysql_database_adapters()
			elif me.database_type == DBTYPE_SQLITE:
				cls.load_sqlite_database_adapters()

			engine_kwargs = {
				'pool_pre_ping': True,
				'future': True,
				'echo': False    # set to True to print each SQL query (for debugging/optimizing/the curious)
			}
			# pool_size=?? # number of permanent database connections

			# Database-specific parameters:
			if me.database_type == DBTYPE_MYSQL:
				# Force TCP connection for MySQL to avoid Unix socket connection attempts
				engine_kwargs['connect_args'] = {'host': '127.0.0.1'}

			me.engine = create_engine(me.database_connection_string, **engine_kwargs)

			# Validate the connection before proceeding
			# This provides clear error messages for common issues
			try:
				DatabaseConnection.validate_connection(me.engine, me.database_type)
			except RuntimeError as e:
				# Re-raise with additional context about where this failed
				raise RuntimeError(
					f"Failed to establish database connection during DatabaseConnection initialization.\n{e}"
				) from e

			me.metadata = None

			# Load pickle'd metadata or create it from the database.
			if cache_name:
				me.metadataCache = MetadataCache(dbc=me, filename=cache_name)
				me.metadataCache.read()
				if me.metadataCache.metadata is not None:
					me.metadata = me.metadataCache.metadata
#			else:
#				me.metadataCache = None

			if me.metadata is None:
				# create here, reflected from database
				me.metadata = MetaData()
				me.metadata.reflect(bind=me.engine) # optionally can reflect specific tables

			me.Session = scoped_session(sessionmaker(me.engine))

			# ------------------------------------------------

		return cls._singletons[cls]

'''
LEGACY DOCUMENTATION - NO LONGER REQUIRED

As of the current version, metadata cache staleness detection works automatically for both
PostgreSQL and MySQL without requiring any manual database setup:

- PostgreSQL: Uses _compute_postgresql_schema_hash() to hash information_schema.columns
- MySQL: Uses _compute_mysql_schema_hash() to hash information_schema.TABLES

The hash is stored in a .hash file alongside the cache file and compared on each cache read.
No triggers, custom tables, or manual setup are required.

---

The information below is DEPRECATED and kept for historical reference only:

These metadata cache staleness checks previously depended on a table called "metadata.metadata"
in PostgreSQL. This table contained a row that logged the last timestamp when the database
schema changed. The value was written via a trigger that called a function on any database
schema change event. The code below shows how this was set up (NO LONGER REQUIRED):

-- Create the metadata schema/table.
CREATE SCHEMA metadata;
CREATE TABLE metadata.metadata (
   schema_last_modified TIMESTAMP
);
INSERT INTO metadata.metadata (schema_last_modified) VALUES (NOW());

-- Set up the trigger.
CREATE OR REPLACE FUNCTION metadata.notice_event() RETURNS event_trigger AS $$
DECLARE r RECORD;
BEGIN
	FOR r IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
		RAISE NOTICE 'caught % event on %', r.command_tag, r.object_identity;
	END LOOP;
	UPDATE metadata.metadata SET schema_last_modified=NOW();
END;
$$
LANGUAGE plpgsql;

CREATE EVENT TRIGGER tr_notice_alter_table
  ON ddl_command_end WHEN TAG IN (
	  'ALTER TABLE', 'ALTER FUNCTION', 'ALTER SCHEMA', 'ALTER TYPE', 'ALTER VIEW',
	  'CREATE FOREIGN TABLE', 'CREATE FUNCTION', 'CREATE SCHEMA', 'CREATE TABLE',
	  'CREATE TABLE AS', 'CREATE VIEW', 'DROP FOREIGN TABLE', 'DROP FUNCTION',
	  'DROP SCHEMA', 'DROP TABLE', 'DROP VIEW', 'IMPORT FOREIGN SCHEMA'
	  )
  EXECUTE PROCEDURE metadata.notice_event();

-- Command to delete the trigger.
DROP EVENT TRIGGER tr_notice_alter_table;
'''




