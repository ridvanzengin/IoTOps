from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.ai.service import AiService
from app.dependencies import get_ai_service
from app.event.repository import EventRepository
from app.event.service import EventService
from app.main import app
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import FakeAnthropicClient, FakeProjectService, message, text_block, tool_use_block
from tests.backend.telemetry.fakes import FakePool


def _event_service() -> EventService:
    database = AsyncMongoMockClient()["iotops"]
    return EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )


def _client_with_handler(handler, anthropic_responses: list | None = None) -> TestClient:
    pool = FakePool(tables=["device_metrics"], schema={"device_metrics": []})
    telemetry_service = TelemetryService(repository=TelemetryRepository(pool))
    service = AiService(
        telemetry_service=telemetry_service,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://ollama",
        model="gemma4:latest",
        event_service=_event_service(),
        project_service=FakeProjectService(),
        anthropic_client=FakeAnthropicClient(anthropic_responses or []),
        anthropic_model="claude-haiku-4-5",
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


def _unused_ollama_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError("Ollama should not be called by the copilot path")


def test_copilot_returns_200_with_answer() -> None:
    client = _client_with_handler(
        _unused_ollama_handler,
        anthropic_responses=[message(text_block("No occurrences in the last 24 hours."))],
    )

    response = client.post(
        "/api/ai/copilot",
        json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "any alerts?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "No occurrences in the last 24 hours."
    assert response.json()["needs_context"] is None


def test_copilot_returns_needs_context_when_flagged() -> None:
    client = _client_with_handler(
        _unused_ollama_handler,
        anthropic_responses=[
            message(tool_use_block("flag_missing_context", {"column": "val1", "reason": "no unit given"})),
            message(text_block("I'm not sure what val1 represents.")),
        ],
    )

    response = client.post(
        "/api/ai/copilot",
        json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "what does val1 mean?"},
    )

    assert response.status_code == 200
    assert response.json()["needs_context"] == {"column": "val1", "reason": "no unit given"}


def test_copilot_returns_502_on_anthropic_failure() -> None:
    error = anthropic.APIConnectionError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    client = _client_with_handler(_unused_ollama_handler, anthropic_responses=[error])

    response = client.post(
        "/api/ai/copilot",
        json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "any alerts?"},
    )

    assert response.status_code == 502
