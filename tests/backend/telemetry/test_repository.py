from datetime import datetime, timedelta, timezone

import pytest

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


async def test_get_schema_returns_columns_per_table() -> None:
    pool = FakePool(
        tables=["device_metrics"],
        schema={
            "device_metrics": [
                {"column_name": "time", "data_type": "timestamp with time zone", "is_nullable": "NO"},
                {"column_name": "temperature", "data_type": "double precision", "is_nullable": "YES"},
            ]
        },
    )
    repository = TelemetryRepository(pool)

    schemas = await repository.get_schema()

    assert len(schemas) == 1
    assert schemas[0].table == "device_metrics"
    assert schemas[0].columns[0].name == "time"
    assert schemas[0].columns[0].is_nullable is False
    assert schemas[0].columns[1].is_nullable is True


async def test_get_schema_returns_empty_list_for_no_tables() -> None:
    pool = FakePool(tables=[])
    repository = TelemetryRepository(pool)

    assert await repository.get_schema() == []


async def test_execute_readonly_returns_query_results() -> None:
    pool = FakePool(
        tables=["device_metrics"],
        query_results={"SELECT avg(temperature) FROM device_metrics": [{"avg": 21.5}]},
    )
    repository = TelemetryRepository(pool)

    rows = await repository.execute_readonly("SELECT avg(temperature) FROM device_metrics", limit=10)

    assert rows == [{"avg": 21.5}]


async def test_execute_bounded_caps_rows_regardless_of_inner_query() -> None:
    sql = "SELECT time, temperature FROM hive_metrics"
    rows = _rows(5)
    pool = FakePool(tables=["hive_metrics"], query_results={sql: rows})
    repository = TelemetryRepository(pool)

    result = await repository.execute_bounded(sql, limit=2, timeout_seconds=10.0)

    assert result == rows[:2]


async def test_execute_bounded_propagates_timeout() -> None:
    sql = "SELECT time, temperature FROM hive_metrics"
    pool = FakePool(tables=["hive_metrics"], query_timeouts={sql})
    repository = TelemetryRepository(pool)

    with pytest.raises(TimeoutError):
        await repository.execute_bounded(sql, limit=50, timeout_seconds=10.0)


async def test_execute_readonly_propagates_timeout() -> None:
    # Regression guard: this is the actual dashboard-panel-rendering path
    # (DashboardService.run_panel_query -> TelemetryService.run_query), the
    # one query path that used to have no timeout at all -- see
    # docs/development-plan.md's "No runaway-query timeout on interactive
    # Panel queries" Known Issue. A stuck panel query used to pin one of
    # the (deliberately tiny, production-constrained) pool's connections
    # indefinitely instead of failing fast.
    sql = "SELECT time, temperature FROM hive_metrics"
    pool = FakePool(tables=["hive_metrics"], query_timeouts={sql})
    repository = TelemetryRepository(pool)

    with pytest.raises(TimeoutError):
        await repository.execute_readonly(sql, limit=50, timeout_seconds=10.0)


async def test_execute_readonly_keeps_most_recent_rows_when_over_limit() -> None:
    # Regression guard: a panel's SQL is always ordered oldest-first
    # within its time window (see DashboardService._substitute_and_run).
    # When there are more matching rows than `limit`, execute_readonly
    # must keep the *tail* (most recent) rows, not the *front* (oldest) --
    # keeping the front is exactly the bug that made denser panels (more
    # series folded into one query) show a stale chart end-label, since
    # they accumulate rows faster within the same time window.
    sql = "SELECT time, temperature FROM hive_metrics ORDER BY time ASC"
    ordered_rows = [{"time": i, "temperature": 20.0 + i} for i in range(5)]
    pool = FakePool(tables=["hive_metrics"], query_results={sql: ordered_rows})
    repository = TelemetryRepository(pool)

    rows = await repository.execute_readonly(sql, limit=2)

    assert rows == ordered_rows[-2:]


async def test_execute_readonly_strips_trailing_semicolon_before_wrapping() -> None:
    # Regression: AI-generated SQL (and hand-typed SQL out of psql habit)
    # routinely ends with a semicolon. execute_readonly wraps `sql` inside
    # a CTE to add its own OFFSET -- `WITH _panel_rows AS (SELECT ...;) ...`
    # is a syntax error in real Postgres even though the inner SELECT
    # alone is valid, since a semicolon can't appear inside a parenthesized
    # subquery expression. The fake's regex extraction wouldn't itself
    # reproduce that syntax error, so this asserts indirectly: the lookup
    # only succeeds if the semicolon was stripped before wrapping.
    pool = FakePool(
        tables=["device_metrics"],
        query_results={"SELECT avg(temperature) FROM device_metrics": [{"avg": 21.5}]},
    )
    repository = TelemetryRepository(pool)

    rows = await repository.execute_readonly("SELECT avg(temperature) FROM device_metrics;", limit=10)

    assert rows == [{"avg": 21.5}]


async def test_execute_bounded_strips_trailing_semicolon_before_wrapping() -> None:
    sql = "SELECT time, temperature FROM hive_metrics"
    rows = _rows(3)
    pool = FakePool(tables=["hive_metrics"], query_results={sql: rows})
    repository = TelemetryRepository(pool)

    result = await repository.execute_bounded(sql + ";", limit=10, timeout_seconds=10.0)

    assert result == rows
