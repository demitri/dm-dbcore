#!/usr/bin/env python
"""
Style gate for dm-dbcore model and connection modules.

Enforces the mechanically-decidable rules in STYLE_GUIDE.md. Run it against the
templates, or against any project's model/connection modules:

    python scripts/check_style.py templates/
    python scripts/check_style.py ../myproject/source/myproject/db/

Exit status is 0 when clean, 1 when any violation is found. Parse errors are
reported as violations rather than skipped -- a file that cannot be parsed has
not been checked, and silently passing it would defeat the gate.

WHAT THIS GATE CANNOT SEE (standing human-review duties):
  - Whether a relationship is semantically correct (right target, right
    direction, sensible lazy= strategy).
  - Whether the reflected table actually exists in the database. Only a real
    connection proves that; see scripts/db_connection_test.py, and run each
    template's own main().
  - Whether `schema=` holds the RIGHT schema -- only that it was passed.
  - Connection URLs that are assembled at runtime rather than written as
    literals (f-strings, URL.create(), os.environ values). Only literal strings
    are checked, so a psycopg2 URL built from parts will pass.
  - Calls whose callee is neither a plain name nor an attribute -- e.g.
    `factories['Table'](...)` or a Table returned from a helper function.
    `import X as Y` aliases ARE resolved, but deciding the rest would need full
    symbol resolution, which this gate does not do.
  - Scope. Any name the module binds itself -- anywhere, by any means -- is
    treated as not-SQLAlchemy's everywhere in that file. So a module that does
    `Table = something` in one function and uses the real `Table` elsewhere
    goes unchecked in both. Likewise `T = T("t", md)`: the right-hand side is
    genuinely SQLAlchemy's Table, but `T` is a bound name, so the call is
    skipped. This under-reports rather than over-reporting, deliberately -- a
    missed violation costs a review comment; a gate that cries wolf gets turned
    off. Real model files do not rebind `Table`.
    Imports are the exception: they are processed in source order (still
    ignoring scope), so `from widgets import Table` shadows a preceding
    `from sqlalchemy import *` but a later `from sqlalchemy import Table`
    takes the name back.
  - Model classes that inherit from Base indirectly. A class counts as a model
    only if it names `Base` (or `x.Base`) directly among its bases, so
    `class Mixin(Base)` / `class T(Mixin)` checks Mixin but not T.
  - Where a registry came from. `@x.mapped` is reported only on a class that
    also sets `__tablename__` or `__table__`; a registry imported from another
    module is caught that way, but a decorated class with neither attribute is
    not.
  - Code inside strings, docstrings, or comments (deliberate: examples in prose
    are not executed).
  - Whether a docstring is accurate, only that model classes have one.
"""

import argparse
import ast
import pathlib
import sys
from typing import Iterator, List, NamedTuple

# STYLE_GUIDE.md section 2: legacy declarative APIs.
LEGACY_ORM_NAMES = {
    "declarative_base": "STYLE_GUIDE 2: use `class Base(DeclarativeBase)`, not declarative_base()",
    "registry": "STYLE_GUIDE 2: mapper registries are legacy; inherit from Base",
}

# STYLE_GUIDE.md section 1: psycopg2 is deprecated for new projects. A bare
# `postgresql://` silently resolves to psycopg2, so it is flagged too.
#
# These prefixes are assembled rather than written as literals so that this
# module does not trip its own rule. Do not "simplify" them back into plain
# strings -- running the gate over its own source would then report two
# violations that are not violations.
_PG = "postgresql"
BAD_URL_PREFIXES = {
    f"{_PG}://": (
        f"STYLE_GUIDE 1: bare `{_PG}://` resolves to psycopg2; "
        f"use `{_PG}+psycopg://` (psycopg v3)"
    ),
    f"{_PG}+psycopg2://": (
        "STYLE_GUIDE 1: psycopg2 is deprecated for new projects; "
        f"use `{_PG}+psycopg://` (psycopg v3)"
    ),
}


class Violation(NamedTuple):
    path: pathlib.Path
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


def _is_sqlalchemy_module(module: str) -> bool:
    """True for 'sqlalchemy' and any submodule of it."""
    return bool(module) and (module == "sqlalchemy" or module.startswith("sqlalchemy."))


