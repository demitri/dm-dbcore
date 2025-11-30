#!/usr/bin/python
#
# TEMPLATE: SQLAlchemy Model Classes for MySQL
#
# MySQL-specific template. Note: MySQL does NOT use schemas like PostgreSQL.
# In MySQL, each "database" is equivalent to a PostgreSQL "schema".
#
# =============================================================================
# TODO CHECKLIST - Update these items before using this file:
# =============================================================================
# [ ] 1. Replace 'MYPROJECT' with your project name
# [ ] 2. Update database connection string in main() function (includes database name)
# [ ] 3. Define your model classes for tables in your database
# [ ] 4. Add relationships between models
# [ ] 5. Update metadata cache filename
# [ ] 6. Remove 'schema' from __table_args__ (MySQL doesn't use it)
# [ ] 7. Test with main() function
# =============================================================================

import logging
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship, configure_mappers, registry

from dm_dbcore import DatabaseConnection, session_scope

logger = logging.getLogger(__name__)

# =============================================================================
# MYSQL DATABASE STRUCTURE
# =============================================================================
#
# IMPORTANT: MySQL != PostgreSQL
#
# PostgreSQL:  server -> database -> schema -> table
# MySQL:       server -> database -> table
#
# In MySQL:
# - No "schema" concept - each database IS like a schema
# - No __table_args__ = {'schema': 'xxx'} needed
# - Connection string specifies the database name
# - To access tables in OTHER databases, use: database_name.table_name
#
# Example connection strings:
#   'mysql+pymysql://user:pass@localhost:3306/my_database'
#   'mysql://user:pass@localhost/my_database'
#
# =============================================================================

# =============================================================================
# MAPPER REGISTRY
# =============================================================================

mapper_registry = registry()

# =============================================================================
# MYSQL-SPECIFIC FEATURES
# =============================================================================
#
# MySQL supports different features than PostgreSQL:
#
# 1. NO SCHEMAS - Database name is in connection string, not table definition
#    __table_args__ = {'autoload': True}  # NO 'schema' parameter!
#
# 2. STORAGE ENGINES - InnoDB (default), MyISAM
#    __table_args__ = {'autoload': True, 'mysql_engine': 'InnoDB'}
#
# 3. CHARACTER SETS - utf8mb4 recommended
#    __table_args__ = {
#        'autoload': True,
#        'mysql_charset': 'utf8mb4',
#        'mysql_collate': 'utf8mb4_unicode_ci'
#    }
#
# 4. AUTO_INCREMENT - Primary key auto-increment
#    id = Column(Integer, primary_key=True, autoincrement=True)
#
# 5. TIMESTAMPS - created_at, updated_at with defaults
#    from sqlalchemy import func
#    created_at = Column(DateTime, default=func.now())
#    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
#
# 6. ENUM TYPES - MySQL native enums
#    from sqlalchemy import Enum
#    status = Column(Enum('active', 'inactive', 'pending'))
#
# 7. FULL TEXT INDEXES - For text search
#    from sqlalchemy import Index
#    __table_args__ = (
#        Index('idx_fulltext_title', 'title', mysql_prefix='FULLTEXT'),
#        {'autoload': True}
#    )
#
# =============================================================================


# =============================================================================
# MODEL CLASSES
# =============================================================================

