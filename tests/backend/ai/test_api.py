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


def test_generate_sql_rejects_non_select_returns_400() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    client = _client_with_handler(handler)

    response = client.post("/api/ai/sql", json={"prompt": "delete everything"})

    assert response.status_code == 400


def test_generate_sql_returns_502_on_ollama_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_handler(handler)

    response = client.post("/api/ai/sql", json={"prompt": "anything"})

    assert response.status_code == 502
