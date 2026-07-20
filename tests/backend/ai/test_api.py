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
from app.plugin.registry import build_default_registry
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import (
    FakeAnthropicClient,
    FakeAutomaterService,
    FakeCollectorService,
    FakeDashboardService,
    FakeProjectService,
    FakeQueryRuleService,
    message,
    text_block,
    tool_use_block,
)
from tests.backend.telemetry.fakes import FakePool


def _event_service() -> EventService:
    database = AsyncMongoMockClient()["iotops"]
    return EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )


def _client(anthropic_responses: list | None = None) -> TestClient:
    pool = FakePool(tables=["device_metrics"], schema={"device_metrics": []})
    telemetry_service = TelemetryService(repository=TelemetryRepository(pool))
    service = AiService(
        telemetry_service=telemetry_service,
        event_service=_event_service(),
        project_service=FakeProjectService(),
        anthropic_client=FakeAnthropicClient(anthropic_responses or []),
        anthropic_model="claude-haiku-4-5",
        automater_service=FakeAutomaterService(),
        query_rule_service=FakeQueryRuleService(),
        collector_service=FakeCollectorService(),
        plugin_registry=build_default_registry(),
        dashboard_service=FakeDashboardService(),
    )
    app.dependency_overrides[get_ai_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_generate_sql_returns_200() -> None:
    client = _client(anthropic_responses=[message(text_block("SELECT * FROM device_metrics"))])

    response = client.post("/api/ai/sql", json={"prompt": "show me all metrics"})

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT * FROM device_metrics"


def test_generate_sql_rejects_non_select_returns_502() -> None:
    # 502 (AiGenerationError), not 400 -- the AI failing to return valid
    # SQL is a different failure than a user hand-writing bad SQL.
    client = _client(anthropic_responses=[message(text_block("DELETE FROM device_metrics"))])

    response = client.post("/api/ai/sql", json={"prompt": "delete everything"})

    assert response.status_code == 502


def test_generate_sql_returns_502_on_anthropic_failure() -> None:
    error = anthropic.APIConnectionError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    client = _client(anthropic_responses=[error])

    response = client.post("/api/ai/sql", json={"prompt": "anything"})

    assert response.status_code == 502


def test_generate_sql_accepts_variable_hints() -> None:
    client = _client(anthropic_responses=[message(text_block("SELECT * FROM device_metrics"))])

    response = client.post(
        "/api/ai/sql",
        json={
            "prompt": "temperature for the selected hive",
            "variables": [{"name": "hive_id", "label": "Hive"}],
        },
    )

    assert response.status_code == 200


def test_generate_query_rule_sql_returns_200() -> None:
    client = _client(
        anthropic_responses=[message(text_block("SELECT device_id FROM device_metrics GROUP BY device_id"))]
    )

    response = client.post(
        "/api/ai/query-rule-sql", json={"prompt": "devices with high average temperature"}
    )

    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT device_id FROM device_metrics GROUP BY device_id"


def test_generate_query_rule_sql_rejects_non_select_returns_502() -> None:
    client = _client(anthropic_responses=[message(text_block("DELETE FROM device_metrics"))])

    response = client.post("/api/ai/query-rule-sql", json={"prompt": "delete everything"})

    assert response.status_code == 502


def test_generate_query_rule_sql_returns_502_on_anthropic_failure() -> None:
    error = anthropic.APIConnectionError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    client = _client(anthropic_responses=[error])

    response = client.post("/api/ai/query-rule-sql", json={"prompt": "anything"})

    assert response.status_code == 502


def test_generate_query_rule_sql_accepts_identifiers_hint() -> None:
    client = _client(
        anthropic_responses=[message(text_block("SELECT hive_id FROM hive_metrics GROUP BY hive_id"))]
    )

    response = client.post(
        "/api/ai/query-rule-sql",
        json={"prompt": "average humidity per hive", "identifiers": ["hive_id"]},
    )

    assert response.status_code == 200


def test_copilot_returns_200_with_answer() -> None:
    client = _client(
        anthropic_responses=[message(text_block("No occurrences in the last 24 hours."))],
    )

    response = client.post(
        "/api/ai/copilot",
        json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "any alerts?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "No occurrences in the last 24 hours."
    assert response.json()["needs_context"] is None
    assert response.json()["quick_replies"] is None


def test_copilot_returns_quick_replies_when_offered() -> None:
    client = _client(
        anthropic_responses=[
            message(
                text_block(
                    "Real-time or scheduled?\n\n"
                    "[[quick-replies]]\n"
                    "Real-time\n"
                    "Scheduled\n"
                    "[[/quick-replies]]"
                )
            )
        ],
    )

    response = client.post(
        "/api/ai/copilot",
        json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "detect X"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Real-time or scheduled?"
    assert response.json()["quick_replies"] == ["Real-time", "Scheduled"]


def test_copilot_returns_needs_context_when_flagged() -> None:
    client = _client(
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


def test_copilot_returns_suggestion_from_a_plain_conversation_with_no_intent() -> None:
    # Regression: this used to require the client to set intent=
    # "suggest-automation" (only sent by the dedicated "Suggest an
    # automation" button) for suggest_automation to be available at all.
    # A real session showed a plain "I want to create a rule" typed into
    # the ordinary Co-pilot -- no intent, no special entry point -- being
    # told the AI couldn't create rules, because the tool genuinely wasn't
    # in that conversation's tool list. It's always available now.
    client = _client(
        anthropic_responses=[
            message(
                tool_use_block(
                    "suggest_automation",
                    {
                        "kind": "automater_rule",
                        "name": "High temperature",
                        "severity": "high",
                        "identifiers": ["device_id"],
                        "table": "device_metrics",
                        "conditions": [{"column": "temperature", "operator": ">", "value": 90}],
                    },
                )
            ),
            message(text_block("Here's a draft rule.")),
        ],
    )

    response = client.post(
        "/api/ai/copilot",
        json={
            "project_id": "11111111-1111-1111-1111-111111111111",
            "question": "I want to create a rule",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"]["kind"] == "automater_rule"
    assert body["suggestion"]["state"]["table"] == "device_metrics"


def test_copilot_returns_panel_suggestion_with_dashboard_id() -> None:
    dashboard_id = "22222222-2222-2222-2222-222222222222"
    client = _client(
        anthropic_responses=[
            message(
                tool_use_block(
                    "suggest_panel",
                    {
                        "dashboard_id": dashboard_id,
                        "title": "Hive Temperature",
                        "chart_type": "line",
                        "sql": "SELECT time, temperature FROM hive_metrics",
                        "x_axis": "time",
                        "y_axis": "temperature",
                    },
                )
            ),
            message(text_block("Here's a panel draft.")),
        ],
    )

    response = client.post(
        "/api/ai/copilot",
        json={
            "project_id": "11111111-1111-1111-1111-111111111111",
            "question": "chart hive temperature",
            "dashboard_id": dashboard_id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"]["kind"] == "panel"
    assert body["suggestion"]["state"]["dashboard_id"] == dashboard_id


def test_copilot_returns_dashboard_suggestion() -> None:
    client = _client(
        anthropic_responses=[
            message(
                tool_use_block(
                    "suggest_dashboard",
                    {
                        "name": "Apiary Overview",
                        "panels": [
                            {
                                "title": "Hive Temperature",
                                "chart_type": "line",
                                "sql": "SELECT time, temperature FROM hive_metrics",
                                "x_axis": "time",
                                "y_axis": "temperature",
                            },
                            {
                                "title": "Hive Weight",
                                "chart_type": "line",
                                "sql": "SELECT time, weight_kg FROM hive_metrics",
                                "x_axis": "time",
                                "y_axis": "weight_kg",
                            },
                            {
                                "title": "Hive Humidity",
                                "chart_type": "line",
                                "sql": "SELECT time, humidity FROM hive_metrics",
                                "x_axis": "time",
                                "y_axis": "humidity",
                            },
                        ],
                    },
                )
            ),
            message(text_block("Here's a dashboard draft.")),
        ],
    )

    response = client.post(
        "/api/ai/copilot",
        json={
            "project_id": "11111111-1111-1111-1111-111111111111",
            "question": "suggest a dashboard",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"]["kind"] == "dashboard"
    assert body["suggestion"]["state"]["name"] == "Apiary Overview"
    assert len(body["suggestion"]["state"]["panels"]) == 3


def test_copilot_returns_502_on_anthropic_failure() -> None:
    error = anthropic.APIConnectionError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    client = _client(anthropic_responses=[error])

    response = client.post(
        "/api/ai/copilot",
        json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "any alerts?"},
    )

    assert response.status_code == 502
