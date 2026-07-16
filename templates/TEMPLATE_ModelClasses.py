#!/usr/bin/env python
"""
TEMPLATE: SQLAlchemy model classes.

Works against any database dm-dbcore supports (PostgreSQL, MySQL, SQLite). For
PostgreSQL-specific features (custom types, JSONB, arrays) start from
TEMPLATE_ModelClasses_PostgreSQL.py instead; for MySQL, TEMPLATE_ModelClasses_MySQL.py.

THE IDEA: the database defines the schema. This file reflects it.

Every class below reflects its columns from the live database with
`autoload_with=engine`. You never declare columns here -- if you did, you would
be writing the schema down twice and the copies would drift. What this file
adds is the part the database cannot express: the Python-side relationships
between tables.

Reflection gives you columns and foreign key CONSTRAINTS. It does NOT give you
`relationship()` objects -- those are a Python concept and always hand-written.
The database says "student.city_id references city.id"; whether that surfaces
as `student.city` or `city.students` is your decision, not the database's.

=============================================================================
TODO CHECKLIST
=============================================================================
[ ] 1. Point the import below at your connection module
[ ] 2. Replace the example classes with your tables
[ ] 3. Give every class a one-line docstring
[ ] 4. Define relationships at the bottom, after all classes exist
[ ] 5. Run this file directly to validate: python ThisFile.py
=============================================================================
"""

import warnings

from sqlalchemy import Table, select
from sqlalchemy.orm import DeclarativeBase, relationship, configure_mappers

# TODO: point this at your connection module. SCHEMA is defined there so that
# this file is identical whichever database it runs against -- only the
# connection module knows where the tables live.
from TEMPLATE_Connection import SCHEMA, engine, session_scope

# Reflection warns about column types it cannot map. They are harmless: the
# column is still reflected, just without a specialised Python type.
warnings.filterwarnings(action="ignore", message="Skipped unsupported reflection")


class Base(DeclarativeBase):
    """Declarative base for this project's model classes."""


# =============================================================================
# Model classes
# =============================================================================
#
# Pattern:
#
#     class MyTable(Base):
#         """What this table represents."""
#         __table__ = Table("my_table", Base.metadata, schema=SCHEMA,
#                           autoload_with=engine)
#
# The table must already exist in the database -- reflection reads it, it does
# not create it. A table name that does not exist raises NoSuchTableError
# naming the table.


class User(Base):
    """A person with an account."""

    __table__ = Table("users", Base.metadata, schema=SCHEMA, autoload_with=engine)

    def __repr__(self) -> str:
        return f"<User(id={self.id})>"


class Post(Base):
    """A post written by a user."""

    __table__ = Table("posts", Base.metadata, schema=SCHEMA, autoload_with=engine)

    def __repr__(self) -> str:
        return f"<Post(id={self.id})>"


class Tag(Base):
    """A label that can be applied to many posts."""

    __table__ = Table("tags", Base.metadata, schema=SCHEMA, autoload_with=engine)

    def __repr__(self) -> str:
        return f"<Tag(id={self.id})>"


# A join table carrying no data of its own needs no class -- reflect it as a
# plain Table and hand it to `secondary=` below.
post_tags = Table("post_tags", Base.metadata, schema=SCHEMA, autoload_with=engine)


# =============================================================================
# Relationships
# =============================================================================
#
# Defined after every class exists, so each one can refer to the others without
# forward references.
#
# ONE-TO-MANY -- one user has many posts. `backref` creates the reverse
# attribute (post.author) at the same time.

User.posts = relationship(Post, backref="author")

# MANY-TO-MANY -- posts have many tags, tags belong to many posts. `secondary`
# names the join table.

Post.tags = relationship(Tag, secondary=post_tags, backref="posts")

# ONE-TO-ONE -- add uselist=False on the "one" side:
#
#     User.profile = relationship(Profile, backref="user", uselist=False)
#
# AMBIGUOUS FOREIGN KEYS -- if a table has two FKs to the same target,
# SQLAlchemy cannot guess which one a relationship means. Say so explicitly:
#
#     Comment.author = relationship(
#         User, foreign_keys=[Comment.__table__.c.author_id]
#     )
#
# LOADING STRATEGY -- lazy="select" (default) fetches on attribute access;
# lazy="joined" fetches in the original query; lazy="selectin" is usually the
# best choice for collections. Tune only when a query is measurably slow.


# Validate every mapping and relationship now, at import, rather than at the
# first query. Raises if a relationship is inconsistent.
configure_mappers()


# =============================================================================
# Validation
# =============================================================================


def main() -> int:
    """Check that the models match the database. Run this file directly."""
    print(f"schema: {SCHEMA}")
    for cls in (User, Post, Tag):
        columns = ", ".join(c.name for c in cls.__table__.columns)
        print(f"  {cls.__name__:12s} -> {columns}")

    with session_scope() as session:
        user = session.scalars(select(User)).first()
        if user is None:
            print("\nNo rows yet -- mappings are valid but the table is empty.")
            return 0
        print(f"\nfirst user : {user}")
        print(f"  posts    : {len(user.posts)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
