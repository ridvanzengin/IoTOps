from datetime import datetime, timedelta, timezone

from app.telemetry.repository import TelemetryRepository
from tests.backend.telemetry.fakes import FakePool

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rows(count: int) -> list[dict]:
    return [
        {"time": NOW - timedelta(minutes=i), "temperature": 20.0 + i}
        for i in range(count)
    ]


async def test_list_tables_returns_hypertable_names() -> None:
    pool = FakePool(tables=["device_metrics", "device_status"])
    repository = TelemetryRepository(pool)

    tables = await repository.list_tables()

    assert tables == ["device_metrics", "device_status"]


async def test_query_recent_orders_by_time_desc_and_limits() -> None:
    pool = FakePool(tables=["device_metrics"], table_rows={"device_metrics": _rows(5)})
    repository = TelemetryRepository(pool)

    rows = await repository.query_recent("device_metrics", limit=2)

    assert len(rows) == 2
    assert rows[0]["time"] == NOW
    assert rows[1]["time"] == NOW - timedelta(minutes=1)


async def test_query_recent_filters_by_since() -> None:
    pool = FakePool(tables=["device_metrics"], table_rows={"device_metrics": _rows(5)})
    repository = TelemetryRepository(pool)

    rows = await repository.query_recent(
        "device_metrics", limit=100, since=NOW - timedelta(minutes=2)
    )

    assert len(rows) == 3


async def test_query_recent_quotes_identifier_safely() -> None:
    pool = FakePool(
        tables=['weird"table'],
        table_rows={'weird"table': _rows(1)},
    )
    repository = TelemetryRepository(pool)

    rows = await repository.query_recent('weird"table', limit=10)

    assert len(rows) == 1
