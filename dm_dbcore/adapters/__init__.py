"""
Database adapters for custom data types.

This module provides SQLAlchemy adapters for:
- NumPy arrays (PostgreSQL and SQLite)
- PostgreSQL geometric types (Point, Polygon, Circle)

Available adapters:
- PGPoint, PGPolygon: Standard PostgreSQL geometric types
- PGASTCircle, PGASTPolygon: Astronomy-specific types (requires cornish)

Example:
    from dm_dbcore.adapters import PGPoint, PGPolygon
    from sqlalchemy.dialects.postgresql import base as pg

    pg.ischema_names['point'] = PGPoint
    pg.ischema_names['polygon'] = PGPolygon
"""

# Import standard PostgreSQL geometry types
from .pggeometry import PGPoint, PGPolygon

# Try to import astronomy types - fail silently if cornish not available
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
    "PGASTCircle",
    "PGASTPolygon",
    # Submodules
    "numpy_postgresql",
    "numpy_sqlite",
    "pggeometry",
    "ast_pg_geometry",
]
