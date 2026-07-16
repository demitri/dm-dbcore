# dm-dbcore TODO

Deferred items, with the evidence that produced them. Each was found while
fixing the templates and adapters on 2026-07-16 and consciously postponed —
they are not unknowns, just unscheduled.

## MySQL is unverified end-to-end

`determine_database_type()` now accepts `mysql+pymysql://` as well as bare
`mysql://` (it previously accepted only the latter, which SQLAlchemy resolves to
the **mysqldb** driver — a driver dm-dbcore does not install, while the `[mysql]`
extra installs **pymysql**). The string-level fix is verified; a real connection
is not.

- [ ] Smoke-test against a live MySQL/MariaDB server: `pip install dm-dbcore[mysql]`,
      then run `templates/TEMPLATE_Connection.py` and `TEMPLATE_ModelClasses_MySQL.py`
      with `DATABASE_TYPE = DBTYPE_MYSQL` and `SCHEMA = None`.
- [ ] Confirm `dm_dbcore.mysql.read_password_from_my_cnf()` still reads `~/.my.cnf`
      (pymysql does not do this itself, unlike libpq/`~/.pgpass`).
- [ ] Decide whether bare `mysql://` should be rejected outright the way bare
      `postgresql://` is. It currently silently selects an uninstalled driver.
      A principled fix is to parse with `sqlalchemy.engine.url.make_url()` and
      branch on `get_backend_name()` / `get_driver_name()` instead of prefix
      matching — but that must preserve the deliberate psycopg2 rejection.

Note: pymysql is NOT installed on the development machine; mysqldb IS. That is
the opposite of what the packaging declares, and is why this went unnoticed.

- [ ] The diagnostic scripts tell MySQL users to put their password in
      `~/.my.cnf`, but in URL mode they hand the URL straight to
      `DatabaseConnection`, and pymysql does not read `~/.my.cnf` (unlike libpq
      and `~/.pgpass`). Either call `read_password_from_my_cnf()` in URL mode or
      say that MySQL users must use `--module` mode. See
      `scripts/db_connection_test.py` and `scripts/test_dm_dbcore.py`.
      (codex round 3)

## Unify db.metadata, Base.metadata, and SCHEMA (metadata caching)

Raised by codex review of 07ebc8c..04539a3. The caching *machinery* is now fixed
and verified — `MetadataCache.write()` is actually called (it never was, so
`cache_name` bought nothing), and the PostgreSQL staleness hash no longer derives
from `current_schema()`, which returns NULL once the search_path is cleared and
made the hash a constant over an empty set. An `ALTER TABLE` is now correctly
detected as stale.

What remains is a design decision, not a defect:

`DatabaseConnection` reflects `db.metadata` from the database's DEFAULT schema.
With the search_path cleared that is empty, so for any project using a named
schema the cache stores nothing. Meanwhile the model templates reflect through
`Base.metadata` with `autoload_with=`, which the cache does not cover at all. So
caching cannot currently speed up the thing it exists to speed up.

- [ ] Decide the shape. Options: have `DatabaseConnection` reflect the configured
      schema(s) rather than the default; or let a project's `Base` share
      `db.metadata` so that autoload_with= populates the cached object; or drop
      the caching feature. Each has consequences for the three-layer pattern in
      AI_DB_CONNECTION_PATTERN.md.
- [ ] `TEMPLATE_Connection.py`'s CACHE_NAME comment currently documents this
      limitation honestly. Rewrite it once the design is settled.

## Cache staleness hashes are low-fidelity

Codex round 2. The hashes now work (they previously could not detect anything at
all), but they under-detect. Low priority while caching covers nothing useful —
revisit together with the unification item above.

- [ ] PostgreSQL: `_compute_postgresql_schema_hash()` hashes only
      schema/table/column, the broad `data_type`, and nullability. It will NOT
      notice `VARCHAR(100)` -> `VARCHAR(200)`, numeric precision, column
      defaults, enum/domain changes, identity/generated attributes, or
      added/removed PK/FK/UNIQUE/CHECK constraints — so stale pickled metadata
      would be accepted as current. Add `character_maximum_length`,
      `numeric_precision`, `numeric_scale`, `column_default`, `udt_name`, and a
      second query over `information_schema.table_constraints`.
