from datetime import datetime, timezone

import pytest

from app.shared.exceptions import EntityNotFoundError
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool


def _service(tables: list[str], table_rows: dict | None = None) -> TelemetryService:
    pool = FakePool(tables=tables, table_rows=table_rows)
    return TelemetryService(repository=TelemetryRepository(pool))


async def test_list_tables_delegates_to_repository() -> None:
    service = _service(tables=["device_metrics"])

    assert await service.list_tables() == ["device_metrics"]


async def test_query_recent_rejects_unknown_table() -> None:
    service = _service(tables=["device_metrics"])

    with pytest.raises(EntityNotFoundError):
        await service.query_recent("does-not-exist", limit=10)


async def test_query_recent_returns_columns_and_rows() -> None:
    row = {"time": datetime(2026, 1, 1, tzinfo=timezone.utc), "temperature": 21.5}
    service = _service(tables=["device_metrics"], table_rows={"device_metrics": [row]})

    result = await service.query_recent("device_metrics", limit=10)

    assert result.table == "device_metrics"
    assert set(result.columns) == {"time", "temperature"}
    assert result.rows == [row]


async def test_query_recent_returns_empty_columns_for_no_rows() -> None:
    service = _service(tables=["device_metrics"], table_rows={"device_metrics": []})

    result = await service.query_recent("device_metrics", limit=10)

    assert result.columns == []
    assert result.rows == []
