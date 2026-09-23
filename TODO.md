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
      and `~/.pgpass`). See `scripts/db_connection_test.py` and
      `scripts/test_dm_dbcore.py`. (codex round 3)

### Make ~/.my.cnf just work — the code should figure it out

The asymmetry is the problem: PostgreSQL users get `~/.pgpass` for free because
libpq reads it, so they write no password and it works. MySQL users are told
about `~/.my.cnf` and then have to wire it up themselves, which is exactly the
kind of boilerplate this package exists to delete.

- [ ] When the URL is MySQL and carries no password, dm-dbcore should look one
      up itself via `read_password_from_my_cnf(host=..., user=...)` — matching
      on the URL's host/user — before handing the URL to SQLAlchemy. Then MySQL
      behaves like PostgreSQL: omit the password, it works.
- [ ] Do as much as can be inferred: default the section to `[client]`, fall
      back to any matching entry, honour host/user wildcards, and take
      host/port/user/database from `~/.my.cnf` when the URL omits them
      (`read_connection_options_from_my_cnf` already exists for this).
- [ ] Fail loudly, not silently: if a password is genuinely required and no
      `~/.my.cnf` entry matches, say so — naming the file, section, host and
      user searched — rather than letting the connection fail with a bare
      "Access denied".
- [ ] Ask before caching credentials anywhere. Read at connect, do not persist.

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

---

# Found while adding CI, tests and coverage (2026-08-23)

## ~~`~/.my.cnf` valueless options crashed the parser~~ — FIXED 2026-08-23

`_load_my_cnf_parser()` built a default `ConfigParser()`, which rejects options
written without `=value`. Real MySQL option files are full of them —
`no-auto-rehash`, `quick`, `skip-ssl` — so an ordinary `~/.my.cnf` raised
`configparser.ParsingError` naming a line number, and reading a password from it
was impossible. Now `ConfigParser(allow_no_value=True)`; such a key parses to a
`None` value, and every read tests the value for truth, so a valueless key is
never mistaken for a setting. Covered by
`tests/test_mysql_utils.py::test_valueless_options_are_tolerated`.

This is a prerequisite for "Make `~/.my.cnf` just work" above: that plan has
dm-dbcore reading the file automatically, which would have hit this on the
first real config file it met.

## ~~An unreadable `~/.my.cnf` read as an absent one~~ — FIXED 2026-08-23

Found by the mandatory silent-skip pass over the commits above, in the same
function. `_load_my_cnf_parser()` wrapped the read in `except OSError: return
None` — the identical return to "the file does not exist". So a `~/.my.cnf`
with the wrong permissions, which is the commonest way to break one, silently
became "no password found", and the user got MySQL's bare "Access denied" with
nothing pointing at the real cause.

The `exists()` check above it already covers the one case that legitimately
means "nothing configured". The read is now unguarded, so a permission error
surfaces as a permission error. This is the "Fail loudly, not silently" bullet
of the `~/.my.cnf` plan above, applied to the read path.

Covered by
`tests/test_mysql_utils.py::test_an_unreadable_file_raises_rather_than_reading_as_absent`.

## MetadataCache's default cache directory is bound at import time

```python
def __init__(self, dbc=None, filename=None,
             path=os.path.join(os.path.expanduser("~"), ".sqlalchemy_cache")):
```

The default is a *default argument*, so `$HOME` is expanded once when the module
is imported, not when the cache is used.

- [ ] Two consequences. Changing `$HOME` afterwards has no effect, which is why
      no test exercises `DatabaseConnection(cache_name=...)` end to end — it
      would write into the developer's real `~/.sqlalchemy_cache`. And a process
      that legitimately relocates `$HOME` (containers, CI, a service account)
      silently keeps the old path.
- [ ] Fix shape: `path=None` in the signature, resolve inside `__init__`. Then
      the caching path becomes testable, and the `cache_name` integration gap
      noted in the coverage section below closes with it.

## `sql_string` means two different things

