import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.service import AiService
from app.dependencies import get_ai_service
from app.main import app
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool


def _client_with_handler(handler) -> TestClient:
    pool = FakePool(tables=["device_metrics"], schema={"device_metrics": []})
    telemetry_service = TelemetryService(repository=TelemetryRepository(pool))
    service = AiService(
        telemetry_service=telemetry_service,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://ollama",
        model="gemma4:latest",
    )
    app.dependency_overrides[get_ai_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_generate_sql_returns_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "SELECT * FROM device_metrics"})

    client = _client_with_handler(handler)

    response = client.post("/api/ai/sql", json={"prompt": "show me all metrics"})

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT * FROM device_metrics"


def test_generate_sql_rejects_non_select_returns_502() -> None:
    # 502 (AiGenerationError), not 400 -- the AI failing to return valid
    # SQL is a different failure than a user hand-writing bad SQL.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    client = _client_with_handler(handler)

    response = client.post("/api/ai/sql", json={"prompt": "delete everything"})

    assert response.status_code == 502


def test_generate_sql_returns_502_on_ollama_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_handler(handler)

    response = client.post("/api/ai/sql", json={"prompt": "anything"})

    assert response.status_code == 502


def test_generate_sql_accepts_variable_hints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "SELECT * FROM device_metrics"})

    client = _client_with_handler(handler)

    response = client.post(
        "/api/ai/sql",
        json={
            "prompt": "temperature for the selected hive",
            "variables": [{"name": "hive_id", "label": "Hive"}],
        },
    )

    assert response.status_code == 200


def test_generate_query_rule_sql_returns_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "SELECT device_id FROM device_metrics GROUP BY device_id"})

    client = _client_with_handler(handler)

    response = client.post(
        "/api/ai/query-rule-sql", json={"prompt": "devices with high average temperature"}
    )

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT device_id FROM device_metrics GROUP BY device_id"


def test_generate_query_rule_sql_rejects_non_select_returns_502() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    client = _client_with_handler(handler)

    response = client.post("/api/ai/query-rule-sql", json={"prompt": "delete everything"})

    assert response.status_code == 502


def test_generate_query_rule_sql_returns_502_on_ollama_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_handler(handler)

    response = client.post("/api/ai/query-rule-sql", json={"prompt": "anything"})

    assert response.status_code == 502


def test_generate_query_rule_sql_accepts_identifiers_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "SELECT hive_id FROM hive_metrics GROUP BY hive_id"})

    client = _client_with_handler(handler)

    response = client.post(
        "/api/ai/query-rule-sql",
        json={"prompt": "average humidity per hive", "identifiers": ["hive_id"]},
    )

    assert response.status_code == 200
