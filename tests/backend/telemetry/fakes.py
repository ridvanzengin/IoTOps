import re
from typing import Any


class FakeConnection:
    def __init__(self, tables: list[str], table_rows: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.table_rows = table_rows

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "timescaledb_information.hypertables" in query:
            return [{"hypertable_name": t} for t in self.tables]

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
        self, tables: list[str], table_rows: dict[str, list[dict[str, Any]]] | None = None
    ) -> None:
        self.connection = FakeConnection(tables, table_rows or {})

    def acquire(self) -> FakeAcquireContext:
        return FakeAcquireContext(self.connection)
