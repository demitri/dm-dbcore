#!/usr/bin/python
#
# TEMPLATE: SQLAlchemy Model Classes for PostgreSQL
#
# PostgreSQL-specific template with schema support, custom types, and advanced features.
#
# =============================================================================
# TODO CHECKLIST - Update these items before using this file:
# =============================================================================
# [ ] 1. Replace 'myschema' with your actual PostgreSQL schema name
# [ ] 2. Replace 'MYPROJECT' with your project name
# [ ] 3. Update database connection string in main() function
# [ ] 4. Define your model classes for tables in your schema
# [ ] 5. Add relationships between models
# [ ] 6. Update metadata cache filename
# [ ] 7. If using custom PostgreSQL types (Point, Polygon), uncomment examples
# [ ] 8. Test with main() function
# =============================================================================

import logging
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship, configure_mappers, registry

from dm_dbcore import DatabaseConnection, session_scope

logger = logging.getLogger(__name__)

# =============================================================================
# POSTGRESQL SCHEMA CONFIGURATION
# =============================================================================
# PostgreSQL uses schemas to organize tables within a database.
# Common schemas: public, metadata, application-specific schemas

SCHEMA_NAME = 'myschema'  # TODO: Replace with your schema name

# =============================================================================
# MAPPER REGISTRY
# =============================================================================

mapper_registry = registry()

# =============================================================================
# POSTGRESQL-SPECIFIC FEATURES
# =============================================================================
#
# PostgreSQL supports advanced features that you can use in your models:
#
# 1. SCHEMAS - Organize tables into logical groups
#    __table_args__ = {'schema': 'myschema', 'autoload': True}
#
# 2. CUSTOM TYPES - Point, Polygon (via dm-dbcore adapters)
#    from dm_dbcore.adapters.pggeometry import PGPoint, PGPolygon
#    location = Column(PGPoint)
#
# 3. ARRAYS - Store arrays of values
#    from sqlalchemy.dialects.postgresql import ARRAY
#    tags = Column(ARRAY(String))
#
# 4. JSON/JSONB - Store JSON data
#    from sqlalchemy.dialects.postgresql import JSONB
#    metadata = Column(JSONB)
#
# 5. UUID - Use UUIDs as primary keys
#    from sqlalchemy.dialects.postgresql import UUID
#    import uuid
#    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#
# 6. FULL TEXT SEARCH - Search text columns efficiently
#    from sqlalchemy.dialects.postgresql import TSVECTOR
#    search_vector = Column(TSVECTOR)
#
# =============================================================================


# =============================================================================
# MODEL CLASSES
# =============================================================================

