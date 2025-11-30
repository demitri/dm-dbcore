#!/usr/bin/python
#
# TEMPLATE: Cross-Schema Relationships
#
# This template demonstrates how to define relationships between tables
# in DIFFERENT database schemas using SQLAlchemy and dm-dbcore.
#
# Cross-schema relationships require special handling because SQLAlchemy
# needs to know the full schema-qualified table names.
#
# =============================================================================
# TODO CHECKLIST - Update these items before using this file:
# =============================================================================
# [ ] 1. Replace 'SCHEMA1' and 'SCHEMA2' with your actual schema names
# [ ] 2. Update model class names and table names
# [ ] 3. Define foreign key relationships with schema-qualified names
# [ ] 4. Import both schemas' model classes
# [ ] 5. Test relationships work correctly
# [ ] 6. Review PostgreSQL search_path handling (see notes below)
# =============================================================================

import logging
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, configure_mappers
from sqlalchemy.orm import registry

from dm_dbcore import DatabaseConnection, session_scope

logger = logging.getLogger(__name__)

# =============================================================================
# IMPORTANT: PostgreSQL search_path
# =============================================================================
#
# The dm-dbcore DatabaseConnection automatically clears the PostgreSQL
# search_path to avoid ambiguity when working with multiple schemas.
#
# This means you MUST use fully-qualified table names in foreign keys:
#   ✓ CORRECT:   ForeignKey('schema1.users.id')
#   ✗ INCORRECT: ForeignKey('users.id')
#
# See DatabaseConnection.py:29-59 for details on search_path handling.
#
# =============================================================================

# Create separate mapper registries for each schema (recommended)
schema1_registry = registry()
schema2_registry = registry()

# =============================================================================
# SCHEMA 1: User Management
# =============================================================================

@schema1_registry.mapped
class User:
    """
    User model in schema1.

    This user can have posts in schema2 (cross-schema relationship).
    """

    __tablename__ = 'users'
    __table_args__ = {'schema': 'SCHEMA1', 'autoload': True}

    # Primary key
    id = Column(Integer, primary_key=True)

    # ONE-TO-MANY cross-schema relationship: User -> Posts
    posts = relationship(
        'Post',                                    # Related class in schema2
        back_populates='author',                   # Corresponding attribute on Post
        foreign_keys='Post.author_id',             # Explicitly specify foreign key
        lazy='select',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f"<User(id={self.id})>"


@schema1_registry.mapped
class UserProfile:
    """
    User profile model in schema1.

    This is a ONE-TO-ONE relationship with User (same schema).
    """

    __tablename__ = 'user_profiles'
    __table_args__ = {'schema': 'SCHEMA1', 'autoload': True}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('SCHEMA1.users.id'), unique=True)

    # ONE-TO-ONE relationship
    user = relationship(
        'User',
        backref='profile',           # Creates User.profile attribute
        uselist=False                # ONE-TO-ONE (not a list)
    )

    def __repr__(self):
        return f"<UserProfile(id={self.id}, user_id={self.user_id})>"


# =============================================================================
# SCHEMA 2: Content Management
# =============================================================================

