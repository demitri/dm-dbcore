#!/usr/bin/python
#
# TEMPLATE: SQLAlchemy Model Classes
#
# This template provides a starting point for defining SQLAlchemy ORM model classes
# for a specific database schema using the dm-dbcore package.
#
# =============================================================================
# TODO CHECKLIST - Update these items before using this file:
# =============================================================================
# [ ] 1. Replace 'MYSCHEMA' with your actual schema name (multiple places)
# [ ] 2. Replace 'MYPROJECT' with your project name
# [ ] 3. Update database connection string in main() function
# [ ] 4. Define your model classes (see examples below)
# [ ] 5. Add relationships between models (one-to-one, one-to-many, many-to-many)
# [ ] 6. Update metadata cache filename
# [ ] 7. Test model class loading with main() function
# [ ] 8. For cross-schema relationships, see TEMPLATE_CrossSchemaRelationships.py
# =============================================================================

import logging
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship, configure_mappers

# Import dm-dbcore components
from dm_dbcore import DatabaseConnection, session_scope

logger = logging.getLogger(__name__)

# =============================================================================
# MAPPER REGISTRY SETUP
# =============================================================================
# The mapper registry is used to define model classes in SQLAlchemy 2.0 style

from sqlalchemy.orm import registry
mapper_registry = registry()

# =============================================================================
# MODEL CLASS DEFINITIONS
# =============================================================================

@mapper_registry.mapped
class MyTable:
    """
    Example model class for a database table.

    This class uses SQLAlchemy's autoload feature to reflect the table structure
    from the database, so you don't need to define every column manually.

    IMPORTANT: The table must exist in the database before loading this class!
    """

    # ------------------------------------------------------------------
    # TODO: Update these for your table
    # ------------------------------------------------------------------
    __tablename__ = 'my_table'           # Table name in database
    __table_args__ = {'schema': 'MYSCHEMA', 'autoload': True}

    # ------------------------------------------------------------------
    # Primary Key (required)
    # ------------------------------------------------------------------
    # You must explicitly define the primary key column(s)
    id = Column(Integer, primary_key=True)

    # ------------------------------------------------------------------
    # Additional Columns (optional - only if not autoloaded)
    # ------------------------------------------------------------------
    # If autoload=True, you don't need to define columns unless you want
    # to override the autoloaded definition or add relationships

    # name = Column(String(100))  # Example: explicit column definition

    # ------------------------------------------------------------------
    # Relationships: ONE-TO-MANY
    # ------------------------------------------------------------------
    # Define relationships when this table is the "one" side of a 1:N relationship
    #
    # Example: One User has many Posts
    #
    # posts = relationship(
    #     'Post',                          # Related model class name
    #     back_populates='user',           # Corresponding attribute on Post
    #     lazy='select',                   # Loading strategy: 'select', 'joined', 'subquery', 'dynamic'
    #     cascade='all, delete-orphan'     # Cascade behavior for deletes
    # )

    # ------------------------------------------------------------------
    # Relationships: MANY-TO-ONE
    # ------------------------------------------------------------------
    # Define relationships when this table is the "many" side of a N:1 relationship
    #
    # Example: Many Posts belong to one User
    #
    # user_id = Column(Integer, ForeignKey('MYSCHEMA.users.id'))
    # user = relationship(
    #     'User',                          # Related model class name
    #     back_populates='posts'           # Corresponding attribute on User
    # )

    # ------------------------------------------------------------------
    # Relationships: MANY-TO-MANY
    # ------------------------------------------------------------------
    # Define many-to-many relationships using an association table
    # See example below with Tag and Post classes

    def __repr__(self):
        """String representation for debugging."""
        return f"<MyTable(id={self.id})>"


# =============================================================================
# EXAMPLE: One-to-Many Relationship
# =============================================================================

@mapper_registry.mapped
class User:
    """Example: User model (the 'one' side of 1:N relationship)."""

    __tablename__ = 'users'
    __table_args__ = {'schema': 'MYSCHEMA', 'autoload': True}

    id = Column(Integer, primary_key=True)

    # ONE-TO-MANY: One user has many posts
    posts = relationship(
        'Post',
        back_populates='user',
        lazy='select',                    # Load posts when accessed
        cascade='all, delete-orphan'      # Delete posts when user is deleted
    )

    def __repr__(self):
        return f"<User(id={self.id})>"


@mapper_registry.mapped
class Post:
    """Example: Post model (the 'many' side of N:1 relationship)."""

    __tablename__ = 'posts'
    __table_args__ = {'schema': 'MYSCHEMA', 'autoload': True}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('MYSCHEMA.users.id'))

    # MANY-TO-ONE: Many posts belong to one user
    user = relationship(
        'User',
        back_populates='posts'
    )

    def __repr__(self):
        return f"<Post(id={self.id}, user_id={self.user_id})>"


# =============================================================================
# EXAMPLE: Many-to-Many Relationship
# =============================================================================

# Association table for many-to-many relationship
# This is NOT a model class, just a Table object
post_tags_association = Table(
    'post_tags',
    mapper_registry.metadata,
    Column('post_id', Integer, ForeignKey('MYSCHEMA.posts.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('MYSCHEMA.tags.id'), primary_key=True),
    schema='MYSCHEMA'
)


@mapper_registry.mapped
class Tag:
    """Example: Tag model for many-to-many relationship."""

    __tablename__ = 'tags'
    __table_args__ = {'schema': 'MYSCHEMA', 'autoload': True}

    id = Column(Integer, primary_key=True)

    # MANY-TO-MANY: Tags can be on many posts, posts can have many tags
    posts = relationship(
        'Post',
        secondary=post_tags_association,  # Association table
        back_populates='tags',
        lazy='select'
    )

    def __repr__(self):
        return f"<Tag(id={self.id})>"


# Don't forget to add the back_populates to Post class:
# Add this to Post class above:
#
# tags = relationship(
#     'Tag',
#     secondary=post_tags_association,
#     back_populates='posts',
#     lazy='select'
# )


# =============================================================================
# RELATIONSHIP LOADING STRATEGIES
# =============================================================================
#
# lazy='select'        - Load related objects on access (default, N+1 queries)
# lazy='joined'        - Load related objects with JOIN in same query
# lazy='subquery'      - Load related objects with subquery
# lazy='dynamic'       - Return Query object instead of loading (for large collections)
# lazy='selectin'      - Use SELECT IN to load related objects (good for collections)
# lazy='noload'        - Never load related objects
# lazy='raise'         - Raise exception if accessed (force explicit loading)
#
# =============================================================================


# =============================================================================
# CASCADE OPTIONS
# =============================================================================
#
# cascade='all'                  - All operations cascade
# cascade='save-update'          - Only save/update cascades (default)
# cascade='delete'               - Deletion cascades
# cascade='delete-orphan'        - Delete orphaned objects
# cascade='all, delete-orphan'   - Common pattern for owned relationships
# cascade='merge'                - Merge operations cascade
# cascade='refresh-expire'       - Refresh/expire operations cascade
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
#   from myproject_models import User, Post
# =============================================================================

# Validate all mapper relationships
configure_mappers()

logger.info("MYSCHEMA model classes configured successfully")