@mapper_registry.mapped
class User:
    """
    User model - demonstrates basic PostgreSQL table with schema.

    PostgreSQL features used:
    - Schema specification
    - Serial primary key (auto-increment)
    - Timestamps
    - One-to-many relationships
    """

    __tablename__ = 'users'
    __table_args__ = {
        'schema': SCHEMA_NAME,
        'autoload': True,
        'comment': 'User accounts table'  # PostgreSQL supports table comments
    }

    # Primary key (required)
    id = Column(Integer, primary_key=True)

    # Relationships
    posts = relationship(
        'Post',
        back_populates='author',
        lazy='select',
        cascade='all, delete-orphan'
    )

    profile = relationship(
        'UserProfile',
        back_populates='user',
        uselist=False,  # One-to-one
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f"<User(id={self.id})>"


@mapper_registry.mapped
class UserProfile:
    """
    User profile - demonstrates one-to-one relationship.
    """

    __tablename__ = 'user_profiles'
    __table_args__ = {
        'schema': SCHEMA_NAME,
        'autoload': True
    }

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.users.id'), unique=True, nullable=False)

    # One-to-one relationship
    user = relationship(
        'User',
        back_populates='profile'
    )

    def __repr__(self):
        return f"<UserProfile(id={self.id}, user_id={self.user_id})>"


@mapper_registry.mapped
class Post:
    """
    Blog post model - demonstrates text content and timestamps.
    """

    __tablename__ = 'posts'
    __table_args__ = {
        'schema': SCHEMA_NAME,
        'autoload': True
    }

    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.users.id'), nullable=False)

    # Relationships
    author = relationship(
        'User',
        back_populates='posts'
    )

    comments = relationship(
        'Comment',
        back_populates='post',
        lazy='select',
        cascade='all, delete-orphan'
    )

    tags = relationship(
        'Tag',
        secondary=lambda: post_tags_association,
        back_populates='posts',
        lazy='select'
    )

    def __repr__(self):
        return f"<Post(id={self.id}, author_id={self.author_id})>"


@mapper_registry.mapped
class Comment:
    """
    Comment model - demonstrates nested relationships.
    """

    __tablename__ = 'comments'
    __table_args__ = {
        'schema': SCHEMA_NAME,
        'autoload': True
    }

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.posts.id'), nullable=False)
    author_id = Column(Integer, ForeignKey(f'{SCHEMA_NAME}.users.id'), nullable=False)

    post = relationship(
        'Post',
        back_populates='comments'
    )

    author = relationship(
        'User',
        foreign_keys=[author_id]
    )

    def __repr__(self):
        return f"<Comment(id={self.id}, post_id={self.post_id})>"


# =============================================================================
# MANY-TO-MANY EXAMPLE
# =============================================================================

# Association table for post-tag many-to-many relationship
post_tags_association = Table(
    'post_tags',
    mapper_registry.metadata,
    Column('post_id', Integer, ForeignKey(f'{SCHEMA_NAME}.posts.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey(f'{SCHEMA_NAME}.tags.id'), primary_key=True),
    schema=SCHEMA_NAME
)


@mapper_registry.mapped
class Tag:
    """Tag model for categorizing posts."""

    __tablename__ = 'tags'
    __table_args__ = {
        'schema': SCHEMA_NAME,
        'autoload': True
    }

    id = Column(Integer, primary_key=True)

    posts = relationship(
        'Post',
        secondary=post_tags_association,
        back_populates='tags',
        lazy='select'
    )

    def __repr__(self):
        return f"<Tag(id={self.id})>"


# =============================================================================
# POSTGRESQL CUSTOM TYPES EXAMPLE (Optional)
# =============================================================================
# Uncomment if you need PostGIS geometric types

# from dm_dbcore.adapters.pggeometry import PGPoint, PGPolygon
#
# @mapper_registry.mapped
# class Location:
#     """Location model using PostgreSQL Point type."""
#
#     __tablename__ = 'locations'
#     __table_args__ = {
#         'schema': SCHEMA_NAME,
#         'autoload': True
#     }
#
#     id = Column(Integer, primary_key=True)
#     # coordinates = Column(PGPoint)  # PostgreSQL Point type
#     # boundary = Column(PGPolygon)   # PostgreSQL Polygon type
#
#     def __repr__(self):
#         return f"<Location(id={self.id})>"


# =============================================================================
# POSTGRESQL ADVANCED TYPES EXAMPLE (Optional)
# =============================================================================
# Uncomment if you need JSON, Arrays, or other PostgreSQL-specific types

# from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
# import uuid
#
# @mapper_registry.mapped
# class Article:
#     """Article model demonstrating PostgreSQL advanced types."""
#
#     __tablename__ = 'articles'
#     __table_args__ = {
#         'schema': SCHEMA_NAME,
#         'autoload': True
#     }
#
#     # UUID primary key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#
#     # Array of strings
#     # tags = Column(ARRAY(String))
#
#     # JSON metadata
#     # metadata = Column(JSONB)
#
#     def __repr__(self):
#         return f"<Article(id={self.id})>"


# =============================================================================
# CROSS-SCHEMA RELATIONSHIPS (if needed)
# =============================================================================
#
# If you have relationships to tables in OTHER schemas, you must:
# 1. Use fully-qualified schema names in ForeignKey:
#    ForeignKey('other_schema.other_table.id')
#
# 2. Explicitly specify foreign_keys in relationship():
#    relationship('OtherModel', foreign_keys=[foreign_key_column])
#
# See TEMPLATE_CrossSchemaRelationships.py for detailed examples
#
# =============================================================================


# =============================================================================
# FINALIZE MODEL CLASSES
# =============================================================================
#
# Model classes are configured automatically via the @mapper_registry.mapped
# decorator when this module is imported. The configure_mappers() call below
# validates all relationships are properly configured.
#
# No explicit load function is needed. Simply import your model classes:
#   from myschema_models import User, Post
# =============================================================================

# Validate all mapper relationships
configure_mappers()

logger.info(f"{SCHEMA_NAME} PostgreSQL model classes configured successfully")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_schema_info(dbc):
    """
    Get information about the PostgreSQL schema.

    Args:
        dbc: DatabaseConnection instance

    Returns:
        dict: Schema information
    """
    from sqlalchemy import text

    info = {
        'schema_name': SCHEMA_NAME,
        'tables': [],
        'exists': False
    }

    try:
        with session_scope(dbc) as session:
            # Check if schema exists
            result = session.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
                {'schema': SCHEMA_NAME}
            )
            info['exists'] = result.first() is not None

            if info['exists']:
                # Get table list
                result = session.execute(
                    text("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = :schema
                        ORDER BY table_name
                    """),
                    {'schema': SCHEMA_NAME}
                )
                info['tables'] = [row[0] for row in result]

    except Exception as e:
        logger.error(f"Failed to get schema info: {e}")

    return info
