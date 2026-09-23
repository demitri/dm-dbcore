# Review log — 2026-09-23

Opus review cycle on the style gate: **a3c1c40..aeddd19**, branch
`fix/templates-and-pg-adapters`. a3c1c40 committed the style-gate work that
the 2026-08-24 log (Residual 7) recorded as pre-existing, uncommitted and
unreviewed: it dropped the `mapper-registry` rule and closed three shadowing
gaps in `_rebound_names`. That residual is closed here.

- **Reviewer:** Opus sub-agent (general-purpose), one session for all four
  rounds, so each round saw its own earlier findings.
- **Stopping:** round 4 was **dry**.
- **Panel:** Opus, then one codex round (at the end of this log), both at
  the owner's request. No sonnet round (see Residuals).

Prompts were the canonical minimal form:

```
Review a3c1c40
Review not only the changes, but make higher level suggestions or improvements if you have any.
addressed in dca4e1f; review
addressed in 8e6c149; review
addressed in 7f0c1a2; review        <- wrong hash, sent before the commit existed
Correction: the hash is aeddd19, not 7f0c1a2. addressed in aeddd19; review
```

The round-4 slip happened because the prompt was sent in parallel with the
commit. The reviewer noticed the bad hash and reviewed aeddd19. In future,
send the round prompt only after the commit returns its hash.

Fix commits: **dca4e1f** (round 1), **8e6c149** (round 2), **aeddd19**
(round 3).

---

## Round 1 (a3c1c40): 5 findings plus 2 higher-level, all real, all fixed in dca4e1f

Each finding was reproduced on scratch files before it was fixed.

1. **Regression: `_unbind` added to the permanent `rebound` set.** A helper's
   `from widgets import Table` disowned a later `from sqlalchemy import
   Table`, so the bad `Table(...)` call was no longer flagged. The parent
   commit had flagged it. Import shadowing of a star import now lives in its
   own order-dependent set (`import_shadowed`), which a later explicit
   SQLAlchemy import or star import clears.
2. **Mixed semantics, and PEP 695 type parameters missed.** The docstring now
   says imports are processed in source order. `class C[Table]` shadowed the
   import but was not recognised, so the gate over-reported.
   `_rebound_names` is now table-driven (`_BINDING_FIELDS` / `_NOT_BINDING`).
3. **The reasoning behind dropping `mapper-registry` was wrong.** "Cannot
   exist without `registry()`" holds only within one file. A model file
   importing its registry from `base.py` passed clean. The rule is back,
   keyed on the class's shape (`@x.mapped` plus `__tablename__` or
   `__table__`) instead of tracking where the registry came from, so it
   also covers the cross-module layout.
4. **Stale `CLAUDE.md:20`.** It became accurate again when the rule
   returned, so no edit was needed.
5. **Redundant test.** Replaced with the cross-module registry case.
- **Higher-level: `db.Base` models skipped every model rule.** `x.Base`
  bases are now accepted, and indirect subclasses are documented as a blind
  spot.
- **Higher-level, rule of two:** this was the fifth round of hand-added
  binding forms. A test now enumerates every `ast` class with a
  `name`/`rest`/`arg` field and fails on any unclassified one.

The CI comment on the Python 3.10 floor gave an outdated reason and was
corrected. The floor still holds, because the gate cannot parse `match`
before 3.10.

## Round 2 (dca4e1f): 5 findings, all real, all fixed in 8e6c149

These were second-order: gaps in the rule reinstated in round 1.

1. `@reg.mapped_as_dataclass(...)` (a called decorator) was missed.
2. The standalone `@mapped_as_dataclass(reg)` was missed.
3. Any `somelib.Base` now counts as a model, which is a false positive.
   **Accepted and documented** as a trade-off: `db.Base` is the common
   form, and model trees rarely subclass another library's `Base`.
   Separately, abstract declarative bases were flagged `no-table`, which is
   now fixed.
4. Nit: the enumeration test's field-name limit is now stated in its
   docstring.
5. Nit: registry-mapped classes now also get the `manual-column` check.

## Round 3 (8e6c149): 2 findings, both real, both in round 2's own fixes, fixed in aeddd19

1. **Under-report.** Abstract bases were exempt from every check, but an
   abstract base is where shared `Column()` / `mapped_column()` declarations
   go. They now skip `no-table` only.
2. **Duplicate report.** A class that was both registry-decorated and a
   `Base` subclass got `manual-column` twice. The two routes are now
   mutually exclusive, and a test counts the occurrences.

## Round 4 (aeddd19): DRY

The reviewer confirmed both round-3 fixes and re-ran every probe from rounds
1 and 2, with no regressions.

**Trajectory:** real regression, then gaps in the fix, then defects in the
fixes of the fix, then dry.

---

## Residuals

1. **The reviewer panel is incomplete.** The standing policy also wants a
   sonnet round. Codex ran one round afterwards (see the end of this log),
   and that round's fix commit has not been reviewed.
2. **The author of the fixes is the orchestrating session.** Every fix was
   verified by execution (probe files plus the suite), and the reviewer
   independently re-ran its probes each round.
3. **Documented blind spots (in the gate's docstring):** import handling
   ignores scope; indirect `Base` subclasses are not checked; any `x.Base`
   counts as a model; a registry-decorated class with neither
   `__tablename__` nor `__table__` is not flagged.

## Test status at close

- Style gate: **0 violations across 20 files**, exit 0.
- Full suite: **227 passed, 18 skipped** (the 14 PostgreSQL round-trip tests
  need a server; the 4 `without_numpy` tests skip where NumPy is installed).

---

## Codex round (a3c1c40..aeddd19): 4 findings, 2 fixed, 2 pushed back

Run at the owner's request, one round only. Dispatched through the
codex-rescue agent with the canonical prompt (`Review a3c1c40..aeddd19` plus
the higher-level line), read-only. Thread `01a0ccdb-c676-7a80-9a6c-f8d4d813a9d1`.
All four findings were reproduced on scratch files.

1. **`@app.mapped` on a class with `__tablename__` is flagged. PUSHED BACK.**
   Real, but this is the deliberate round-1 trade-off. Tracking where a
   registry came from is what failed before, and it cannot see a registry
   imported from another file. A class that sets `__tablename__` or
   `__table__` under a `.mapped` decorator is SQLAlchemy's declarative
   signature. Now listed explicitly as an accepted over-report in the
   gate's docstring.
2. **An aliased `mapped_as_dataclass as madc` escaped the gate. FIXED.**
   The decorator check now resolves names through `sa_names`.
3. **The PEP 695 test encodes the wrong scope semantics. PUSHED BACK, test
   reworded.** Codex is right that type parameters are class-scoped. But
   the gate is flat by documented design; function parameters behave the
   same way. The test was renamed and its docstring now pins the policy
   instead of claiming anything about Python.
4. **`from widgets import *` left SQLAlchemy names resolved: a false
   positive. FIXED.** A non-SQLAlchemy star import now drops every tracked
   SQLAlchemy binding until SQLAlchemy is imported again (under-report).
   Documented as a blind spot.
- **Higher-level: a scope-aware symbol resolver.** Real, but a redesign.
  Added to TODO.md.

**Residual:** the fix commit for this round has not been reviewed. The
owner asked for one codex round; a follow-up would be
`addressed in <hash>; review --resume`.
