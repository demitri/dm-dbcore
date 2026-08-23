# Review log — 2026-08-24

Capped review cycle on the night's work: **d65eaf7..ec0b575**, branch
`fix/templates-and-pg-adapters` (CI workflow, the 204-test suite, coverage
config, README/docstring pass, `.my.cnf` fixes, silent-skip audit fixes).

- **Reviewer:** codex MCP, default model, `sandbox: read-only`,
  `approval-policy: never`, cwd = repo root.
- **Thread:** `01a02d7c-96d0-7cf1-ab14-af07e49df937` — one thread, both rounds
  (round 2 sent with `codex-reply`, so the reviewer saw its own round-1
  findings and could tell a real fix from a papered-over one).
- **Cap:** two rounds, hard, by owner directive. **Round 2 was not dry** — see
  Residuals. The cycle stopped because the cap was reached, not because the
  reviewer ran out of findings.

Prompts were the canonical minimal form, verbatim, nothing appended:

```
Review d65eaf7..ec0b575. Review not only the changes, but make higher level suggestions or improvements if you have any.
addressed in f295ca6; review
```

Fix commits: **f295ca6** (round 1), **400b5aa** (round 2).

---

## Round 1 — findings, verbatim

> ## Findings
>
> 1. **High — failed construction poisons the singleton.**
>    [DatabaseConnection.py](dm_dbcore/DatabaseConnection.py:501) stores the singleton before connection validation and reflection. If either fails, subsequent calls return that half-built object—even with a valid URL—and it lacks `metadata` and `Session`. This contradicts the new README contract. Store the instance only after successful initialization, or remove/dispose it in an exception handler. Add a test that retries after failure.
>
> 2. **Medium — `%` characters break MySQL passwords.**
>    [mysql_utils.py](dm_dbcore/mysql/mysql_utils.py:127) uses `ConfigParser`'s default interpolation. A password such as `pa%ss` raises `InterpolationSyntaxError`, while `100%%safe` is silently changed to `100%safe`. MySQL option values should be literal; construct it with `interpolation=None` and add percent-containing password tests.
>
> 3. **Medium — the documented default test command fails on supported Python 3.8/3.9.**
>    [README.md](README.md:455) recommends plain `python -m pytest`, which collects `test_check_style.py`. Its checker references pattern-matching AST classes introduced in Python 3.10. CI avoids this using `--ignore`, but local developers following the README do not. Explicitly skip that test module below 3.10 or document the corresponding `--ignore` command.
>
> ## Higher-level improvements
>
> - Add one minimal-install CI job using only `pip install -e ".[dev]"`. Every package-test matrix job currently installs NumPy and psycopg, so the absence paths for those optional dependencies are not genuinely tested.
> - Pin the third-party coverage action in [ci.yml](.github/workflows/ci.yml:198) to a full commit SHA because it receives a repository write token. The push-only badge job likely also does not need `pull-requests: write`.
> - Consolidating package metadata into `pyproject.toml` and removing duplicated `setup.py` metadata remains worthwhile; this is already correctly recorded in `TODO.md`.
>
> Validation: `git diff --check` passed, the committed style gate reported 0 violations across 20 files, and 97 pure adapter/public-API tests passed. The complete suite could not run in this read-only environment because pytest could not create temporary files; no live PostgreSQL validation was available. Existing uncommitted changes to `scripts/check_style.py` and `tests/test_check_style.py` were left untouched.

### Adjudication — round 1

**1. Poisoned singleton — REAL, fixed (f295ca6).** Verified by reading
`__new__`: `cls._singletons[cls] = object.__new__(cls)` ran before
`validate_connection` and before reflection, and `me` was an alias into the
registry. Any failure below that point left the half-built object installed
permanently; the next call — with a good URL — returned it with no `metadata`
and no `Session`, failing later and elsewhere with an `AttributeError`.

Fixed as suggested and slightly beyond: the instance is built into a local and
registered only after initialization fully succeeds, *and* a failure disposes
the engine before re-raising. The engine is created before validation, so it
owns a connection pool that the reviewer's version of the fix would have
leaked on every failed attempt. The `except BaseException` re-raises the
original exception unchanged — nothing is suppressed.

Two tests added, per the reviewer's request for a retry test:
`test_failed_construction_leaves_no_singleton` and
`test_a_good_connection_works_after_a_failed_one`.

**2. `%` in MySQL passwords — REAL, fixed (f295ca6).** `ConfigParser`'s default
`BasicInterpolation` treats `%` as an escape; MySQL option-file values are
literal. Both failure shapes confirmed. The silent one is the worse of the
two: `100%%safe` came back as `100%safe`, so the user got "Access denied" with
no hint the file had been read and then altered. `interpolation=None`, plus
four tests covering `pa%ss`, `100%%safe`, `%(user)s` (the interpolation syntax
proper), and the options reader.

