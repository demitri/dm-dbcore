"""PostgreSQL-specific adapters."""

from .pggeometry import PGPoint, PGPolygon, PGCircle
from .pgcitext import PGCitext

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
    "PGCitext",
    "PGASTCircle",
    "PGASTPolygon",
    "numpy_postgresql",
    "numpy_postgresql_psycopg2",
    "pggeometry",
    "pgcitext",
    "ast_pg_geometry",
]
