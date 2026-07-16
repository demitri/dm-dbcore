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