`PGPoint.sql_string` and `PGCircle.sql_string` return bare literals
(`POINT(1.5,2.5)`, `<(3.0,4.0),5.0>`). `PGPolygon.sql_string` returns quoted SQL
with a cast: `'((1, 2), (3, 4))'::POLYGON`. It also renders through `str()` on a
list, so it carries spaces the other two do not.

- [ ] Decide which one the property means and make all three agree. The polygon
      form is the odd one out and is the shape that caused the `bind_processor`
      bug fixed on 2026-07-16 — the same confusion between *data* and *SQL*,
      surviving in a second place. `_polygon_literal()` already produces the
      data form; `sql_string` should probably use it.
- [ ] Nothing in the package calls `sql_string`. It is public API for callers
      hand-writing SQL, which is why the inconsistency has gone unnoticed.

## The style gate needs Python 3.10, the package claims 3.8

`scripts/check_style.py` inspects `ast.MatchAs` / `ast.MatchStar` /
`ast.MatchMapping`, which do not exist before 3.10, and `tests/test_check_style.py`
has fixtures containing `match` statements, which are a SyntaxError before 3.10.

This is not a limit on the distribution: the gate lives in `scripts/` and is not
in `[tool.setuptools] packages`. `dm_dbcore/` itself contains no 3.10-only
syntax. CI reflects this — the gate runs in its own job on 3.12, and the package
is tested on 3.8 through 3.13.

- [ ] Optional: make the gate degrade explicitly on <3.10 (`getattr(ast, "MatchAs", ())`)
      if it ever needs to run on an older interpreter. Do not do this silently —
      a gate that quietly checks less is worse than one that refuses to start.

## Coverage baseline and where the gaps are

First measured baseline, offline (no PostgreSQL): **68%** overall, 204 tests.
The gaps are known, not mysterious:

- `numpy_postgresql_psycopg2.py` — 0%, 51 statements. The deliberate reference
  copy (see above). Costs about seven points of the total; deliberately not
  excluded from the report, so the figure stays honest.
- `DatabaseConnection.py` — 55% offline. The uncovered regions are the
  PostgreSQL and MySQL schema-hash and staleness paths, the adapter-loading
  branches, and `validate_connection`'s per-error-class messages. The CI
  PostgreSQL job covers most of the first two; the MySQL paths stay uncovered
  until "MySQL is unverified end-to-end" above is done.
- `ast_pg_geometry.py` — 25%. Needs both `cornish` and a live server.
- No `fail_under` is set. A threshold nobody has measured is a guess. Set one
  from a real baseline once CI has reported a few runs on `main`.
- No `exclude_also` either. A draft of this config excluded the
  optional-dependency guards and scored 71%. Measured against no exclusions at
  all, that was three points bought by hiding 48 statements — and it was wrong
  on its own terms, because CI does not install `cornish`, so the
  `except ImportError:` fallback in `ast_pg_geometry.py` genuinely executes
  there. The exclusion was discarding coverage that was being achieved.

## Two sources of packaging truth

`setup.py` and `pyproject.toml` both declare name, version, classifiers and
extras, and they had already drifted: `setup.py` was missing the `astronomy`
extra that `pyproject.toml` has. Added, but the next drift is a matter of time.

- [ ] `pyproject.toml` is sufficient on its own with a modern setuptools.
      Reduce `setup.py` to nothing (or delete it) rather than maintaining the
      same facts twice.

- [ ] `DatabaseConnection.py:518` uses `assert` for the None-connection-string guard — stripped under `python -O`, leaving an unrelated AttributeError; replace with an explicit raise. (sonnet round 3, 2026-08-24; pre-existing)
- [ ] Singleton: log at debug level when a losing concurrent caller passed a different `database_connection_string` than the registered winner's — the first-caller-wins contract is documented but now officially exercised concurrently. (sonnet round 3, 2026-08-24)
- [ ] Style gate: replace the flat `rebound` / `import_shadowed` model with one scope-aware symbol resolver (module/class/function/type-parameter scope stack) shared by calls, decorators and bases. Would remove the documented flat-scope false negatives (e.g. a function parameter or PEP 695 type parameter named `Table` disowns the module-level import). (codex, 2026-09-23)