# AST node types that bind a bare identifier (a str field, not a Name node),
# and which field holds it. Keyed by class name so that forms added in later
# Pythons (PEP 695 type parameters, 3.12) are simply absent on older ones.
# tests/test_check_style.py enumerates every ast class with a `name`, `rest`
# or `arg` field and fails unless it is listed here or in _NOT_BINDING, so a
# new binding form surfaces as a test failure rather than a review finding.
_BINDING_FIELDS = {
    "arg": "arg",  # def and lambda parameters
    "ExceptHandler": "name",  # except E as e
    "MatchAs": "name",  # case Foo() as bar / case bar
    "MatchStar": "name",  # case [*rest]
    "MatchMapping": "rest",  # case {**rest}
    "FunctionDef": "name",
    "AsyncFunctionDef": "name",
    "ClassDef": "name",
    "TypeVar": "name",  # class C[T]
    "ParamSpec": "name",  # class C[**P]
    "TypeVarTuple": "name",  # class C[*Ts]
}

# Node types with such a field that are deliberately not treated as bindings.
_NOT_BINDING = {
    "alias": "imports are order-dependent; handled by visit_Import/visit_ImportFrom",
    "keyword": "a call's keyword argument name, not a binding",
    "TypeAlias": "`type X = ...` binds through a Name(Store), caught directly",
}


def _rebound_names(tree: ast.AST) -> set:
    """Every name the module binds to something of its own.

    One pass instead of a visitor per binding form. Enumerating the forms as
    visitors was a losing game: four review rounds, four more forms each time.
    Instead: any Name in a Store context, plus the bare-identifier forms in
    _BINDING_FIELDS, is treated as not-SQLAlchemy's. Imports are not included
    -- see visit_ImportFrom.

    This is deliberately conservative and flat. It ignores scope, so a name
    rebound anywhere is untrusted everywhere, and it errs toward NOT checking a
    call rather than wrongly flagging one. Under-reporting is the safe
    direction: a missed violation costs one review comment, while a gate that
    cries wolf gets switched off.
    """
    names = set()
    for node in ast.walk(tree):
        # Covers Assign, AnnAssign, AugAssign, For, With-as, walrus,
        # comprehension targets, tuple/list unpacking, starred targets, `type`
        # aliases -- anything that binds a Name.
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
            continue
        field = _BINDING_FIELDS.get(type(node).__name__)
        if field and getattr(node, field):
            names.add(getattr(node, field))
    return names


def _assigns_name(stmt: ast.stmt, name: str) -> bool:
    if isinstance(stmt, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets)
    if isinstance(stmt, ast.AnnAssign):
        return isinstance(stmt.target, ast.Name) and stmt.target.id == name
    return False


