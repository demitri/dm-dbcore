"""SQLAlchemy adapter for PostgreSQL CITEXT type."""

import sqlalchemy.types as types


class PGCitext(types.UserDefinedType):
    """PostgreSQL CITEXT type (case-insensitive text)."""

    def get_col_spec(self, **kwargs):
        return "citext"

    def bind_processor(self, dialect):
        return None

    def result_processor(self, dialect, coltype):
        return None
