"""Tests for the STYLE_GUIDE gate (scripts/check_style.py).

The gate has twice shipped with resolution bugs -- first missing aliased
`Table as T`, then flagging unrelated `@app.mapped` and missing
`sqlalchemy.orm.declarative_base()`. Both classes of failure are invisible in
normal use: a gate that under-reports looks like a clean repo, and one that
over-reports gets ignored. These cases pin both directions down.

Run:  python -m pytest tests/
"""

import pathlib
import re
import subprocess
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "check_style.py"

COMPLIANT_MODEL = """\
from sqlalchemy import Table
from myproject.db import Base, engine, SCHEMA

class Thing(Base):
    '''A thing.'''
    __table__ = Table("thing", Base.metadata, schema=SCHEMA, autoload_with=engine)
"""

# (source, should_be_flagged, rules that MUST appear)
CASES = [
    # --- must be flagged: real STYLE_GUIDE violations -----------------------
    pytest.param(
        "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n",
        True, {"legacy-import", "legacy-orm"}, id="declarative_base",
    ),
    pytest.param(
        "import sqlalchemy.orm\nBase = sqlalchemy.orm.declarative_base()\n",
        True, {"legacy-orm"}, id="dotted-module-import",
    ),
    pytest.param(
        "from sqlalchemy import orm\nBase = orm.declarative_base()\n",
        True, {"legacy-orm"}, id="submodule-as-symbol",
    ),
    pytest.param(
        "import sqlalchemy.orm as so\nBase = so.declarative_base()\n",
        True, {"legacy-orm"}, id="aliased-module",
    ),
    pytest.param(
        "from sqlalchemy.orm import registry\n"
        "mapper_registry = registry()\n"
        "@mapper_registry.mapped\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n",
        True, {"mapper-registry"}, id="mapper-registry-mapped",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n    __table__ = T('t', Base.metadata)\n",
        True, {"no-reflection", "no-schema"}, id="aliased-Table-missing-kwargs",
    ),
    pytest.param(
        "import sqlalchemy as sa\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n    __table__ = sa.Table('t', Base.metadata)\n",
        True, {"no-reflection", "no-schema"}, id="module-attr-Table-missing-kwargs",
    ),
    pytest.param(
        "from sqlalchemy import Table, Column as C, Integer\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n"
        "    __table__ = Table('t', Base.metadata, schema=None, autoload_with=engine)\n"
        "    id = C(Integer)\n",
        True, {"manual-column"}, id="aliased-manual-Column",
    ),
    pytest.param(
        "from sqlalchemy import *\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n    __table__ = Table('t', Base.metadata)\n",
        True, {"no-reflection", "no-schema"}, id="star-import",
    ),
    pytest.param(
        'URL = "postgresql://user@host/db"\n',
        True, {"psycopg2-url"}, id="bare-postgresql-url",
    ),
    pytest.param(
        'URL = "postgresql+psycopg2://user@host/db"\n',
        True, {"psycopg2-url"}, id="psycopg2-url",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "from x import Base, engine, SCHEMA\n"
        "class M(Base):\n"
        "    __table__ = Table('t', Base.metadata, schema=SCHEMA, autoload_with=engine)\n",
        True, {"no-docstring"}, id="missing-docstring",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "from x import Base, engine, SCHEMA\n"
        "class M(Base):\n    '''d'''\n    __tablename__ = 't'\n",
        True, {"legacy-tablename"}, id="legacy-tablename",
    ),
    pytest.param("def f(:\n", True, {"parse-error"}, id="parse-error-is-a-violation"),

    # --- must NOT be flagged: not SQLAlchemy, or already compliant ----------
    pytest.param(COMPLIANT_MODEL, False, set(), id="compliant-model"),
    pytest.param(
        "from widgets import Table as T\nT('widget')\n",
        False, set(), id="unrelated-Table",
    ),
    pytest.param(
        "from someorm import registry\nr = registry()\n",
        False, set(), id="unrelated-registry",
    ),
    pytest.param(
        "import app\n@app.mapped\nclass Thing:\n    '''d'''\n    x = 1\n",
        False, set(), id="unrelated-mapped-decorator",
    ),
    pytest.param(
        'URL = "postgresql+psycopg://user@host/db"\n',
        False, set(), id="psycopg3-url",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "from x import Base, engine\n"
        "t = Table('join_t', Base.metadata, schema=None, autoload_with=engine)\n",
        False, set(), id="plain-join-table",
    ),
    # Rebinding shadows the import: after `T = widget_factory`, T is not
    # sqlalchemy.Table. The binding maps used to only grow, so this was flagged.
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "T = widget_factory\n"
        "T('widget')\n",
        False, set(), id="alias-reassigned",
    ),
    pytest.param(
        "import sqlalchemy as sa\n"
        "sa = something_else\n"
        "sa.Table('t')\n",
        False, set(), id="module-alias-reassigned",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "def make(Table):\n"
        "    return Table('widget')\n",
        False, set(), id="param-shadows-import",
    ),
]