@mapper_registry.mapped
class User:
    """
    User model - demonstrates basic MySQL table.

    MySQL features:
    - No schema specification (database is in connection string)
    - Auto-increment primary key
    - Character set handling
    - One-to-many relationships
    """

    __tablename__ = 'users'
    __table_args__ = {
        'autoload': True,
        'mysql_engine': 'InnoDB',           # Storage engine (default)
        'mysql_charset': 'utf8mb4',         # Character set
        'mysql_collate': 'utf8mb4_unicode_ci'  # Collation
    }

    # Primary key (required)
    id = Column(Integer, primary_key=True, autoincrement=True)

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
        'autoload': True,
        'mysql_engine': 'InnoDB',
        'mysql_charset': 'utf8mb4'
    }

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)

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
    Blog post model - demonstrates text content and foreign keys.
    """

    __tablename__ = 'posts'
    __table_args__ = {
        'autoload': True,
        'mysql_engine': 'InnoDB',
        'mysql_charset': 'utf8mb4'
    }

    id = Column(Integer, primary_key=True, autoincrement=True)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)

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
        'autoload': True,
        'mysql_engine': 'InnoDB'
    }

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey('posts.id'), nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)

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
# NOTE: No 'schema' parameter for MySQL!
post_tags_association = Table(
    'post_tags',
    mapper_registry.metadata,
    Column('post_id', Integer, ForeignKey('posts.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True),
    mysql_engine='InnoDB',
    mysql_charset='utf8mb4'
)


@mapper_registry.mapped
class Tag:
    """Tag model for categorizing posts."""

    __tablename__ = 'tags'
    __table_args__ = {
        'autoload': True,
        'mysql_engine': 'InnoDB'
    }

    id = Column(Integer, primary_key=True, autoincrement=True)

    posts = relationship(
        'Post',
        secondary=post_tags_association,
        back_populates='tags',
        lazy='select'
    )

    def __repr__(self):
        return f"<Tag(id={self.id})>"


# =============================================================================
# MYSQL TIMESTAMP EXAMPLE (Optional)
# =============================================================================
# Uncomment if you want to explicitly define timestamp columns

# from sqlalchemy import func
#
# @mapper_registry.mapped
# class Article:
#     """Article model with timestamp tracking."""
#
#     __tablename__ = 'articles'
#     __table_args__ = {'autoload': True, 'mysql_engine': 'InnoDB'}
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#
#     # Timestamps with automatic defaults
#     # created_at = Column(DateTime, default=func.now(), nullable=False)
#     # updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
#
#     def __repr__(self):
#         return f"<Article(id={self.id})>"


# =============================================================================
# MYSQL ENUM EXAMPLE (Optional)
# =============================================================================
# Uncomment if you want to use MySQL ENUM types

# from sqlalchemy import Enum
#
# @mapper_registry.mapped
# class Order:
#     """Order model with status enum."""
#
#     __tablename__ = 'orders'
#     __table_args__ = {'autoload': True, 'mysql_engine': 'InnoDB'}
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#
#     # MySQL ENUM type
#     # status = Column(
#     #     Enum('pending', 'processing', 'completed', 'cancelled', name='order_status'),
#     #     nullable=False,
#     #     default='pending'
#     # )
#
#     def __repr__(self):
#         return f"<Order(id={self.id})>"


# =============================================================================
# CROSS-DATABASE RELATIONSHIPS (if needed)
# =============================================================================
#
# If you have relationships to tables in OTHER MySQL databases:
#
# 1. Use database-qualified table names in ForeignKey:
#    ForeignKey('other_database.other_table.id')
#
# 2. The user must have permissions on both databases
#
# 3. Example:
#    @mapper_registry.mapped
#    class CrossDbReference:
#        __tablename__ = 'references'
#        __table_args__ = {'autoload': True}
#
#        id = Column(Integer, primary_key=True)
#        other_id = Column(Integer, ForeignKey('other_db.other_table.id'))
#
#        other_record = relationship(
#            'OtherModel',
#            foreign_keys=[other_id]
#        )
#
# NOTE: Cross-database queries can be slower and may not work with all
#       MySQL configurations. Consider consolidating into one database.
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

logger.info("MySQL model classes configured successfully")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_database_info(dbc):
    """
    Get information about the MySQL database.

    Args:
        dbc: DatabaseConnection instance

    Returns:
        dict: Database information
    """
    from sqlalchemy import text

    info = {
        'database_name': None,
        'tables': [],
        'character_set': None,
        'collation': None
    }

    try:
        with session_scope(dbc) as session:
            # Get current database name
            result = session.execute(text("SELECT DATABASE()"))
            info['database_name'] = result.scalar()

            # Get database character set and collation
            result = session.execute(
                text("""
                    SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
                    FROM information_schema.SCHEMATA
                    WHERE SCHEMA_NAME = DATABASE()
                """)
            )
            row = result.first()
            if row:
                info['character_set'] = row[0]
                info['collation'] = row[1]

            # Get table list
            result = session.execute(
                text("""
                    SELECT TABLE_NAME
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    ORDER BY TABLE_NAME
                """)
            )
            info['tables'] = [row[0] for row in result]

    except Exception as e:
        logger.error(f"Failed to get database info: {e}")

    return info


# =============================================================================
# MAIN (for testing)
# =============================================================================

