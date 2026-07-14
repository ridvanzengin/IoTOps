from datetime import datetime
from typing import Any, Protocol

from app.telemetry.models import TelemetryColumn, TelemetryTableSchema


class _Connection(Protocol):
    async def fetch(self, query: str, *args: Any, timeout: float | None = None) -> list[Any]: ...


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

    async def execute_match_query(self, sql: str, timeout_seconds: float) -> list[dict[str, Any]]:
        # Unlike execute_readonly below (Panel-chart-specific: wraps the
        # query to keep only the newest N rows), a Query Rule's full result
        # set *is* the current match set -- every currently-matching row,
        # not a windowed tail -- so no OFFSET/LIMIT wrapping here. Runs
        # with a native asyncpg timeout (unused anywhere else in this
        # repository) since this executes unattended, on a schedule, with
        # nobody watching it hang. See app/query_rule/service.py.
        async with self._pool.acquire() as conn:
            records = await conn.fetch(sql, timeout=timeout_seconds)
        return [dict(record) for record in records]

    async def execute_readonly(self, sql: str, limit: int) -> list[dict[str, Any]]:
        # `sql` (built by DashboardService._substitute_and_run) is already
        # ordered oldest-first within the requested time window -- a plain
        # `LIMIT $1` here would keep the *oldest* rows and silently drop
        # the most recent ones whenever a panel's window holds more rows
        # than `limit` (denser panels -- more series via series_by --
        # accumulate rows faster and get truncated further from "now").
        # OFFSET-ing past everything but the tail keeps the most recent
        # rows instead, without needing to know which column `sql` sorted
        # by. The CTE means `sql` is only evaluated once; its own ORDER BY
        # is preserved through the OFFSET the same way the previous LIMIT-
        # only version already relied on it being preserved through a
        # plain wrapping SELECT.
        query = (
            f"WITH _panel_rows AS ({sql}) "
            f"SELECT * FROM _panel_rows "
            f"OFFSET GREATEST(0, (SELECT count(*) FROM _panel_rows) - $1)"
        )
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
