"""PostgreSQL-specific adapters."""

from .pggeometry import PGPoint, PGPolygon, PGCircle
from .pgcitext import PGCIText
from .pgxml import PGXML

try:
    from .ast_pg_geometry import PGASTCircle, PGASTPolygon
    _ASTRONOMY_AVAILABLE = True
except ImportError:
    _ASTRONOMY_AVAILABLE = False
    PGASTCircle = None
    PGASTPolygon = None

__all__ = [
    "PGPoint",
    "PGPolygon",
    "PGCircle",
    "PGCIText",
    "PGXML",
    "PGASTCircle",
    "PGASTPolygon",
    "numpy_postgresql",
    "numpy_postgresql_psycopg2",
    "pggeometry",
    "pgcitext",
    "pgxml",
    "ast_pg_geometry",
]