class StyleChecker(ast.NodeVisitor):
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.violations: List[Violation] = []
        # Local name -> canonical SQLAlchemy name, for `from sqlalchemy import
        # Table as T`. Without this, T(...) would not match "Table" and the
        # call would silently escape the Table checks.
        #
        # Only names imported FROM sqlalchemy are recorded. Tracking every
        # module's aliases would flag `from widgets import Table as T` as a
        # malformed SQLAlchemy table -- a false positive that trains people to
        # ignore the gate.
        self.sa_names: dict = {}
        # Local module alias -> module, for `import sqlalchemy as sa`, so that
        # sa.Table(...) resolves too.
        self.sa_modules: dict = {}
        # Set by `from sqlalchemy import *`, after which any bare name may be
        # a SQLAlchemy export and we fall back to matching on the name alone.
        self.sa_star = False
        # Names this module binds itself, from a pre-pass -- see
        # _rebound_names(). A name in here is never resolved as SQLAlchemy's.
        self.rebound: set = set()
        # Names a non-SQLAlchemy import has taken since the last
        # `from sqlalchemy import *`. Consulted only by the star fallback:
        # unlike `rebound`, this is order-dependent, so a later explicit
        # SQLAlchemy import (or another star import) can take the name back.
        self.import_shadowed: set = set()

    def report(self, node: ast.AST, rule: str, message: str) -> None:
        self.violations.append(
            Violation(self.path, getattr(node, "lineno", 0), rule, message)
        )

    # -- imports -------------------------------------------------------------

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not _is_sqlalchemy_module(node.module):
            # Not SQLAlchemy: none of these rules apply. Importing over an
            # existing binding rebinds it, though -- after
            # `from widgets import Table`, Table is widgets', not ours. That
            # matters even with no prior binding, because a preceding
            # `from sqlalchemy import *` would otherwise claim the bare name.
            for alias in node.names:
                if alias.name != "*":
                    self._unbind(alias.asname or alias.name)
            self.generic_visit(node)
            return

        if node.module == "sqlalchemy.ext.declarative":
            self.report(
                node,
                "legacy-import",
                "STYLE_GUIDE 2: `sqlalchemy.ext.declarative` is SQLAlchemy 1.x",
            )

        for alias in node.names:
            if alias.name == "*":
                self.sa_star = True
                self.import_shadowed.clear()
                continue
            if alias.name in LEGACY_ORM_NAMES:
                self.report(node, "legacy-import", LEGACY_ORM_NAMES[alias.name])
            local = alias.asname or alias.name
            self.sa_names[local] = alias.name
            self.import_shadowed.discard(local)
            # The imported name may itself be a submodule, as in
            # `from sqlalchemy import orm` -> orm.declarative_base(). Record it
            # as a module too so attribute calls through it resolve.
            self.sa_modules[local] = f"{node.module}.{alias.name}"

        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if not _is_sqlalchemy_module(alias.name):
                # Rebinds the local name away from SQLAlchemy.
                self._unbind(alias.asname or alias.name.split(".")[0])
                continue
            if alias.asname:
                # `import sqlalchemy.orm as so` binds "so".
                self.sa_modules[alias.asname] = alias.name
            else:
                # `import sqlalchemy.orm` binds the ROOT name "sqlalchemy", not
                # "sqlalchemy.orm". Keying by the full dotted path meant
                # sqlalchemy.orm.declarative_base() resolved to nothing.
                root = alias.name.split(".")[0]
                self.sa_modules[root] = root
        self.generic_visit(node)

    def _unbind(self, name: str) -> None:
        """Forget a SQLAlchemy binding whose local name a non-SQLAlchemy
        import has taken, so that a `from sqlalchemy import *` cannot go on
        claiming it either."""
        self.sa_names.pop(name, None)
        self.sa_modules.pop(name, None)
        self.import_shadowed.add(name)

    def _is_model_class(self, node: ast.ClassDef) -> bool:
        """A model class inherits from Base (STYLE_GUIDE 2), as `Base` or
        through a module, as in `db.Base`."""
        return any(
            (isinstance(base, ast.Name) and base.id == "Base")
            or (isinstance(base, ast.Attribute) and base.attr == "Base")
            for base in node.bases
        )

    @staticmethod
    def _is_registry_mapped_class(node: ast.ClassDef) -> bool:
        """`@x.mapped` on a class that sets `__tablename__` or `__table__`.

        No attempt is made to prove x is a SQLAlchemy registry -- that needed
        provenance tracking that broke across review rounds, and cannot see a
        registry imported from another module anyway. The table attribute is
        what makes the decorator SQLAlchemy's, and an unrelated `@app.mapped`
        on a class without one is left alone.
        """
        decorated = any(
            isinstance(d, ast.Attribute) and d.attr in ("mapped", "mapped_as_dataclass")
            for d in node.decorator_list
        )
        return decorated and any(
            _assigns_name(s, "__tablename__") or _assigns_name(s, "__table__")
            for s in node.body
        )

    def _resolve_call(self, node: ast.Call):
        """Return the canonical SQLAlchemy name this call targets, else None.

        Resolves `T(...)` from `from sqlalchemy import Table as T`, and
        `sa.Table(...)` from `import sqlalchemy as sa`. Returns None for calls
        that are not SQLAlchemy, so unrelated code is never flagged.
        """
        func = node.func

        if isinstance(func, ast.Name):
            if func.id in self.rebound:
                # The module binds this name itself, so it is not SQLAlchemy's.
                return None
            if func.id in self.sa_names:
                return self.sa_names[func.id]
            if self.sa_star and func.id not in self.import_shadowed:
                # `from sqlalchemy import *` -- match on the bare name.
                return func.id
            return None

        if isinstance(func, ast.Attribute):
            # sa.Table(...) / sqlalchemy.orm.registry()
            root = func.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if (
                isinstance(root, ast.Name)
                and root.id not in self.rebound
                and root.id in self.sa_modules
            ):
                return func.attr
            return None

        # Any other callee shape (subscript, call, lambda) -- see the blind
        # spots in this module's docstring.
        return None

    # -- calls ---------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = self._resolve_call(node)

        if name in LEGACY_ORM_NAMES:
            self.report(node, "legacy-orm", LEGACY_ORM_NAMES[name])

        if name == "Table":
            self._check_table_call(node)

        self.generic_visit(node)

    def _check_table_call(self, node: ast.Call) -> None:
        kwargs = {kw.arg for kw in node.keywords if kw.arg}

        if "autoload_with" not in kwargs:
            self.report(
                node,
                "no-reflection",
                "STYLE_GUIDE 3: Table(...) must reflect via `autoload_with=engine`",
            )

        # The schema= kwarg must be present. Its value may legitimately be None
        # (SQLite and MySQL have no schemas), but it must be stated, not omitted
        # -- dm-dbcore clears the PostgreSQL search_path, so an omitted schema
        # silently resolves to nothing.
        if "schema" not in kwargs:
            self.report(
                node,
                "no-schema",
                "STYLE_GUIDE 3: Table(...) must pass `schema=` explicitly "
                "(use schema=None for SQLite/MySQL)",
            )

        for kw in node.keywords:
            if kw.arg == "autoload":
                self.report(
                    node,
                    "legacy-autoload",
                    "STYLE_GUIDE 3: `autoload=` was removed in SQLAlchemy 2.0; "
                    "use `autoload_with=engine`",
                )

    # -- classes -------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._is_registry_mapped_class(node):
            self.report(
                node,
                "mapper-registry",
                "STYLE_GUIDE 2: `@mapper_registry.mapped` is legacy; "
                "inherit from Base instead",
            )

        if not self._is_model_class(node):
            self.generic_visit(node)
            return

        self._check_model_class(node)
        self.generic_visit(node)

    def _check_model_class(self, node: ast.ClassDef) -> None:
        has_table = any(_assigns_name(s, "__table__") for s in node.body)
        has_tablename = any(_assigns_name(s, "__tablename__") for s in node.body)

        if has_tablename:
            self.report(
                node,
                "legacy-tablename",
                f"STYLE_GUIDE 3: `{node.name}` uses __tablename__; "
                "use `__table__ = Table(..., autoload_with=engine)`",
            )
        elif not has_table:
            self.report(
                node,
                "no-table",
                f"STYLE_GUIDE 3: `{node.name}` defines no `__table__` reflection",
            )

        for stmt in node.body:
            self._check_no_manual_columns(node, stmt)

        if not ast.get_docstring(node):
            self.report(
                node,
                "no-docstring",
                f"STYLE_GUIDE 3: model class `{node.name}` needs a one-line docstring",
            )

    def _check_no_manual_columns(self, cls: ast.ClassDef, stmt: ast.stmt) -> None:
        """Columns come from reflection; declaring them duplicates the schema."""
        value = getattr(stmt, "value", None)
        if not isinstance(value, ast.Call):
            return
        name = self._resolve_call(value)
        if name in ("Column", "mapped_column"):
            self.report(
                stmt,
                "manual-column",
                f"STYLE_GUIDE 3: `{cls.name}` declares a column manually; "
                "reflection supplies all columns",
            )

    # -- connection strings --------------------------------------------------

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            for prefix, message in BAD_URL_PREFIXES.items():
                if node.value.startswith(prefix):
                    self.report(node, "psycopg2-url", message)
        self.generic_visit(node)


