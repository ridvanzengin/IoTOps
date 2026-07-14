from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.dependencies import get_query_rule_service
from app.event.repository import EventRepository
from app.main import app
from app.query_rule.repository import QueryRuleRepository
from app.query_rule.service import QueryRuleService
from app.telemetry.repository import TelemetryRepository
from tests.backend.query_rule.fakes import FakeTelemetryRepository

VALID_PAYLOAD = {
    "project_id": str(uuid4()),
    "name": "high-wind-scheduled",
    "sql": "SELECT station_id FROM weather_metrics",
    "identifiers": ["station_id"],
    "schedule": {"interval": "5m"},
}


def _build_service() -> QueryRuleService:
    database = AsyncMongoMockClient()["iotops"]
    return QueryRuleService(
        repository=QueryRuleRepository(database),
        # Not exercised by these CRUD-only API tests.
        telemetry_repository=TelemetryRepository(pool=None),  # type: ignore[arg-type]
        event_repository=EventRepository(database),
    )


@pytest.fixture
def client() -> TestClient:
    service = _build_service()
    app.dependency_overrides[get_query_rule_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_query_rule_returns_201(client: TestClient) -> None:
    response = client.post("/api/query-rule", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "high-wind-scheduled"
    assert body["schedule"]["interval"] == "5m"


def test_create_query_rule_rejects_non_select_sql() -> None:
    service = _build_service()
    app.dependency_overrides[get_query_rule_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/api/query-rule", json={**VALID_PAYLOAD, "sql": "DROP TABLE weather_metrics"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_get_query_rule(client: TestClient) -> None:
    created = client.post("/api/query-rule", json=VALID_PAYLOAD).json()

    response = client.get(f"/api/query-rule/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_query_rule_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/query-rule/{uuid4()}")

    assert response.status_code == 404


def test_list_query_rules(client: TestClient) -> None:
    client.post("/api/query-rule", json=VALID_PAYLOAD)
    client.post("/api/query-rule", json={**VALID_PAYLOAD, "name": "second-rule"})

    response = client.get("/api/query-rule")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_update_query_rule(client: TestClient) -> None:
    created = client.post("/api/query-rule", json=VALID_PAYLOAD).json()

    response = client.put(f"/api/query-rule/{created['id']}", json={**VALID_PAYLOAD, "name": "renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_delete_query_rule(client: TestClient) -> None:
    created = client.post("/api/query-rule", json=VALID_PAYLOAD).json()

    response = client.delete(f"/api/query-rule/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/query-rule/{created['id']}").status_code == 404


def test_preview_query_rule_sql_returns_columns_and_rows() -> None:
    database = AsyncMongoMockClient()["iotops"]
    sql = "SELECT station_id FROM weather_metrics"
    service = QueryRuleService(
        repository=QueryRuleRepository(database),
        telemetry_repository=FakeTelemetryRepository({sql: [{"station_id": "wx-01"}]}),  # type: ignore[arg-type]
        event_repository=EventRepository(database),
    )
    app.dependency_overrides[get_query_rule_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/api/query-rule/preview", json={"sql": sql})
        assert response.status_code == 200
        assert response.json() == {"columns": ["station_id"], "rows": [{"station_id": "wx-01"}]}
    finally:
        app.dependency_overrides.clear()


def test_preview_query_rule_sql_rejects_non_select_sql(client: TestClient) -> None:
    response = client.post("/api/query-rule/preview", json={"sql": "DROP TABLE weather_metrics"})

    assert response.status_code == 400