- [ ] MySQL: `_compute_mysql_schema_hash()` hashes `TABLES.UPDATE_TIME`, which
      tracks DATA modification, not schema. Ordinary DML invalidates the cache;
      some engines leave it NULL entirely. Hash `information_schema.COLUMNS` the
      way PostgreSQL does.
- [ ] Better still: hash a migration/schema revision number if the project has
      one, rather than fingerprinting the catalogue.

## Singleton keying (codex, higher-level)

`DatabaseConnection._singletons` is keyed by class only, and the instance is
stored BEFORE initialization completes:

- two different URLs in one process silently share the first connection, which
  undercuts the advertised multi-database support;
- a failed initialization leaves a partially built singleton behind (e.g. a bad
  connection string raises from `determine_database_type()` *after* the instance
  is registered), so retrying with corrected credentials returns the broken one.

- [ ] Key by normalized URL, or drop the singleton and let SQLAlchemy's engine
      pooling handle reuse. Either way, do not register the instance until
      __new__ has succeeded.

## Pre-existing silent skips in DatabaseConnection.py

Found by the mandatory silent-skip pre-pass. Not introduced by this work, but in
files it touched. `MetadataCache.write()`'s bare `except: pass` was fixed as part
of making caching work; these remain:

- [ ] `clearSearchPathCallback` (~line 53): `except Exception: pass`, commented
      "silently skip". It uses exceptions to sniff "is this PostgreSQL?", so a
      genuine PostgreSQL error (permissions, dead connection) is swallowed
      identically. `DatabaseConnection` already knows `database_type` — it does
      not need to guess by failure. This is the same pattern that hid the dead
      psycopg dumper registrations for the life of the package.
- [ ] `cacheIsStale` (~lines 217, 243): `except Exception: logger.warning(...);
      return True`. Warning-level logging is not a remediation. Fail direction is
      safe (treat as stale) but a permission error is permanent and unreported.
- [ ] `MetadataCache.read` (~line 183): `except IOError: return`. Also
      inconsistent — `pickle.load` raises `UnpicklingError`, not `IOError`, so a
      corrupt cache propagates while an unreadable one is swallowed.

## Astronomy geometric types (cornish)

- [ ] `PGASTCircle` and `PGASTPolygon` do not set `cache_ok`, so SQLAlchemy emits
      a per-query performance warning for them. `PGPoint`, `PGCircle`, `PGPolygon`,
      `PGCIText`, and `PGXML` all set it now. Needs cornish installed to exercise.
- [ ] These are the one case requiring manual `ischema_names` registration (they
      must override the plain `PGCircle`/`PGPolygon` that dm-dbcore auto-registers).
      Documented in README.md; not tested.

## ~~PGPolygon.bind_processor~~ — FIXED 2026-07-16, was not deferred

Recorded here because the first draft of this file wrongly said the broken
`bind_processor` was "bypassed in practice and has not bitten anyone". That was
false, and only writing to a POLYGON column revealed it. It was reachable and
every write went through it:

  - `str()` on a PGPolygon returns the compiled *type name* (`'POLYGON'`),
    because the class doubles as SQLAlchemy type and Python value. The
    else-branch did `str(value)`, producing the parameter `"'POLYGON'::POLYGON"`.
  - Both branches embedded a `::POLYGON` cast and quotes in a *bound parameter*,
    which is data, not SQL.

Now uses the existing `_polygon_literal()` helper and accepts either a PGPolygon
or a raw ndarray/sequence. Verified round-tripping both against PostgreSQL 18.

Lesson for future passes: test the WRITE path of every type, not a sample. The
point and circle round-trips passed while polygon was broken.

## numpy_postgresql_psycopg2.py

Kept deliberately as a reference copy of the psycopg2-era adapter. Not imported
by the package's normal path. Leave it alone.
