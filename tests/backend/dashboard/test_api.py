from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.dashboard.repository import DashboardRepository
from app.dashboard.service import DashboardService
from app.dependencies import get_dashboard_service
from app.main import app
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool

VALID_PAYLOAD = {
    "project_id": str(uuid4()),
    "name": "Hive Overview",
    "description": "",
    "variables": [],
    "panels": [],
    "layout": {},
}

PANEL_PAYLOAD = {
    "title": "Temperature",
    "chart": {"type": "line", "title": "Temperature", "x_axis": "time", "y_axis": "temperature"},
    "query": {"sql": "SELECT * FROM device_metrics"},
    "time_range": "1h",
    "refresh_interval": 0,
    "position": {"x": 0, "y": 0, "width": 6, "height": 4},
}


@pytest.fixture
def client() -> TestClient:
    database = AsyncMongoMockClient()["iotops"]
    pool = FakePool(tables=["device_metrics"])
    telemetry_service = TelemetryService(repository=TelemetryRepository(pool))
    service = DashboardService(
        repository=DashboardRepository(database), telemetry_service=telemetry_service
    )
    app.dependency_overrides[get_dashboard_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_dashboard_returns_201(client: TestClient) -> None:
    response = client.post("/api/dashboard", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["name"] == "Hive Overview"


def test_create_dashboard_with_duplicate_name_returns_409(client: TestClient) -> None:
    client.post("/api/dashboard", json=VALID_PAYLOAD)

    response = client.post("/api/dashboard", json=VALID_PAYLOAD)

    assert response.status_code == 409


def test_get_missing_dashboard_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/dashboard/{uuid4()}")

    assert response.status_code == 404


def test_list_dashboards_returns_created_dashboard(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == [created["id"]]


def test_update_dashboard_renames_it(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.put(
        f"/api/dashboard/{created['id']}",
        json={**VALID_PAYLOAD, "name": "Renamed Dashboard"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Dashboard"


def test_add_panel_returns_dashboard_with_panel(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.post(f"/api/dashboard/{created['id']}/panel", json=PANEL_PAYLOAD)

    assert response.status_code == 201
    assert len(response.json()["panels"]) == 1


def test_update_panel_edits_it(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()
    with_panel = client.post(f"/api/dashboard/{created['id']}/panel", json=PANEL_PAYLOAD).json()
    panel_id = with_panel["panels"][0]["id"]

    response = client.put(
        f"/api/dashboard/{created['id']}/panel/{panel_id}",
        json={**PANEL_PAYLOAD, "title": "Renamed Panel"},
    )

    assert response.status_code == 200
    assert response.json()["panels"][0]["title"] == "Renamed Panel"


def test_remove_panel_deletes_it(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()
    with_panel = client.post(f"/api/dashboard/{created['id']}/panel", json=PANEL_PAYLOAD).json()
    panel_id = with_panel["panels"][0]["id"]

    response = client.delete(f"/api/dashboard/{created['id']}/panel/{panel_id}")

    assert response.status_code == 200
    assert response.json()["panels"] == []


def test_save_layout_updates_positions(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()
    with_panel = client.post(f"/api/dashboard/{created['id']}/panel", json=PANEL_PAYLOAD).json()
    panel_id = with_panel["panels"][0]["id"]

    response = client.put(
        f"/api/dashboard/{created['id']}/layout",
        json={
            "panels": [{"id": panel_id, "position": {"x": 6, "y": 0, "width": 6, "height": 4}}],
            "layout": {"cols": 12},
        },
    )

    assert response.status_code == 200
    assert response.json()["panels"][0]["position"]["x"] == 6
    assert response.json()["layout"] == {"cols": 12}


def test_delete_dashboard_removes_it(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.delete(f"/api/dashboard/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/dashboard/{created['id']}").status_code == 404


def test_run_panel_query_returns_rows(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()
    with_panel = client.post(f"/api/dashboard/{created['id']}/panel", json=PANEL_PAYLOAD).json()
    panel_id = with_panel["panels"][0]["id"]

    response = client.post(
        f"/api/dashboard/{created['id']}/panel/{panel_id}/query",
        json={"time_range": "1h", "variable_values": {}},
    )

    assert response.status_code == 200
    assert response.json() == {"columns": [], "rows": []}


def test_run_panel_query_missing_panel_returns_404(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.post(
        f"/api/dashboard/{created['id']}/panel/{uuid4()}/query",
        json={"time_range": "1h", "variable_values": {}},
    )

    assert response.status_code == 404


def test_preview_query_returns_rows(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.post(
        f"/api/dashboard/{created['id']}/preview-query",
        json={"sql": "SELECT * FROM device_metrics", "limit": 100},
    )

    assert response.status_code == 200
    assert response.json() == {"columns": [], "rows": []}


def test_resolve_variable_options_returns_empty_list_by_default(client: TestClient) -> None:
    created = client.post("/api/dashboard", json=VALID_PAYLOAD).json()

    response = client.post(
        f"/api/dashboard/{created['id']}/variables/options",
        json={"table": "device_metrics", "value_column": "hive"},
    )

    assert response.status_code == 200
    assert response.json() == {"options": []}


def test_create_dashboard_rejects_duplicate_variable_names(client: TestClient) -> None:
    response = client.post(
        "/api/dashboard",
        json={
            **VALID_PAYLOAD,
            "variables": [
                {"name": "hive", "label": "Hive A", "table": "hives", "value_column": "id"},
                {"name": "hive", "label": "Hive B", "table": "hives", "value_column": "id"},
            ],
        },
    )

    assert response.status_code == 422
