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
        True, {"legacy-import", "legacy-orm", "mapper-registry"}, id="mapper-registry-mapped",
    ),
    # The realistic layout: the registry lives in base.py and is imported, so
    # this file never mentions registry() -- only the decorator gives it away.
    pytest.param(
        "from .base import mapper_registry\n"
        "@mapper_registry.mapped\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n",
        True, {"mapper-registry"}, id="mapper-registry-imported-from-base",
    ),
    pytest.param(
        "from .base import reg\n"
        "@reg.mapped_as_dataclass\n"
        "class T:\n    '''d'''\n    __table__ = t\n",
        True, {"mapper-registry"}, id="mapped-as-dataclass",
    ),
    pytest.param(
        "from .base import reg\n"
        "@reg.mapped_as_dataclass(unsafe_hash=True)\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n",
        True, {"mapper-registry"}, id="mapped-as-dataclass-called",
    ),
    pytest.param(
        "from sqlalchemy.orm import mapped_as_dataclass\nfrom .base import reg\n"
        "@mapped_as_dataclass(reg)\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n",
        True, {"mapper-registry"}, id="standalone-mapped-as-dataclass",
    ),
    pytest.param(
        "from sqlalchemy import Column\nfrom .base import reg\n"
        "@reg.mapped\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n    x = Column()\n",
        True, {"mapper-registry", "manual-column"}, id="registry-mapped-manual-column",
    ),
    pytest.param(
        "from app import db\n"
        "class Mixin(db.Base):\n    '''d'''\n    __abstract__ = True\n",
        False, set(), id="abstract-base-is-not-a-model",
    ),
    # ...but an abstract base is where shared columns get declared, so the
    # column rule still applies to it.
    pytest.param(
        "from sqlalchemy import Column, DateTime\nfrom app import db\n"
        "class Stamped(db.Base):\n    '''d'''\n    __abstract__ = True\n"
        "    created = Column(DateTime)\n",
        True, {"manual-column"}, id="abstract-base-manual-column",
    ),
    pytest.param(
        "from sqlalchemy.orm import mapped_column\nfrom app import db\n"
        "class Stamped(db.Base):\n    '''d'''\n    __abstract__: bool = True\n"
        "    created = mapped_column()\n",
        True, {"manual-column"}, id="annotated-abstract-base-manual-column",
    ),
    # A model reached through a module attribute is still a model.
    pytest.param(
        "import sqlalchemy as sa\nfrom app import db\n"
        "class T(db.Base):\n    '''d'''\n    x = sa.Column(sa.Integer)\n",
        True, {"manual-column", "no-table"}, id="attribute-base-is-model",
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
    # Re-importing over an alias rebinds it.
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "from widgets import Table as T\n"
        "T('widget')\n",
        False, set(), id="reimport-shadows-alias",
    ),
    pytest.param(
        "import sqlalchemy as sa\nimport widgets as sa\nsa.Table('t')\n",
        False, set(), id="reimport-module-alias",
    ),
    # Other binding forms.
    pytest.param(
        "from sqlalchemy import Table as T\nT: object = widget_factory\nT('widget')\n",
        False, set(), id="annassign-shadows-alias",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\nT, U = widget_factory, 1\nT('widget')\n",
        False, set(), id="tuple-unpack-shadows-alias",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "def Table(name):\n    return name\n"
        "Table('widget')\n",
        False, set(), id="def-shadows-import",
    ),
    pytest.param(
        "from sqlalchemy import Table\n"
        "class Table:\n    '''mine'''\n    x = 1\n",
        False, set(), id="class-shadows-import",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\nfor T in items:\n    T('widget')\n",
        False, set(), id="for-target-shadows-alias",
    ),
    # A star import does not make every bare name SQLAlchemy's forever.
    pytest.param(
        "from sqlalchemy import *\nTable = widget_factory\nTable('widget')\n",
        False, set(), id="star-import-then-rebound",
    ),
    # Binding forms that used to need a visitor each.
    pytest.param(
        "from sqlalchemy import Table as T\nwith ctx() as T:\n    T('widget')\n",
        False, set(), id="with-as-shadows-alias",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "try:\n    pass\nexcept Exception as T:\n    T('widget')\n",
        False, set(), id="except-as-shadows-alias",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\nxs = [T('w') for T in items]\n",
        False, set(), id="comprehension-target-shadows-alias",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\nif (T := widget_factory):\n    T('widget')\n",
        False, set(), id="walrus-shadows-alias",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "match obj:\n    case T:\n        T('widget')\n",
        False, set(), id="match-capture-shadows-alias",
    ),
    # A later non-SQLAlchemy import takes the name back from a star import.
    pytest.param(
        "from sqlalchemy import *\nfrom widgets import Table\nTable('widget')\n",
        False, set(), id="star-import-then-reimported",
    ),
    # Lambda parameters are ast.arg, not Name(Store).
    pytest.param(
        "from sqlalchemy import Table\nf = lambda Table: Table('widget')\n",
        False, set(), id="lambda-param-shadows-import",
    ),
    pytest.param(
        "from sqlalchemy import Table as T\n"
        "match obj:\n    case {**T}:\n        T('widget')\n",
        False, set(), id="match-mapping-rest-shadows-alias",
    ),
    # A non-SQLAlchemy import in one function must not permanently disown the
    # name: a later explicit SQLAlchemy import takes it back.
    pytest.param(
        "def helper():\n    from widgets import Table\n    return Table\n"
        "from sqlalchemy import Table\nTable('t', md)\n",
        True, {"no-reflection", "no-schema"}, id="sqlalchemy-import-reclaims-name",
    ),
    # ...and so does a later star import.
    pytest.param(
        "from widgets import Table\nfrom sqlalchemy import *\nTable('t', md)\n",
        True, {"no-reflection", "no-schema"}, id="star-import-reclaims-name",
    ),
    # An unknown star import may rebind anything: stop resolving.
    pytest.param(
        "from sqlalchemy import Table\nfrom widgets import *\nTable('widget')\n",
        False, set(), id="foreign-star-import-disowns-names",
    ),
    pytest.param(
        "from widgets import *\nfrom sqlalchemy import Table\nTable('t', md)\n",
        True, {"no-reflection", "no-schema"}, id="sqlalchemy-import-after-foreign-star",
    ),
    pytest.param(
        "from sqlalchemy.orm import mapped_as_dataclass as madc\nfrom .base import reg\n"
        "@madc(reg)\n"
        "class T:\n    '''d'''\n    __tablename__ = 't'\n",
        True, {"mapper-registry"}, id="aliased-standalone-mapped-as-dataclass",
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


def test_manual_column_reported_once_on_registry_mapped_base_subclass():
    """A class both registry-decorated and a Base subclass has two routes to
    the column check; the finding must appear once, or the count is wrong."""
    code, out, rules = run_gate(
        "from sqlalchemy import Column\nfrom .base import Base, reg\n"
        "@reg.mapped\n"
        "class T(Base):\n    \'\'\'d\'\'\'\n    __tablename__ = 't'\n    x = Column()\n"
    )
    assert out.count("[manual-column]") == 1, f"expected one manual-column finding:\n{out}"


def test_every_bare_identifier_binding_form_is_classified():
    """Every ast node type that can carry a bound identifier is accounted for.

    _rebound_names grew one binding form per review round until it became
    table-driven. This enumerates the ast classes of the running Python that
    have a `name`, `rest` or `arg` field and requires each to be either handled
    (_BINDING_FIELDS) or deliberately excluded (_NOT_BINDING) -- so a binding
    form added by a future Python fails here instead of in review.

    Blind spot: only those three field names are searched. A future binding
    form stored under another field (`names`, `target`, ...) passes unnoticed.
    """
    sys.path.insert(0, str(GATE.parent))
    try:
        import check_style
    finally:
        sys.path.remove(str(GATE.parent))
    import ast

    candidates = {
        name
        for name, cls in vars(ast).items()
        if isinstance(cls, type)
        and issubclass(cls, ast.AST)
        and {"name", "rest", "arg"} & set(getattr(cls, "_fields", ()))
    }
    classified = set(check_style._BINDING_FIELDS) | set(check_style._NOT_BINDING)
    unclassified = candidates - classified
    assert not unclassified, (
        f"ast node types not classified as binding or non-binding: {sorted(unclassified)}"
    )


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax")
@pytest.mark.parametrize("header", ["class C[Table]:", "class C[*Table]:", "class C[**Table]:"])
def test_type_parameters_disown_the_name_file_wide(header):
    """Python scopes a type parameter to its class; the gate deliberately
    does not. Like a function parameter, a type parameter named `Table` makes
    `Table` untrusted everywhere in the file (see _rebound_names). This pins
    that flat-scope policy -- it is not a claim about Python's semantics."""
    code, out, rules = run_gate(
        f"from sqlalchemy import Table\n{header}\n    pass\nTable('widget')\n"
    )
    assert code == 0 and not rules, f"a type parameter did not disown the name:\n{out}"


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