**3. `python -m pytest` broken on 3.8/3.9 — REAL, fixed (f295ca6).** Confirmed:
`scripts/check_style.py` references `ast.MatchAs` / `ast.MatchStar` /
`ast.MatchMapping`, all Python 3.10+, while the package declares `>=3.8` in
both `pyproject.toml` and `setup.py`.

Fixed via `collect_ignore` in `tests/conftest.py` rather than the reviewer's
alternative of documenting an `--ignore` incantation in the README — the
documented command should be *true*, not accompanied by a footnote. This also
avoids touching `tests/test_check_style.py`, which was outside this session's
scope (see Out of scope). The skip is explicit, version-gated, and commented
with its reason; `CLAUDE.md` already records that 3.10+ is a limit on the
tool, not on the package, and the CI `style-gate` job still runs that module
unconditionally on 3.12.

**Higher-level: minimal-install CI job — REAL gap, adopted (f295ca6).**
`dm_dbcore/adapters/` is full of `except ImportError` guards that exist so the
package works without NumPy or psycopg, and every CI job installed both — so
not one of those guards had ever been executed in CI. Added a
`minimal-install` job, with an extra step that asserts numpy/psycopg/psycopg2
really are absent, so the job cannot silently decay into a duplicate of `test`
the day something adds numpy to the `dev` extra. This job immediately earned
its place; see round 2 finding 1.

**Higher-level: pin the coverage action, drop `pull-requests: write` — REAL,
adopted (f295ca6).** `coverage-badge` is the only job holding a write token,
and `v3` is a mutable tag repointable by anyone who can push to that
third-party repo. Pinned to `50d15ff8768f6d897b04e5a0805bd1a98f7096c4` (v3 as
of 2026-08-24, resolved via the GitHub API), with a comment saying to bump
deliberately. `pull-requests: write` dropped: the job is gated to
push-on-main, where there is no pull request to comment on.

**Higher-level: consolidate `setup.py` into `pyproject.toml` — REJECTED as
out of scope.** Real and worth doing, but it is packaging surgery unrelated to
this commit range, and the reviewer itself notes it is already recorded in
`TODO.md`. Left there.

---

## Round 2 — findings, verbatim

> ## Findings
>
> 1. **High — the new minimal-install job fails.**
>    [ci.yml](.github/workflows/ci.yml:142) runs the entire suite without NumPy, but `test_pg_geometry.py` does not skip its NumPy-dependent polygon tests. Simulating that environment produced **7 failures, 31 passes, 3 skips**. Mark only the NumPy-dependent polygon tests, while retaining explicit tests for the intended no-NumPy error paths.
>
> 2. **Medium — concurrent first callers can receive different singleton instances.**
>    [DatabaseConnection.py](dm_dbcore/DatabaseConnection.py:499) now correctly publishes only after initialization, but the check/build/register sequence is unsynchronized. Connection validation and reflection release the GIL, allowing two threads to both observe an empty registry and build separate objects. A barrier-based reproduction returned two distinct instances, with only the second stored in `_singletons`. Protect first initialization with a class-level lock and add a concurrent-construction test.
>
> The previous findings are otherwise correctly addressed: failed initialization leaves no singleton and retry succeeds; percent-containing MySQL values remain literal; older Python versions ignore the incompatible style tests; and the coverage action is pinned with reduced permissions.
>
> Validation: 97 ordinary adapter/public-API tests passed, `diff --check` passed, and the new singleton retry behavior passed directly. The full filesystem-backed suite remains unavailable in this read-only sandbox. Existing uncommitted style-checker changes were untouched.

### Adjudication — round 2

**1. Minimal-install job fails — REAL, fixed (400b5aa).** Not adjudicated by
reading: a real virtualenv was built with `pip install -e ".[dev]"` and
neither numpy nor psycopg present, and the suite was run in it. Result before
the fix: **7 failed, 124 passed, 5 skipped** — the same seven tests the
reviewer named. (The reviewer's "31 passes, 3 skips" reflects its narrower
sandboxed run; the failure set matched exactly.)

Root cause is in the tests, not the library. `np = ... if _NUMPY_AVAILABLE
else None`, and seven polygon tests dereference `np`, dying on `'NoneType'
object has no attribute 'array'`. Checked the library paths behind the two
failures that raised `RuntimeError` instead — `PGPolygon.__init__` and
`PGPolygon.result_processor` — and both are *correct*: each checks
`_NUMPY_AVAILABLE` first and raises an error naming the missing package and
the exact install command. Nothing in the product needed changing.

Fixed exactly as scoped, including the reviewer's caveat about retaining the
no-NumPy error-path tests:

- `requires_numpy` marker on the seven genuinely NumPy-dependent tests.
- `test_polygon_literal_accepts_lists_and_arrays` split in two so the list
  half — which needs no NumPy — keeps running in the minimal job.