def check_file(path: pathlib.Path) -> List[Violation]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        # Do not skip: an unparseable file is unchecked, which is a failure.
        return [
            Violation(path, exc.lineno or 0, "parse-error", f"cannot parse: {exc.msg}")
        ]

    checker = StyleChecker(path)
    # Pre-pass: learn which names the module binds itself, before deciding
    # which calls are SQLAlchemy's.
    checker.rebound = _rebound_names(tree)
    checker.visit(tree)
    return checker.violations


def iter_python_files(targets: List[str]) -> Iterator[pathlib.Path]:
    for target in targets:
        p = pathlib.Path(target)
        if p.is_dir():
            yield from sorted(p.rglob("*.py"))
        elif p.suffix == ".py":
            yield p
        else:
            raise SystemExit(f"not a Python file or directory: {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", help="files or directories to check")
    parser.add_argument(
        "--quiet", action="store_true", help="only print violations, not the summary"
    )
    args = parser.parse_args()

    violations: List[Violation] = []
    checked = 0
    for path in iter_python_files(args.targets):
        checked += 1
        violations.extend(check_file(path))

    for v in sorted(violations, key=lambda v: (str(v.path), v.line)):
        print(v)

    if not args.quiet:
        by_rule: dict = {}
        for v in violations:
            by_rule[v.rule] = by_rule.get(v.rule, 0) + 1
        print(f"\n{checked} file(s) checked, {len(violations)} violation(s).")
        for rule, count in sorted(by_rule.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4d}  {rule}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
