from datetime import datetime
from typing import Any, Protocol

from app.telemetry.models import TelemetryColumn, TelemetryTableSchema


class _Connection(Protocol):
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...


class _Pool(Protocol):
    def acquire(self) -> Any: ...


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class TelemetryRepository:
    def __init__(self, pool: _Pool) -> None:
        self._pool = pool

    async def list_tables(self) -> list[str]:
        query = "SELECT hypertable_name FROM timescaledb_information.hypertables ORDER BY hypertable_name"
        async with self._pool.acquire() as conn:
            records = await conn.fetch(query)
        return [record["hypertable_name"] for record in records]

    async def get_schema(self) -> list[TelemetryTableSchema]:
        tables = await self.list_tables()
        if not tables:
            return []

        query = (
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ANY($1) "
            "ORDER BY table_name, ordinal_position"
        )
        async with self._pool.acquire() as conn:
            records = await conn.fetch(query, tables)

        schemas: dict[str, list[TelemetryColumn]] = {table: [] for table in tables}
        for record in records:
            schemas[record["table_name"]].append(
                TelemetryColumn(
                    name=record["column_name"],
                    data_type=record["data_type"],
                    is_nullable=record["is_nullable"] in (True, "YES"),
                )
            )
        return [
            TelemetryTableSchema(table=table, columns=columns)
            for table, columns in schemas.items()
        ]

    async def execute_readonly(self, sql: str, limit: int) -> list[dict[str, Any]]:
        query = f"SELECT * FROM ({sql}) AS _q LIMIT $1"
        async with self._pool.acquire() as conn:
            records = await conn.fetch(query, limit)
        return [dict(record) for record in records]

    async def query_recent(
        self, table: str, limit: int, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        identifier = _quote_identifier(table)
        if since is not None:
            query = f"SELECT * FROM {identifier} WHERE time >= $1 ORDER BY time DESC LIMIT $2"
            args: tuple[Any, ...] = (since, limit)
        else:
            query = f"SELECT * FROM {identifier} ORDER BY time DESC LIMIT $1"
            args = (limit,)

        async with self._pool.acquire() as conn:
            records = await conn.fetch(query, *args)
        return [dict(record) for record in records]