- Four *new* `without_numpy` tests pinning the NumPy-absent contract:
  constructing a polygon with points, and reading a POLYGON column, each raise
  an error naming NumPy; a POLYGON column can still be reflected; and
  `_polygon_literal` still handles plain lists. These paths were written to be
  kind to users without the extra and had never been executed.

After: **130 passed, 12 skipped, 0 failed** in the same NumPy-free
interpreter.

**2. Singleton construction race — REAL, fixed (400b5aa).** Verified against
the code as restructured in f295ca6: the check, the build, and the register
are three separate steps with no lock, and both `validate_connection` and
`metadata.reflect` do I/O and release the GIL. Two threads could both observe
an empty registry, both build a complete object, and hand their callers two
different "singletons" — two engines, two session registries — with only the
last-writer stored. Work done through the other went to an object nothing else
in the process could reach.

Fixed with a class-level `threading.RLock` and double-checked locking: the
fast path stays a bare dict lookup with no locking once the singleton exists,
and the second check inside the lock catches the thread that waited. `RLock`
rather than `Lock` deliberately, so re-entrant construction on a single thread
cannot self-deadlock. `test_concurrent_first_callers_get_the_same_instance`
pins it with a two-thread barrier, and asserts on thread liveness so a
deadlock fails the test rather than hanging the suite.

Note this race predates the reviewed range — the original code had it too, and
in a worse form. It is fixed here because f295ca6 restructured exactly this
block, which is what brought it into scope.

---

## Residuals

1. **Round 2 was NOT a dry round.** Both of its findings were real and are
   fixed, but the cycle terminated on the two-round cap, not on a reviewer
   reporting nothing. **400b5aa is therefore unreviewed** — it is a fix commit
   written in response to review, which is precisely the category the standing
   policy says resets the yield curve. A round 3 (`addressed in 400b5aa;
   review`, same thread `01a02d7c-96d0-7cf1-ab14-af07e49df937`) is the
   outstanding work.
2. **Round 2 finding 1 was a defect in code round 1 introduced.** The
   minimal-install job was added in f295ca6 and was broken on arrival. The
   trajectory across the two rounds is therefore *not* decaying: round 1 found
   pre-existing defects, round 2 found a defect in round 1's fix plus a real
   latent race. That is a live cycle, cut short by the cap.
3. **No PostgreSQL round-trip coverage this cycle.** Docker was not running
   locally, so the 14 `tests/test_postgresql_roundtrip.py` tests skipped, as
   the suite is designed to do (skipped with a reason, never faked). CI's
   `postgresql` job runs them for real against a service container; nothing in
   either fix commit touches those paths, but they are unverified locally.
4. **Rejected, still open:** `setup.py` / `pyproject.toml` metadata
   consolidation. Tracked in `TODO.md`.
5. **The coverage action SHA pin needs manual maintenance.** Pinning trades
   automatic patch updates for supply-chain safety; nothing will now tell us
   when `v3` moves.
6. **Both reviewer rounds ran read-only** and could not execute the
   filesystem-backed suite; the reviewer said so explicitly both times. Every
   claim about test outcomes in this log comes from local runs, not from the
   reviewer.
7. **Untouched, by directive:** `scripts/check_style.py` and
   `tests/test_check_style.py` carry pre-existing uncommitted changes from
   other work. Not mine, not staged, not reviewed here. The reviewer confirmed
   it left them alone in both rounds.

## Test status at close

- Style gate: `python scripts/check_style.py templates/ dm_dbcore/ examples/`
  → **0 violations across 20 files**, exit 0.
- Full suite (all extras): **212 passed, 18 skipped**. Skips are the 14
  PostgreSQL round-trip tests (no local server) plus 4 `without_numpy` tests
  that correctly skip where NumPy is installed.
- Minimal install (no numpy, no psycopg): **130 passed, 12 skipped, 0 failed**.
- Suite grew 204 → 212 with all extras present; 10 new tests total across the
  two fix commits (6 in f295ca6, 4 in 400b5aa), minus counting effects from the
  one test that was split.

## Round 3 (sonnet, 2026-08-24 morning) — DRY

Independent review of d65eaf7..HEAD with particular attention to 400b5aa
(the previously unreviewed fix commit). Verified by execution, not
reading: full suite 212/18, numpy/psycopg-free venv 130/12/0, style gate
0/20, concurrency test 5x in isolation. Verdict: 400b5aa is sound
(textbook double-checked locking, registration only after success,
dispose-on-failure inside the lock; numpy markers match the library
paths). NO new defects — the cycle the cap left open is now closed dry.

Two low, non-blocking notes recorded in TODO.md: the pre-existing
`assert database_connection_string is not None` (stripped under -O), and
a debug log when a losing concurrent caller's connection string differs
from the registered singleton's.
