"""SQLAlchemy adapter for PostgreSQL XML type."""

import sqlalchemy.types as types


class PGXML(types.UserDefinedType):
    """PostgreSQL XML type (native XML storage)."""

    cache_ok = True

    def get_col_spec(self, **kwargs):
        return "xml"

    def bind_processor(self, dialect):
        return None

    def result_processor(self, dialect, coltype):
        return None
