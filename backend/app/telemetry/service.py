from datetime import datetime

from app.shared.exceptions import EntityNotFoundError
from app.telemetry.models import TelemetryQueryResult
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
