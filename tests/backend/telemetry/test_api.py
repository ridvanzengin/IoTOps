from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_telemetry_service
from app.main import app
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool


@pytest.fixture
def client() -> TestClient:
    row = {"time": datetime(2026, 1, 1, tzinfo=timezone.utc), "temperature": 21.5}
    pool = FakePool(
        tables=["device_metrics"],
        table_rows={"device_metrics": [row]},
        schema={
            "device_metrics": [
                {"column_name": "time", "data_type": "timestamptz", "is_nullable": "NO"},
                {"column_name": "temperature", "data_type": "double precision", "is_nullable": "YES"},
            ]
        },
        query_results={"SELECT avg(temperature) FROM device_metrics": [{"avg": 21.5}]},
        query_errors={"SELECT * FROM device_metrics WHERE": "syntax error"},
    )
    service = TelemetryService(repository=TelemetryRepository(pool))
    app.dependency_overrides[get_telemetry_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_tables(client: TestClient) -> None:
    response = client.get("/api/telemetry/tables")

    assert response.status_code == 200
    assert response.json() == ["device_metrics"]


def test_query_table_returns_rows(client: TestClient) -> None:
    response = client.get("/api/telemetry/device_metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["table"] == "device_metrics"
    assert body["rows"][0]["temperature"] == 21.5


def test_query_unknown_table_returns_404(client: TestClient) -> None:
    response = client.get("/api/telemetry/does-not-exist")

    assert response.status_code == 404


def test_query_table_respects_limit_bounds(client: TestClient) -> None:
    response = client.get("/api/telemetry/device_metrics", params={"limit": 0})

    assert response.status_code == 422


def test_get_schema_returns_table_columns(client: TestClient) -> None:
    response = client.get("/api/telemetry/schema")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["table"] == "device_metrics"
    assert body[0]["columns"][0]["name"] == "time"


def test_query_sql_runs_valid_select(client: TestClient) -> None:
    response = client.post(
        "/api/telemetry/query", json={"sql": "SELECT avg(temperature) FROM device_metrics"}
    )

    assert response.status_code == 200
    assert response.json()["rows"] == [{"avg": 21.5}]


def test_query_sql_rejects_non_select(client: TestClient) -> None:
    response = client.post("/api/telemetry/query", json={"sql": "DELETE FROM device_metrics"})

    assert response.status_code == 400


def test_query_sql_returns_400_on_database_error(client: TestClient) -> None:
    response = client.post(
        "/api/telemetry/query", json={"sql": "SELECT * FROM device_metrics WHERE"}
    )

    assert response.status_code == 400
