from datetime import datetime, timezone

import pytest

from app.shared.exceptions import EntityNotFoundError, InvalidQueryError, QueryExecutionError
from app.telemetry.models import TelemetrySqlQuery
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool


def _service(
    tables: list[str],
    table_rows: dict | None = None,
    schema: dict | None = None,
    query_results: dict | None = None,
    query_errors: dict | None = None,
    query_timeouts: set | None = None,
) -> TelemetryService:
    pool = FakePool(
        tables=tables,
        table_rows=table_rows,
        schema=schema,
        query_results=query_results,
        query_errors=query_errors,
        query_timeouts=query_timeouts,
    )
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


async def test_get_schema_delegates_to_repository() -> None:
    service = _service(
        tables=["device_metrics"],
        schema={"device_metrics": [{"column_name": "time", "data_type": "timestamptz", "is_nullable": "NO"}]},
    )

    schemas = await service.get_schema()

    assert schemas[0].table == "device_metrics"


async def test_run_query_rejects_non_select_statement() -> None:
    service = _service(tables=["device_metrics"])

    with pytest.raises(InvalidQueryError):
        await service.run_query(TelemetrySqlQuery(sql="DELETE FROM device_metrics"))


async def test_run_query_rejects_stacked_statements() -> None:
    service = _service(tables=["device_metrics"])

    with pytest.raises(InvalidQueryError):
        await service.run_query(
            TelemetrySqlQuery(sql="SELECT 1; DROP TABLE device_metrics")
        )


async def test_run_query_executes_valid_select() -> None:
    service = _service(
        tables=["device_metrics"],
        query_results={"SELECT avg(temperature) FROM device_metrics": [{"avg": 21.5}]},
    )

    result = await service.run_query(
        TelemetrySqlQuery(sql="SELECT avg(temperature) FROM device_metrics")
    )

    assert result.columns == ["avg"]
    assert result.rows == [{"avg": 21.5}]


async def test_run_query_wraps_database_errors_as_query_execution_error() -> None:
    service = _service(
        tables=["device_metrics"],
        query_errors={
            "SELECT DISTINCT device FROM device_metrics ORDER BY time": "ORDER BY expressions must appear in select list"
        },
    )

    with pytest.raises(QueryExecutionError):
        await service.run_query(
            TelemetrySqlQuery(sql="SELECT DISTINCT device FROM device_metrics ORDER BY time")
        )


async def test_run_query_wraps_timeout_as_query_execution_error() -> None:
    # Regression guard for the dashboard-panel connection-exhaustion bug:
    # run_query is what actually renders a saved panel's chart data
    # (DashboardService.run_panel_query), and used to have no timeout at
    # all -- a stuck query held a pool connection forever instead of
    # failing fast as a QueryExecutionError like every other query path
    # already does.
    sql = "SELECT * FROM device_metrics"
    service = _service(tables=["device_metrics"], query_timeouts={sql})

    with pytest.raises(QueryExecutionError):
        await service.run_query(TelemetrySqlQuery(sql=sql), timeout_seconds=0.01)


async def test_run_bounded_query_rejects_non_select_statement() -> None:
    service = _service(tables=["device_metrics"])

    with pytest.raises(InvalidQueryError):
        await service.run_bounded_query("DELETE FROM device_metrics")


async def test_run_bounded_query_executes_valid_select_with_row_cap() -> None:
    sql = "SELECT temperature FROM device_metrics"
    service = _service(
        tables=["device_metrics"],
        query_results={sql: [{"temperature": 20.0}, {"temperature": 21.0}, {"temperature": 22.0}]},
    )

    result = await service.run_bounded_query(sql, limit=2)

    assert result.rows == [{"temperature": 20.0}, {"temperature": 21.0}]


async def test_run_bounded_query_wraps_database_errors() -> None:
    sql = "SELECT bogus_column FROM device_metrics"
    service = _service(tables=["device_metrics"], query_errors={sql: "column does not exist"})

    with pytest.raises(QueryExecutionError):
        await service.run_bounded_query(sql)


async def test_run_bounded_query_wraps_timeout_as_query_execution_error() -> None:
    sql = "SELECT * FROM device_metrics"
    service = _service(tables=["device_metrics"], query_timeouts={sql})

    with pytest.raises(QueryExecutionError):
        await service.run_bounded_query(sql, timeout_seconds=0.01)
