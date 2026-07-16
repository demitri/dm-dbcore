#!/usr/bin/env python
"""
TEMPLATE: SQLAlchemy model classes for PostgreSQL.

Start from TEMPLATE_ModelClasses.py if you do not need anything PostgreSQL
specific -- everything there applies here too. This file adds only what is
particular to PostgreSQL: schemas, and the rich column types the other backends
do not have.

THE IDEA: the database defines the schema. This file reflects it.

Every class below reflects its columns from the live database with
`autoload_with=engine`. You never declare columns here -- if you did, you would
be writing the schema down twice and the copies would drift. What this file
adds is the part the database cannot express: the Python-side relationships
between tables.

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

from sqlalchemy import Table, select, text
from sqlalchemy.orm import DeclarativeBase, relationship, configure_mappers

# TODO: point this at your connection module. SCHEMA is defined there, so a
# project that moves schemas changes one line there rather than every Table()
# call here.
from TEMPLATE_Connection import SCHEMA, engine, session_scope

# Reflection warns about column types it cannot map. They are harmless: the
# column is still reflected, just without a specialised Python type.
warnings.filterwarnings(action="ignore", message="Skipped unsupported reflection")


class Base(DeclarativeBase):
    """Declarative base for this project's model classes."""


# =============================================================================
# Schemas
# =============================================================================
#
# PostgreSQL nests tables one level deeper than the other backends:
#
#     server -> database -> schema -> table
#
# Every Table() call below passes `schema=SCHEMA` explicitly, and that is not
# decoration. dm-dbcore CLEARS THE search_path on every connection, deliberately
# -- an implicit search_path is what lets "users" mean core.users on your laptop
# and public.users in production, silently. With it cleared, an unqualified
# table name resolves to nothing and reflection raises NoSuchTableError instead
# of quietly reflecting the wrong table.
#
# =============================================================================
# PostgreSQL column types
# =============================================================================
#
# JSONB, ARRAY, UUID, TSVECTOR, and the geometric types all arrive through
# reflection already typed. There is nothing to declare and nothing to import:
# a JSONB column hands you a dict, an ARRAY column hands you a list, a POINT
# column hands you a tuple of floats.
#
# The geometric and text types are not native to SQLAlchemy -- dm-dbcore
# supplies adapters (PGPoint, PGPolygon, PGCircle, PGCIText, PGXML; see
# dm_dbcore/adapters/postgresql/pggeometry.py) and registers them into the
# dialect automatically whenever DatabaseConnection sees a PostgreSQL URL.
# Importing your connection module is all the setup there is; reflection then
# picks them up on its own.


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
# not create it.


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


class Location(Base):
    """A place on a map, using PostgreSQL geometric columns."""

    # Geometric columns reflect through the dm-dbcore adapters with nothing
    # declared here:
    #
    #   location.coordinates -> PGPoint((1.5, 2.5))        .x  .y
    #   location.boundary    -> PGPolygon()                .points (ndarray)
    #
    # They round-trip: assign one straight back, or build a new one in Python
    # (PGPoint((10.25, -3.5))) and insert it.
    __table__ = Table("locations", Base.metadata, schema=SCHEMA, autoload_with=engine)

    def __repr__(self) -> str:
        return f"<Location(id={self.id})>"


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

# CROSS-SCHEMA -- relationships whose two ends live in different schemas need
# schema-qualified ForeignKey targets ("other_schema.other_table.id") and an
# explicit foreign_keys=. See TEMPLATE_CrossSchemaRelationships.py.
#
# AMBIGUOUS FOREIGN KEYS -- if a table has two FKs to the same target,
# SQLAlchemy cannot guess which one a relationship means. Say so explicitly:
#
#     Comment.author = relationship(
#         User, foreign_keys=[Comment.__table__.c.author_id]
#     )


# Validate every mapping and relationship now, at import, rather than at the
# first query. Raises if a relationship is inconsistent.
configure_mappers()


# =============================================================================
# Utilities
# =============================================================================


def get_schema_info(session) -> dict:
    """Return {'schema', 'exists', 'tables'} for SCHEMA, read from the server.

    This asks PostgreSQL what is actually there, which is the useful counterpart
    to reflection: it lists tables this file has NOT declared classes for.
    """
    exists = session.execute(
        text(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"
        ),
        {"schema": SCHEMA},
    ).first()

    tables = session.scalars(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name"
        ),
        {"schema": SCHEMA},
    ).all()

    return {"schema": SCHEMA, "exists": exists is not None, "tables": list(tables)}


# =============================================================================
# Validation
# =============================================================================


def main() -> int:
    """Check that the models match the database. Run this file directly."""
    print(f"schema: {SCHEMA}")
    for cls in (User, Post, Tag, Location):
        columns = ", ".join(c.name for c in cls.__table__.columns)
        print(f"  {cls.__name__:12s} -> {columns}")

    with session_scope() as session:
        info = get_schema_info(session)
        if not info["exists"]:
            print(f"\nSchema {SCHEMA!r} does not exist on this server.")
            return 1
        print(f"\ntables in {SCHEMA}: {', '.join(info['tables']) or '(none)'}")

        user = session.scalars(select(User)).first()
        if user is None:
            print("\nNo rows yet -- mappings are valid but the table is empty.")
            return 0
        print(f"\nfirst user : {user}")
        print(f"  posts    : {len(user.posts)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
