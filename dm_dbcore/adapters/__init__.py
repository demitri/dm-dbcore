"""
Database adapters for custom data types.

This module provides SQLAlchemy adapters for:
- NumPy arrays (PostgreSQL and SQLite)
- PostgreSQL geometric types (Point, Polygon, Circle)
- PostgreSQL CITEXT (case-insensitive text)

Available adapters:
- PGPoint, PGPolygon: Standard PostgreSQL geometric types
- PGASTCircle, PGASTPolygon: Astronomy-specific types (requires cornish)
- PGCitext: PostgreSQL citext type

Example:
    from dm_dbcore.adapters import PGPoint, PGPolygon
    from sqlalchemy.dialects.postgresql import base as pg

    pg.ischema_names['point'] = PGPoint
    pg.ischema_names['polygon'] = PGPolygon
"""

# Import PostgreSQL adapter symbols
from .postgresql import PGPoint, PGPolygon, PGCircle, PGCitext

# Try to import astronomy types - fail silently if cornish not available
try:
    from .postgresql import PGASTCircle, PGASTPolygon
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
    # Submodules
    "postgresql",
    "sqlite",
]
