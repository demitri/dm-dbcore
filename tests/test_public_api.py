"""The importable surface of the package.

Every name a README or a downstream project imports is imported here. These are
cheap tests that catch one specific failure: a name listed in ``__all__`` (or
in the README) that no longer resolves. That breaks callers at import time and
is invisible to every test that imports the module directly.
"""

import importlib

import pytest

import dm_dbcore


def test_all_names_resolve():
    for name in dm_dbcore.__all__:
        assert hasattr(dm_dbcore, name), f"__all__ lists {name!r} but the package has no such attribute"


def test_documented_top_level_imports():
    """The imports the README's Quick Start tells people to write."""
    from dm_dbcore import (  # noqa: F401
        DatabaseConnection,
        DBTYPE_MYSQL,
        DBTYPE_POSTGRESQL,
        DBTYPE_SQLITE,
        MetadataCache,
        session_scope,
    )


def test_database_type_constants_are_the_dialect_names():
    """These constants are compared against SQLAlchemy URL prefixes, so the
    exact strings are part of the contract, not an implementation detail."""
    assert dm_dbcore.DBTYPE_POSTGRESQL == "postgresql"
    assert dm_dbcore.DBTYPE_MYSQL == "mysql"
    assert dm_dbcore.DBTYPE_SQLITE == "sqlite"


def test_version_is_exposed():
    assert isinstance(dm_dbcore.__version__, str)
    assert dm_dbcore.__version__


def test_adapter_names_resolve():
    from dm_dbcore.adapters import PGCIText, PGCircle, PGPoint, PGPolygon, PGXML  # noqa: F401


def test_mysql_utility_names_resolve():
    from dm_dbcore.mysql import (  # noqa: F401
        read_connection_options_from_my_cnf,
        read_password_from_my_cnf,
    )


@pytest.mark.parametrize(
    "module",
    [
        "dm_dbcore",
        "dm_dbcore.DatabaseConnection",
        "dm_dbcore.adapters",
        "dm_dbcore.adapters.postgresql",
        "dm_dbcore.adapters.postgresql.pggeometry",
        "dm_dbcore.adapters.postgresql.pgcitext",
        "dm_dbcore.adapters.postgresql.pgxml",
        "dm_dbcore.adapters.sqlite",
        "dm_dbcore.adapters.sqlite.numpy_sqlite",
        "dm_dbcore.mysql",
        "dm_dbcore.mysql.mysql_utils",
    ],
)
def test_every_module_imports(module):
    """Import side effects (adapter registration) must not raise on import."""
    assert importlib.import_module(module) is not None


@pytest.mark.parametrize(
    "module",
    [
        "dm_dbcore.adapters.postgresql.numpy_postgresql",
        "dm_dbcore.adapters.postgresql.ast_pg_geometry",
    ],
)
def test_optional_dependency_modules_import(module):
    """These guard optional imports (psycopg, numpy, cornish) and must import
    cleanly whether or not the optional package is installed."""
    assert importlib.import_module(module) is not None


@pytest.mark.parametrize("name", ["PGASTCircle", "PGASTPolygon"])
def test_astronomy_names_are_always_importable(name):
    """They resolve to None when cornish is absent rather than failing the import.

    A downstream `from dm_dbcore.adapters import PGASTCircle` must not explode
    just because the astronomy extra is not installed -- but a caller that then
    uses the name gets a clear failure rather than a wrong type.
    """
    import dm_dbcore.adapters as adapters

    assert hasattr(adapters, name)


def test_every_public_module_has_a_docstring():
    """Module docstrings are the first thing help() and an IDE show."""
    modules = [
        "dm_dbcore",
        "dm_dbcore.DatabaseConnection",
        "dm_dbcore.adapters",
        "dm_dbcore.adapters.postgresql",
        "dm_dbcore.adapters.postgresql.pggeometry",
        "dm_dbcore.adapters.postgresql.pgcitext",
        "dm_dbcore.adapters.postgresql.pgxml",
        "dm_dbcore.adapters.postgresql.numpy_postgresql",
        "dm_dbcore.adapters.postgresql.ast_pg_geometry",
        "dm_dbcore.adapters.sqlite",
        "dm_dbcore.adapters.sqlite.numpy_sqlite",
        "dm_dbcore.mysql",
        "dm_dbcore.mysql.mysql_utils",
    ]
    missing = [m for m in modules if not (importlib.import_module(m).__doc__ or "").strip()]
    assert not missing, f"modules without a docstring: {missing}"