@schema2_registry.mapped
class Post:
    """
    Post model in schema2.

    Posts belong to users in schema1 (cross-schema relationship).
    """

    __tablename__ = 'posts'
    __table_args__ = {'schema': 'SCHEMA2', 'autoload': True}

    # Primary key
    id = Column(Integer, primary_key=True)

    # IMPORTANT: Foreign key MUST include schema name!
    author_id = Column(Integer, ForeignKey('SCHEMA1.users.id'))

    # MANY-TO-ONE cross-schema relationship: Post -> User
    author = relationship(
        'User',                                    # Related class in schema1
        back_populates='posts',                    # Corresponding attribute on User
        foreign_keys=[author_id],                  # Explicitly specify foreign key
        lazy='select'
    )

    # ONE-TO-MANY same-schema relationship: Post -> Comments
    comments = relationship(
        'Comment',
        back_populates='post',
        lazy='select',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f"<Post(id={self.id}, author_id={self.author_id})>"


@schema2_registry.mapped
class Comment:
    """
    Comment model in schema2.

    Comments belong to posts in the same schema, and authors in schema1.
    """

    __tablename__ = 'comments'
    __table_args__ = {'schema': 'SCHEMA2', 'autoload': True}

    id = Column(Integer, primary_key=True)

    # Foreign key to Post (same schema)
    post_id = Column(Integer, ForeignKey('SCHEMA2.posts.id'))

    # Foreign key to User (cross-schema) - MUST include schema name!
    author_id = Column(Integer, ForeignKey('SCHEMA1.users.id'))

    # Relationships
    post = relationship(
        'Post',
        back_populates='comments'
    )

    author = relationship(
        'User',
        foreign_keys=[author_id],
        lazy='select'
    )

    def __repr__(self):
        return f"<Comment(id={self.id}, post_id={self.post_id}, author_id={self.author_id})>"


# =============================================================================
# EXAMPLE: Cross-Schema Many-to-Many Relationship
# =============================================================================

from sqlalchemy import Table

# Association table in schema2 linking posts to categories in schema1
post_categories_association = Table(
    'post_categories',
    schema2_registry.metadata,
    # Note: Foreign keys MUST include schema names!
    Column('post_id', Integer, ForeignKey('SCHEMA2.posts.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('SCHEMA1.categories.id'), primary_key=True),
    schema='SCHEMA2'
)


@schema1_registry.mapped
class Category:
    """Category model in schema1."""

    __tablename__ = 'categories'
    __table_args__ = {'schema': 'SCHEMA1', 'autoload': True}

    id = Column(Integer, primary_key=True)

    # MANY-TO-MANY cross-schema relationship
    posts = relationship(
        'Post',
        secondary=post_categories_association,
        back_populates='categories',
        lazy='select'
    )

    def __repr__(self):
        return f"<Category(id={self.id})>"


# Add corresponding relationship to Post class:
# (This would be added to the Post class definition above)
#
# categories = relationship(
#     'Category',
#     secondary=post_categories_association,
#     back_populates='posts',
#     lazy='select'
# )


# =============================================================================
# COMMON PITFALLS AND SOLUTIONS
# =============================================================================
#
# PITFALL 1: Forgetting schema name in ForeignKey
# ✗ WRONG:  ForeignKey('users.id')
# ✓ RIGHT:  ForeignKey('SCHEMA1.users.id')
#
# PITFALL 2: Circular imports between schema modules
# SOLUTION: Import model classes within functions, not at module level
#           Or use string-based relationship() references
#
# PITFALL 3: Ambiguous foreign_keys with multiple FKs to same table
# SOLUTION: Explicitly specify foreign_keys parameter:
#           relationship('User', foreign_keys=[author_id])
#
# PITFALL 4: search_path is set in PostgreSQL config
# SOLUTION: dm-dbcore automatically clears search_path
#           Always use fully-qualified names anyway
#
# PITFALL 5: Metadata not properly shared between registries
# SOLUTION: Use separate registries per schema, bind both to same engine
#
# =============================================================================


# =============================================================================
# LOADING FUNCTIONS
# =============================================================================

def load_schema1_models(dbc):
    """
    Load and validate schema1 model classes.

    Args:
        dbc: DatabaseConnection instance

    Returns:
        bool: True if successful
    """
    try:
        schema1_registry.metadata.bind = dbc.engine
        # Don't configure_mappers() yet - wait for all schemas
        logger.info("SCHEMA1 models loaded")
        return True
    except Exception as e:
        logger.error(f"Failed to load SCHEMA1 models: {e}")
        return False


def load_schema2_models(dbc):
    """
    Load and validate schema2 model classes.

    Args:
        dbc: DatabaseConnection instance

    Returns:
        bool: True if successful
    """
    try:
        schema2_registry.metadata.bind = dbc.engine
        # Don't configure_mappers() yet - wait for all schemas
        logger.info("SCHEMA2 models loaded")
        return True
    except Exception as e:
        logger.error(f"Failed to load SCHEMA2 models: {e}")
        return False


def load_all_models_with_relationships(dbc):
    """
    Load all model classes and configure cross-schema relationships.

    IMPORTANT: This must be called AFTER all individual schema loaders.

    Args:
        dbc: DatabaseConnection instance

    Returns:
        bool: True if successful
    """
    try:
        # Load both schemas
        if not load_schema1_models(dbc):
            return False
        if not load_schema2_models(dbc):
            return False

        # NOW configure all mappers and relationships
        configure_mappers()

        logger.info("All cross-schema relationships configured")
        return True

    except Exception as e:
        logger.error(f"Failed to configure cross-schema relationships: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# MAIN (for testing)
# =============================================================================

