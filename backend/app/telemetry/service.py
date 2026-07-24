from datetime import datetime

import asyncpg

from app.shared.exceptions import EntityNotFoundError, QueryExecutionError
from app.shared.validators import validate_select_only_sql
from app.telemetry.models import (
    TelemetryQueryResult,
    TelemetrySqlQuery,
    TelemetrySqlQueryResult,
    TelemetryTableSchema,
)
from app.telemetry.repository import TelemetryRepository


class TelemetryService:
    def __init__(self, repository: TelemetryRepository) -> None:
        self._repository = repository

    async def list_tables(self) -> list[str]:
        return await self._repository.list_tables()

    async def query_recent(
        self, table: str, limit: int, since: datetime | None = None
    ) -> TelemetryQueryResult:
        available_tables = await self._repository.list_tables()
        if table not in available_tables:
            raise EntityNotFoundError("TelemetryTable", table)

        rows = await self._repository.query_recent(table, limit, since)
        columns = list(rows[0].keys()) if rows else []
        return TelemetryQueryResult(table=table, columns=columns, rows=rows)

    async def get_schema(self) -> list[TelemetryTableSchema]:
        return await self._repository.get_schema()

    async def run_query(
        self, query: TelemetrySqlQuery, timeout_seconds: float = 10.0
    ) -> TelemetrySqlQueryResult:
        validate_select_only_sql(query.sql)
        try:
            rows = await self._repository.execute_readonly(
                query.sql, query.limit, timeout_seconds
            )
        except (asyncpg.PostgresError, TimeoutError) as exc:
            raise QueryExecutionError(str(exc)) from exc
        columns = list(rows[0].keys()) if rows else []
        return TelemetrySqlQueryResult(columns=columns, rows=rows)

    async def run_bounded_query(
        self, sql: str, limit: int = 50, timeout_seconds: float = 10.0
    ) -> TelemetrySqlQueryResult:
        # Used by the AI Co-pilot's query_telemetry tool -- a row cap and a
        # timeout, same bound run_query above now enforces too (see
        # execute_readonly/execute_bounded in the repository). Distinct
        # from run_query in ordering assumptions only: this wraps arbitrary
        # model-generated SQL with a plain LIMIT (no assumption about which
        # column it's ordered by), where run_query's execute_readonly keeps
        # the newest N rows via an OFFSET, assuming oldest-first ordering
        # (see that method's own comment).
        validate_select_only_sql(sql)
        try:
            rows = await self._repository.execute_bounded(sql, limit, timeout_seconds)
        except (asyncpg.PostgresError, TimeoutError) as exc:
            raise QueryExecutionError(str(exc)) from exc
        columns = list(rows[0].keys()) if rows else []
        return TelemetrySqlQueryResult(columns=columns, rows=rows)
