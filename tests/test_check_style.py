"""Tests for the STYLE_GUIDE gate (scripts/check_style.py).

The gate has twice shipped with resolution bugs -- first missing aliased
`Table as T`, then flagging unrelated `@app.mapped` and missing
`sqlalchemy.orm.declarative_base()`. Both classes of failure are invisible in
normal use: a gate that under-reports looks like a clean repo, and one that
over-reports gets ignored. These cases pin both directions down.

Run:  python -m pytest tests/
"""

import pathlib
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

# (id, source, should_be_flagged)
CASES = [
    # --- must be flagged: real STYLE_GUIDE violations -----------------------
    pytest.param(
        "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n",
        True, id="declarative_base",
    ),
    pytest.param(
        "import sqlalchemy.orm\nBase = sqlalchemy.orm.declarative_base()\n",
        True, id="dotted-module-import",
    ),
    pytest.param(
        "from sqlalchemy import orm\nBase = orm.declarative_base()\n",
        True, id="submodule-as-symbol",
    ),
    pytest.param(
        "import sqlalchemy.orm as so\nBase = so.declarative_base()\n",
        True, id="aliased-module",
    ),
    pytest.param(
        "from sqlalchemy.orm import registry\n"
        "mapper_registry = registry()\n"
        "@mapper_registry.mapped\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n",
        True, id="mapper-registry-mapped",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n    __table__ = T('t', Base.metadata)\n",
        True, id="aliased-Table-missing-kwargs",
    ),
    pytest.param(
        "import sqlalchemy as sa\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n    __table__ = sa.Table('t', Base.metadata)\n",
        True, id="module-attr-Table-missing-kwargs",
    ),
    pytest.param(
        "from sqlalchemy import Table, Column as C, Integer\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n"
        "    __table__ = Table('t', Base.metadata, schema=None, autoload_with=engine)\n"
        "    id = C(Integer)\n",
        True, id="aliased-manual-Column",
    ),
    pytest.param(
        "from sqlalchemy import *\n"
        "from x import Base, engine\n"
        "class M(Base):\n    '''d'''\n    __table__ = Table('t', Base.metadata)\n",
        True, id="star-import",
    ),
    pytest.param(
        'URL = "postgresql://user@host/db"\n', True, id="bare-postgresql-url",
    ),
    pytest.param(
        'URL = "postgresql+psycopg2://user@host/db"\n', True, id="psycopg2-url",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "from x import Base, engine, SCHEMA\n"
        "class M(Base):\n"
        "    __table__ = Table('t', Base.metadata, schema=SCHEMA, autoload_with=engine)\n",
        True, id="missing-docstring",
    ),
    pytest.param("def f(:\n", True, id="parse-error-is-a-violation"),

    # --- must NOT be flagged: not SQLAlchemy, or already compliant ----------
    pytest.param(COMPLIANT_MODEL, False, id="compliant-model"),
    pytest.param(
        "from widgets import Table as T\nT('widget')\n",
        False, id="unrelated-Table",
    ),
    pytest.param(
        "from someorm import registry\nr = registry()\n",
        False, id="unrelated-registry",
    ),
    pytest.param(
        "import app\n@app.mapped\nclass Thing:\n    '''d'''\n    x = 1\n",
        False, id="unrelated-mapped-decorator",
    ),
    pytest.param(
        'URL = "postgresql+psycopg://user@host/db"\n', False, id="psycopg3-url",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "from x import Base, engine\n"
        "t = Table('join_t', Base.metadata, schema=None, autoload_with=engine)\n",
        False, id="plain-join-table",
    ),
]


def run_gate(source: str):
    """Run the gate over `source`; return (exit_code, stdout)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(source)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, str(GATE), path, "--quiet"],
            capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout
    finally:
        pathlib.Path(path).unlink()


@pytest.mark.parametrize("source,should_flag", CASES)
def test_gate_verdict(source, should_flag):
    code, out = run_gate(source)
    flagged = bool(code)
    assert flagged == should_flag, (
        f"expected {'a violation' if should_flag else 'clean'}, got:\n{out}"
    )


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
    code, out = run_gate(GATE.read_text())
    assert code == 0, out
