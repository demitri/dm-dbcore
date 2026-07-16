#!/usr/bin/env python
"""
TEMPLATE: relationships that cross schemas (PostgreSQL) or databases (MySQL).

Use this when a table in one schema has a foreign key into another --
`content.post.author_id` -> `people.user.id`. For single-schema projects start
from TEMPLATE_ModelClasses.py instead.

THE SHORT VERSION: there is much less to do here than you would expect.

The foreign key already exists in the database, and reflection reads it. You do
not declare `ForeignKey(...)` in this file -- doing so would be writing the
constraint down a second time, in a second language, where it can drift. What
this file adds is the same thing every model file adds: the Python-side
`relationship()` objects, which reflection cannot infer.

Two rules make cross-schema work:

  1. ONE Base, one MetaData, for every schema. Tables that reference each other
     must live in the same MetaData or SQLAlchemy cannot resolve the foreign
     key across them. Do not create a registry or a Base per schema.

  2. Always pass `schema=` explicitly. dm-dbcore clears the PostgreSQL
     search_path on every connection, so an unqualified name resolves to
     nothing -- loudly, which is the point. Ambiguity here is far more
     expensive than the typing.

MySQL: substitute "database" for "schema" throughout. MySQL has no schemas, so
a cross-database reference uses the database name in the same position:
`schema="otherdb"`. The connection user needs privileges on both.

=============================================================================
TODO CHECKLIST
=============================================================================
[ ] 1. Point the import below at your connection module
[ ] 2. Replace PEOPLE_SCHEMA / CONTENT_SCHEMA with your schema names
[ ] 3. Replace the example classes with your tables
[ ] 4. Define cross-schema relationships at the bottom
[ ] 5. Run this file directly to validate: python ThisFile.py
=============================================================================
"""

import warnings

from sqlalchemy import Table, select
from sqlalchemy.orm import DeclarativeBase, relationship, configure_mappers

# TODO: point this at your connection module. Note that SCHEMA is not imported:
# a cross-schema file names more than one schema, so it defines them below.
from TEMPLATE_Connection import engine, session_scope

warnings.filterwarnings(action="ignore", message="Skipped unsupported reflection")

# TODO: name your schemas. On MySQL these are database names.
PEOPLE_SCHEMA = "people"
CONTENT_SCHEMA = "content"


class Base(DeclarativeBase):
    """Single declarative base shared by every schema in this project."""


# =============================================================================
# people schema
# =============================================================================
#
# Reflect the referenced ("parent") tables first. This is not strictly
# required -- SQLAlchemy follows a foreign key and reflects its target
# automatically, so reflecting content.post would pull people.user in by
# itself -- but doing it explicitly means each table is declared where you
# expect to find it, rather than appearing as a side effect.


class User(Base):
    """A person, in the people schema."""

    __table__ = Table("user", Base.metadata, schema=PEOPLE_SCHEMA, autoload_with=engine)

    def __repr__(self) -> str:
        return f"<User(id={self.id})>"


# =============================================================================
# content schema
# =============================================================================


class Post(Base):
    """A post in the content schema, written by a user in the people schema."""

    __table__ = Table("post", Base.metadata, schema=CONTENT_SCHEMA, autoload_with=engine)

    def __repr__(self) -> str:
        return f"<Post(id={self.id})>"


class Comment(Base):
    """A comment on a post. Written by a user, so it also crosses schemas."""

    __table__ = Table(
        "comment", Base.metadata, schema=CONTENT_SCHEMA, autoload_with=engine
    )

    def __repr__(self) -> str:
        return f"<Comment(id={self.id})>"


# =============================================================================
# Relationships
# =============================================================================
#
# Nothing here mentions a schema. Once both tables are reflected into the same
# MetaData, a relationship that crosses schemas is written exactly like one
# that does not -- SQLAlchemy already knows where each table lives and how the
# foreign key connects them.

User.posts = relationship(Post, backref="author")

# AMBIGUOUS FOREIGN KEYS. `comment` has two foreign keys -- one to post, one to
# user -- so SQLAlchemy cannot infer which one a relationship means and will
# raise AmbiguousForeignKeysError. Name the column explicitly. This is the most
# common failure in cross-schema models, because a table that reaches into
# another schema usually also reaches within its own.

Post.comments = relationship(
    Comment,
    backref="post",
    foreign_keys=[Comment.__table__.c.post_id],
)

User.comments = relationship(
    Comment,
    backref="author",
    foreign_keys=[Comment.__table__.c.author_id],
)

# MANY-TO-MANY across schemas. Reflect the join table like any other, naming
# whichever schema it physically lives in, and pass it as `secondary=`:
#
#     post_tags = Table("post_tag", Base.metadata, schema=CONTENT_SCHEMA,
#                       autoload_with=engine)
#     Post.tags = relationship(Tag, secondary=post_tags, backref="posts")
#
# The join table's two foreign keys may point into different schemas; that is
# fine and needs no special handling.


# Validate every mapping now rather than at the first query. If a cross-schema
# foreign key cannot be resolved, this is where you find out.
configure_mappers()


# =============================================================================
# Validation
# =============================================================================


def main() -> int:
    """Check that cross-schema mappings resolve. Run this file directly."""
    print(f"schemas: {PEOPLE_SCHEMA}, {CONTENT_SCHEMA}")
    for cls in (User, Post, Comment):
        table = cls.__table__
        print(f"  {cls.__name__:10s} -> {table.schema}.{table.name}")

    # Show the reflected foreign keys, including the ones crossing schemas.
    print("\nreflected foreign keys:")
    for cls in (Post, Comment):
        for fk in sorted(cls.__table__.foreign_keys, key=lambda f: f.parent.name):
            crosses = fk.column.table.schema != cls.__table__.schema
            marker = "  (crosses schemas)" if crosses else ""
            print(f"  {cls.__table__.name}.{fk.parent.name} -> "
                  f"{fk.column.table.schema}.{fk.column.table.name}.{fk.column.name}"
                  f"{marker}")

    with session_scope() as session:
        user = session.scalars(select(User)).first()
        if user is None:
            print("\nNo rows yet -- mappings are valid but the table is empty.")
            return 0
        print(f"\nfirst user : {user}")
        print(f"  posts    : {len(user.posts)}")
        print(f"  comments : {len(user.comments)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
