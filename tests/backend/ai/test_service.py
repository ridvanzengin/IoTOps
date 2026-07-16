from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import anthropic
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.ai.models import AiVariableHint
from app.ai.service import AiService
from app.event.models import Event, EventFlag
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.shared.exceptions import AiGenerationError
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import FakeAnthropicClient, message, text_block, tool_use_block
from tests.backend.telemetry.fakes import FakePool


def _telemetry_service() -> TelemetryService:
    pool = FakePool(
        tables=["device_metrics"],
        schema={
            "device_metrics": [
                {"column_name": "temperature", "data_type": "double precision", "is_nullable": "YES"}
            ]
        },
    )
    return TelemetryService(repository=TelemetryRepository(pool))


def _event_service() -> EventService:
    database = AsyncMongoMockClient()["iotops"]
    return EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )


async def _event_service_with_occurrence(project_id, rule_name: str = "swarm-alert") -> EventService:
    database = AsyncMongoMockClient()["iotops"]
    event = Event(
        project_id=project_id,
        automater_id=uuid4(),
        rule_id=uuid4(),
        rule_name=rule_name,
        table="hive_metrics",
        flag=EventFlag.MATCH,
        matched_at=datetime.now(timezone.utc),
    )
    await database["events"].insert_one(to_document(event))
    return EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )


def _unused_ollama_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError("Ollama should not be called by the copilot path")


def _service(
    handler,
    anthropic_responses: list | None = None,
    event_service: EventService | None = None,
    anthropic_client=None,
) -> AiService:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AiService(
        telemetry_service=_telemetry_service(),
        http_client=client,
        base_url="http://ollama",
        model="gemma4:latest",
        event_service=event_service or _event_service(),
        anthropic_client=anthropic_client or FakeAnthropicClient(anthropic_responses or []),
        anthropic_model="claude-haiku-4-5",
    )


async def test_generate_sql_strips_markdown_fences() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"response": "```sql\nSELECT * FROM device_metrics\n```"}
        )

    sql = await _service(handler).generate_sql("show me all metrics")

    assert sql == "SELECT * FROM device_metrics"


async def test_generate_sql_sends_configured_model() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_sql("count rows")

    assert b'"model":"gemma4:latest"' in captured["body"]


async def test_generate_sql_rejects_non_select_response() -> None:
    # Wrapped into AiGenerationError, not left as InvalidQueryError -- the
    # AI failing to return usable SQL is a different failure than the
    # *user* hand-writing bad SQL, and deserves a message that says so.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_sql("delete everything")


async def test_generate_sql_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_sql("anything")


async def test_generate_sql_wraps_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_sql("anything")


async def test_generate_sql_forwards_variable_hints_into_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_sql(
        "temperature for the selected hive",
        variables=[AiVariableHint(name="hive_id", label="Hive")],
    )

    assert b"$hive_id" in captured["body"]


async def test_generate_query_rule_sql_strips_markdown_fences() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"response": "```sql\nSELECT device_id FROM device_metrics GROUP BY device_id\n```"}
        )

    sql = await _service(handler).generate_query_rule_sql("devices with high average temperature")

    assert sql == "SELECT device_id FROM device_metrics GROUP BY device_id"


async def test_generate_query_rule_sql_uses_the_query_rule_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_query_rule_sql("devices with high average temperature")

    # The query-rule-specific framing, not the Panel/dashboard one -- a
    # cheap way to confirm this went through build_query_rule_sql_prompt,
    # not build_sql_prompt, without re-testing the prompt's own content.
    assert b"scheduled monitoring rule" in captured["body"]


async def test_generate_query_rule_sql_rejects_non_select_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "DELETE FROM device_metrics"})

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_query_rule_sql("delete everything")


async def test_generate_query_rule_sql_gives_actionable_message_on_invalid_sql() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "I need more information about which table."})

    with pytest.raises(AiGenerationError, match="more specific"):
        await _service(handler).generate_query_rule_sql("average humidity is higher than 60")


async def test_generate_query_rule_sql_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AiGenerationError):
        await _service(handler).generate_query_rule_sql("anything")


async def test_generate_query_rule_sql_forwards_identifiers_hint_into_prompt() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"response": "SELECT 1"})

    await _service(handler).generate_query_rule_sql("average humidity per hive", identifiers=["hive_id"])

    assert b"hive_id" in captured["body"]


async def test_answer_copilot_question_returns_final_text_with_no_tool_calls() -> None:
    responses = [message(text_block("There have been no alerts today."))]

    answer = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "any alerts today?", [])

    assert answer == "There have been no alerts today."


async def test_answer_copilot_question_executes_tool_call_then_returns_final_answer() -> None:
    project_id = uuid4()
    event_service = await _event_service_with_occurrence(project_id, rule_name="swarm-alert")
    fake_client = FakeAnthropicClient(
        [
            message(tool_use_block("query_occurrences", {"rule_name": "swarm-alert"})),
            message(text_block("swarm-alert fired once today.")),
        ]
    )

    answer = await _service(
        _unused_ollama_handler, event_service=event_service, anthropic_client=fake_client
    ).answer_copilot_question(project_id, "why did swarm-alert fire?", [])

    assert answer == "swarm-alert fired once today."
    # Second round-trip's messages must carry the tool_result from the first.
    second_call_messages = fake_client.messages.calls[1]["messages"]
    tool_result_messages = [
        m for m in second_call_messages if m["role"] == "user" and isinstance(m["content"], list)
    ]
    assert tool_result_messages
    assert tool_result_messages[-1]["content"][0]["type"] == "tool_result"


async def test_answer_copilot_question_raises_when_iterations_exhausted() -> None:
    # MAX_COPILOT_ITERATIONS is 4 -- queue a tool call for every iteration
    # so the model never produces a final answer.
    responses = [message(tool_use_block("query_occurrences", {})) for _ in range(4)]

    with pytest.raises(AiGenerationError, match="allotted steps"):
        await _service(
            _unused_ollama_handler, anthropic_responses=responses
        ).answer_copilot_question(uuid4(), "keep asking forever", [])


async def test_answer_copilot_question_wraps_anthropic_api_errors() -> None:
    error = anthropic.APIConnectionError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )

    with pytest.raises(AiGenerationError):
        await _service(
            _unused_ollama_handler, anthropic_responses=[error]
        ).answer_copilot_question(uuid4(), "anything", [])


async def test_answer_copilot_question_raises_on_empty_final_answer() -> None:
    responses = [message(text_block(""))]

    with pytest.raises(AiGenerationError):
        await _service(
            _unused_ollama_handler, anthropic_responses=responses
        ).answer_copilot_question(uuid4(), "anything", [])