def run_gate(source: str):
    """Run the gate over `source`; return (exit_code, stdout, rules_reported).

    `rules` is the set of rule ids in the output, e.g. {"no-schema"}. Tests
    assert on those rather than merely on a non-zero exit: any crash also exits
    non-zero, and several fixtures trip more than one rule, so "exited non-zero"
    would pass even if the rule under test had stopped working.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(source)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, str(GATE), path, "--quiet"],
            capture_output=True, text=True,
        )
        rules = set(re.findall(r"\[([a-z0-9-]+)\]", proc.stdout))
        return proc.returncode, proc.stdout, rules
    finally:
        pathlib.Path(path).unlink()


@pytest.mark.parametrize("source,should_flag,expected_rules", CASES)
def test_gate_verdict(source, should_flag, expected_rules):
    code, out, rules = run_gate(source)

    # 0 = clean, 1 = violations found. Anything else is the gate itself
    # failing, which must never be mistaken for a finding.
    assert code in (0, 1), f"gate exited {code}, which is a crash, not a verdict:\n{out}"

    assert bool(code) == should_flag, (
        f"expected {'a violation' if should_flag else 'clean'}, got:\n{out}"
    )

    # The specific rule must fire -- not merely *some* rule.
    missing = set(expected_rules) - rules
    assert not missing, f"expected rule(s) {sorted(missing)}; got {sorted(rules)}:\n{out}"

    if not should_flag:
        assert not rules, f"expected no findings, got {sorted(rules)}:\n{out}"


def test_registry_reassignment_does_not_trigger_decorator_rule():
    """After `mapper_registry = app_thing`, @mapper_registry.mapped is not ours.

    This file still trips `legacy-import` (importing `registry` is itself a
    violation), so it cannot be asserted clean -- the point is narrower: the
    mapper-registry decorator rule must not fire once the name is rebound.
    """
    code, out, rules = run_gate(
        "from sqlalchemy.orm import registry\n"
        "mapper_registry = registry()\n"
        "mapper_registry = app_thing\n"
        "@mapper_registry.mapped\n"
        "class T:\n    '''d'''\n    x = 1\n"
    )
    assert code in (0, 1), out
    assert "mapper-registry" not in rules, f"decorator rule fired on a rebound name:\n{out}"


def test_gate_is_clean_on_its_own_repo():
    """The gate must pass the package and templates it governs."""
    proc = subprocess.run(
        [sys.executable, str(GATE), str(REPO / "dm_dbcore"), str(REPO / "templates")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout


def test_gate_does_not_flag_itself():
    """check_style.py builds its psycopg2 URL prefixes rather than writing them
    as literals, precisely so it does not trip its own rule."""
    code, out, _ = run_gate(GATE.read_text())
    assert code == 0, out
