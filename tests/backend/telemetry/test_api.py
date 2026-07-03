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
    pool = FakePool(tables=["device_metrics"], table_rows={"device_metrics": [row]})
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
