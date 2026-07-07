import re
from typing import Any

import asyncpg


class FakeConnection:
    def __init__(
        self,
        tables: list[str],
        table_rows: dict[str, list[dict[str, Any]]],
        schema: dict[str, list[dict[str, Any]]] | None = None,
        query_results: dict[str, list[dict[str, Any]]] | None = None,
        query_errors: dict[str, str] | None = None,
    ) -> None:
        self.tables = tables
        self.table_rows = table_rows
        self.schema = schema or {}
        self.query_results = query_results or {}
        self.query_errors = query_errors or {}

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "timescaledb_information.hypertables" in query:
            return [{"hypertable_name": t} for t in self.tables]

        if "information_schema.columns" in query:
            (table_names,) = args
            rows = []
            for table in table_names:
                for column in self.schema.get(table, []):
                    rows.append({"table_name": table, **column})
            return rows

        readonly_match = re.search(r"FROM \((?P<sql>.*)\) AS _q LIMIT \$1", query, re.DOTALL)
        if readonly_match:
            sql = readonly_match.group("sql")
            if sql in self.query_errors:
                raise asyncpg.exceptions.PostgresError(self.query_errors[sql])
            return self.query_results.get(sql, [])

        match = re.search(r'FROM "((?:[^"]|"")*)"', query)
        assert match is not None
        table = match.group(1).replace('""', '"')
        rows = sorted(self.table_rows.get(table, []), key=lambda r: r["time"], reverse=True)

        if "WHERE time >=" in query:
            since, limit = args
            rows = [row for row in rows if row["time"] >= since]
        else:
            (limit,) = args

        return rows[:limit]


class FakeAcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class FakePool:
    def __init__(
        self,
        tables: list[str],
        table_rows: dict[str, list[dict[str, Any]]] | None = None,
        schema: dict[str, list[dict[str, Any]]] | None = None,
        query_results: dict[str, list[dict[str, Any]]] | None = None,
        query_errors: dict[str, str] | None = None,
    ) -> None:
        self.connection = FakeConnection(
            tables, table_rows or {}, schema, query_results, query_errors
        )

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self.connection)
