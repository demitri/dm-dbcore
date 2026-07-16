#!/usr/bin/env python
"""
TEMPLATE: SQLAlchemy model classes for MySQL.

Start from TEMPLATE_ModelClasses.py for the generic version; this file adds only
what MySQL does differently. For PostgreSQL, see TEMPLATE_ModelClasses_PostgreSQL.py.

THE IDEA: the database defines the schema. This file reflects it.

Every class below reflects its columns from the live database with
`autoload_with=engine`. You never declare columns here -- if you did, you would
be writing the schema down twice and the copies would drift. What this file
adds is the part the database cannot express: the Python-side relationships
between tables.

=============================================================================
MYSQL HAS NO SCHEMAS
=============================================================================
This is the one thing that trips up everyone arriving from PostgreSQL.

    PostgreSQL:  server -> database -> schema -> table
    MySQL:       server -> database ->           table

A MySQL "database" occupies the slot PostgreSQL gives to a schema. There is no
level below it to name, so `SCHEMA` is None for MySQL, and the database name
moves into the connection URL instead -- which is why a MySQL URL MUST carry
one:

    mysql+pymysql://user:pass@host:3306/database
                                       ^^^^^^^^ not optional

`schema=SCHEMA` is still passed to every Table(...) call below, with the value
None. That is deliberate: this file then has the same shape as its PostgreSQL
and SQLite siblings, and the connection module is the only thing that differs.
Passing schema=None is also what the style gate expects -- an OMITTED schema is
a violation; an explicit None is not.

=============================================================================
TODO CHECKLIST
=============================================================================
[ ] 1. Point the import below at your MySQL connection module
[ ] 2. Confirm SCHEMA is None there, and the URL names the database
[ ] 3. Replace the example classes with your tables
[ ] 4. Give every class a one-line docstring
[ ] 5. Define relationships at the bottom, after all classes exist
[ ] 6. Run this file directly to validate: python ThisFile.py
=============================================================================
"""

import warnings

from sqlalchemy import Table, select
from sqlalchemy.orm import DeclarativeBase, relationship, configure_mappers

# TODO: point this at your connection module. SCHEMA is defined there -- None
# for MySQL -- so that this file is identical whichever database it runs
# against. See TEMPLATE_Connection.py, including its note that pymysql does NOT
# read ~/.my.cnf the way libpq reads ~/.pgpass; dm-dbcore supplies a reader:
#
#     from dm_dbcore.mysql import read_password_from_my_cnf
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
# The table must already exist -- reflection reads it, it does not create it.
#
# STORAGE ENGINE AND CHARSET are decisions you make in the DDL that CREATES the
# table, not here. By the time this file runs they are settled facts about the
# database, and reflection reads them; restating them in Python would be a
# second copy that can drift. In your CREATE TABLE:
#
#     ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
#
# InnoDB is not optional if you want relationships: MyISAM parses FOREIGN KEY
# and then silently ignores it, so the constraint never exists, reflection finds
# nothing to reflect, and every relationship below has to be spelled out by hand
# with foreign_keys=. Use utf8mb4 rather than MySQL's "utf8", which is a 3-byte
# encoding that cannot store emoji or much of CJK.


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
# ACROSS DATABASES -- MySQL's version of PostgreSQL's cross-schema problem. The
# other database is named where PostgreSQL would name a schema:
#
#     ForeignKey("other_database.other_table.id")
#
# The connecting user needs privileges on both, and both must live on the same
# server -- MySQL cannot follow a foreign key to another host. See
# TEMPLATE_CrossSchemaRelationships.py for the full pattern.


# Validate every mapping and relationship now, at import, rather than at the
# first query. Raises if a relationship is inconsistent.
configure_mappers()


# =============================================================================
# Validation
# =============================================================================


def main() -> int:
    """Check that the models match the database. Run this file directly."""
    from sqlalchemy import text

    # SCHEMA is None for MySQL; DATABASE() reports what the URL actually
    # selected, which is the value that matters here.
    with session_scope() as session:
        print(f"database: {session.execute(text('SELECT DATABASE()')).scalar()}")

    print(f"schema  : {SCHEMA} (MySQL has no schemas -- this is expected)")
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
