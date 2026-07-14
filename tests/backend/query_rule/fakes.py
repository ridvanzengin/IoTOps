from typing import Any

import asyncpg


class FakeTelemetryRepository:
    """Stands in for TelemetryRepository -- QueryRuleService only ever
    calls execute_match_query(sql, timeout_seconds) on it, so a real
    asyncpg pool/connection isn't needed for these tests."""

    def __init__(
        self,
        rows_by_sql: dict[str, list[dict[str, Any]]] | None = None,
        error_sql: set[str] | None = None,
    ) -> None:
        self.rows_by_sql = rows_by_sql or {}
        self.error_sql = error_sql or set()
        self.calls: list[tuple[str, float]] = []

    async def execute_match_query(self, sql: str, timeout_seconds: float) -> list[dict[str, Any]]:
        self.calls.append((sql, timeout_seconds))
        if sql in self.error_sql:
            raise asyncpg.exceptions.PostgresError("simulated query failure")
        return self.rows_by_sql.get(sql, [])
