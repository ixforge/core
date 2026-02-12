"""Custom SQLAlchemy types that ensure string results from PostgreSQL network types.

asyncpg returns ipaddress objects for INET/CIDR/MACADDR columns. These
TypeDecorators normalize values back to plain strings so that application
code can rely on ``Mapped[str]`` annotations consistently.
"""

from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import CIDR as PG_CIDR
from sqlalchemy.dialects.postgresql import INET as PG_INET
from sqlalchemy.dialects.postgresql import MACADDR as PG_MACADDR


class INET(TypeDecorator[str]):
    impl = PG_INET
    cache_ok = True

    def process_result_value(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        return str(value)


class CIDR(TypeDecorator[str]):
    impl = PG_CIDR
    cache_ok = True

    def process_result_value(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        return str(value)


class MACADDR(TypeDecorator[str]):
    impl = PG_MACADDR
    cache_ok = True

    def process_result_value(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        return str(value)
