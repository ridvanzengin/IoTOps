from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import anthropic
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.ai.models import AiVariableHint
from app.ai.service import MAX_COPILOT_ITERATIONS, AiService
from app.collector.models import Collector
from app.event.models import Event, EventFlag
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.plugin.registry import build_default_registry
from app.shared.exceptions import AiGenerationError
from app.shared.models import InputPlugin, OutputPlugin
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import (
    FakeAnthropicClient,
    FakeAutomaterService,
    FakeCollectorService,
    FakeProjectService,
    FakeQueryRuleService,
    message,
    text_block,
    tool_use_block,
)
from tests.backend.telemetry.fakes import FakePool


def _telemetry_service() -> TelemetryService:
    # Two tables, only one of which any given test's collector fixture
    # covers -- lets the project-scoping tests assert an out-of-project
    # table is excluded, not just that an in-project one is included.
    pool = FakePool(
        tables=["device_metrics", "vehicle_metrics"],
        schema={
            "device_metrics": [
                {"column_name": "temperature", "data_type": "double precision", "is_nullable": "YES"}
            ],
            "vehicle_metrics": [
                {"column_name": "fuel_level", "data_type": "double precision", "is_nullable": "YES"}
            ],
        },
    )
    return TelemetryService(repository=TelemetryRepository(pool))


def _collector(project_id: UUID, table: str = "device_metrics") -> Collector:
    return Collector(
        project_id=project_id,
        name="Test Collector",
        inputs=[InputPlugin(plugin_type="mqtt", name="in", configuration={"name_override": table})],
        outputs=[OutputPlugin(plugin_type="timescaledb", name="out")],
    )


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
    ai_context: str = "",
    automater_service=None,
    query_rule_service=None,
    collector_service=None,
) -> AiService:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AiService(
        telemetry_service=_telemetry_service(),
        http_client=client,
        base_url="http://ollama",
        model="gemma4:latest",
        event_service=event_service or _event_service(),
        project_service=FakeProjectService(ai_context),
        anthropic_client=anthropic_client or FakeAnthropicClient(anthropic_responses or []),
        anthropic_model="claude-haiku-4-5",
        automater_service=automater_service or FakeAutomaterService(),
        query_rule_service=query_rule_service or FakeQueryRuleService(),
        # Empty by default -- no collector means no table is "in scope"
        # for the project, which is the correct/honest behavior (see
        # test_answer_copilot_question_scopes_schema_to_project_collectors
        # for the non-empty case). No existing test asserts on the
        # copilot path's schema content, only prompts.py's own tests
        # (which call build_copilot_system_prompt directly, bypassing
        # this scoping).
        collector_service=collector_service or FakeCollectorService(),
        plugin_registry=build_default_registry(),
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

    answer, needs_context, suggestion, quick_replies = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "any alerts today?", [])

    assert answer == "There have been no alerts today."
    assert needs_context is None
    assert suggestion is None
    assert quick_replies is None


async def test_answer_copilot_question_executes_tool_call_then_returns_final_answer() -> None:
    project_id = uuid4()
    event_service = await _event_service_with_occurrence(project_id, rule_name="swarm-alert")
    fake_client = FakeAnthropicClient(
        [
            message(tool_use_block("query_occurrences", {"rule_name": "swarm-alert"})),
            message(text_block("swarm-alert fired once today.")),
        ]
    )

    answer, needs_context, suggestion, quick_replies = await _service(
        _unused_ollama_handler, event_service=event_service, anthropic_client=fake_client
    ).answer_copilot_question(project_id, "why did swarm-alert fire?", [])

    assert answer == "swarm-alert fired once today."
    assert needs_context is None
    assert suggestion is None
    assert quick_replies is None
    # Second round-trip's messages must carry the tool_result from the first.
    second_call_messages = fake_client.messages.calls[1]["messages"]
    tool_result_messages = [
        m for m in second_call_messages if m["role"] == "user" and isinstance(m["content"], list)
    ]
    assert tool_result_messages
    assert tool_result_messages[-1]["content"][0]["type"] == "tool_result"


async def test_answer_copilot_question_raises_when_iterations_exhausted() -> None:
    # Queue a tool call for every iteration so the model never produces a
    # final answer.
    responses = [message(tool_use_block("query_occurrences", {})) for _ in range(MAX_COPILOT_ITERATIONS)]

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


async def test_answer_copilot_question_surfaces_flag_missing_context() -> None:
    responses = [
        message(tool_use_block("flag_missing_context", {"column": "val1", "reason": "no unit given"})),
        message(text_block("I'm not sure what val1 represents.")),
    ]

    answer, needs_context, suggestion, quick_replies = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "what does val1 mean?", [])

    assert answer == "I'm not sure what val1 represents."
    assert needs_context is not None
    assert needs_context.column == "val1"
    assert needs_context.reason == "no unit given"
    assert suggestion is None
    assert quick_replies is None


async def test_answer_copilot_question_forwards_ai_context_into_system_prompt() -> None:
    fake_client = FakeAnthropicClient([message(text_block("Answer."))])

    await _service(
        _unused_ollama_handler,
        anthropic_client=fake_client,
        ai_context="val1 is coolant temperature in Celsius",
    ).answer_copilot_question(uuid4(), "what is val1?", [])

    system_prompt = fake_client.messages.calls[0]["system"]
    assert "val1 is coolant temperature in Celsius" in system_prompt


async def test_answer_copilot_question_scopes_schema_to_project_collectors() -> None:
    # Regression: the Co-pilot used to get the *global* TimescaleDB schema
    # regardless of which project was open (TimescaleDB has no per-project
    # table isolation), so a beekeeping project's system prompt would also
    # list an unrelated project's vehicle/solar tables -- observed live as
    # the model asking about vehicle theft for a hive-theft question. Scope
    # to exactly the tables this project's own Collectors cover.
    project_id = uuid4()
    fake_client = FakeAnthropicClient([message(text_block("Answer."))])

    await _service(
        _unused_ollama_handler,
        anthropic_client=fake_client,
        collector_service=FakeCollectorService([_collector(project_id, table="device_metrics")]),
    ).answer_copilot_question(project_id, "what tables can you see?", [])

    system_prompt = fake_client.messages.calls[0]["system"]
    assert "device_metrics" in system_prompt
    assert "vehicle_metrics" not in system_prompt


async def test_answer_copilot_question_ignores_other_projects_collectors() -> None:
    project_id = uuid4()
    other_project_id = uuid4()
    fake_client = FakeAnthropicClient([message(text_block("Answer."))])

    await _service(
        _unused_ollama_handler,
        anthropic_client=fake_client,
        collector_service=FakeCollectorService(
            [
                _collector(project_id, table="device_metrics"),
                _collector(other_project_id, table="vehicle_metrics"),
            ]
        ),
    ).answer_copilot_question(project_id, "what tables can you see?", [])

    system_prompt = fake_client.messages.calls[0]["system"]
    assert "device_metrics" in system_prompt
    assert "vehicle_metrics" not in system_prompt


async def test_answer_copilot_question_always_includes_suggestion_tools() -> None:
    # Regression: these used to be gated behind an `intent` flag only set
    # when the panel was opened via the dedicated "Suggest an automation"
    # button. A real session showed a plain "I want to create a rule"
    # typed into the ordinary Co-pilot getting no suggest_automation tool
    # at all, and the model correctly (from its own perspective) said it
    # couldn't create one. Every conversation gets the full tool set now,
    # regardless of how it started.
    fake_client = FakeAnthropicClient([message(text_block("Answer."))])

    await _service(
        _unused_ollama_handler, anthropic_client=fake_client
    ).answer_copilot_question(uuid4(), "any alerts?", [])

    tool_names = {tool["name"] for tool in fake_client.messages.calls[0]["tools"]}
    assert "suggest_automation" in tool_names
    assert "list_existing_rules" in tool_names


async def test_answer_copilot_question_surfaces_automater_rule_suggestion() -> None:
    project_id = uuid4()
    responses = [
        message(
            tool_use_block(
                "suggest_automation",
                {
                    "kind": "automater_rule",
                    "name": "High hive temperature",
                    "severity": "high",
                    "identifiers": ["hive_id"],
                    "table": "hive_metrics",
                    "conditions": [{"column": "temperature", "operator": ">", "value": 38}],
                },
            )
        ),
        message(text_block("I've drafted a rule for you.")),
    ]

    answer, needs_context, suggestion, _ = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(project_id, "watch for hot hives", [])

    assert needs_context is None
    assert suggestion is not None
    assert suggestion.kind == "automater_rule"
    assert suggestion.state.table == "hive_metrics"
    assert suggestion.state.project_id == project_id
    # The prose stays clean for display, but the raw answer round-tripped
    # as history carries a machine-readable recap so a later refinement
    # turn is grounded on the exact prior proposal, not a paraphrase --
    # see AiService's _SUGGESTION_CONTEXT_START/_END.
    assert answer.startswith("I've drafted a rule for you.")
    assert "[[suggestion-context]]" in answer
    assert "hive_metrics" in answer


async def test_answer_copilot_question_surfaces_query_rule_suggestion() -> None:
    project_id = uuid4()
    responses = [
        message(
            tool_use_block(
                "suggest_automation",
                {
                    "kind": "query_rule",
                    "name": "High average vibration",
                    "severity": "medium",
                    "identifiers": ["machine_id"],
                    "sql": "SELECT machine_id FROM machine_metrics GROUP BY machine_id HAVING AVG(vibration) > 5",
                    "schedule_interval": "15m",
                },
            )
        ),
        message(text_block("Here's a scheduled rule draft.")),
    ]

    _, _, suggestion, _ = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(project_id, "watch for noisy machines", [])

    assert suggestion is not None
    assert suggestion.kind == "query_rule"
    assert suggestion.state.schedule.interval == "15m"
    assert suggestion.state.schedule.cron is None


async def test_answer_copilot_question_invalid_suggestion_lets_model_retry() -> None:
    project_id = uuid4()
    responses = [
        message(tool_use_block("suggest_automation", {"kind": "automater_rule", "name": "Bad"})),
        message(text_block("Let me try again.")),
    ]

    answer, _, suggestion, _ = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(project_id, "suggest something", [])

    assert suggestion is None
    assert answer == "Let me try again."


async def test_answer_copilot_question_keeps_suggestion_when_final_answer_is_only_quick_replies() -> None:
    # Regression: if the model's entire final turn is just a
    # [[quick-replies]] block with no prose, extraction used to leave an
    # empty `answer`, which raised AiGenerationError and discarded a
    # suggestion already built earlier in the same turn.
    project_id = uuid4()
    responses = [
        message(
            tool_use_block(
                "suggest_automation",
                {
                    "kind": "automater_rule",
                    "name": "High hive temperature",
                    "severity": "high",
                    "identifiers": ["hive_id"],
                    "table": "hive_metrics",
                    "conditions": [{"column": "temperature", "operator": ">", "value": 38}],
                },
            )
        ),
        message(text_block("[[quick-replies]]\nLooks good\nAdjust it\n[[/quick-replies]]")),
    ]

    answer, _, suggestion, quick_replies = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(project_id, "suggest something", [])

    assert suggestion is not None
    assert answer
    assert "[[quick-replies]]" not in answer
    assert quick_replies == ["Looks good", "Adjust it"]


async def test_answer_copilot_question_extracts_quick_replies() -> None:
    responses = [
        message(
            text_block(
                "Would you like option A or option B?\n\n"
                "[[quick-replies]]\n"
                "Option A: real-time rule\n"
                "Option B: scheduled rule\n"
                "[[/quick-replies]]"
            )
        )
    ]

    answer, _, _, quick_replies = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "how should I detect this?", [])

    assert answer == "Would you like option A or option B?"
    assert "[[quick-replies]]" not in answer
    assert quick_replies == ["Option A: real-time rule", "Option B: scheduled rule"]


async def test_answer_copilot_question_omits_quick_replies_when_not_offered() -> None:
    responses = [message(text_block("No occurrences today."))]

    _, _, _, quick_replies = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "any alerts?", [])

    assert quick_replies is None


async def test_answer_copilot_question_strips_every_quick_replies_block() -> None:
    # Mirrors the suggestion-context marker's own already-observed bug:
    # the model can echo a bracket-delimited block it saw in its own
    # history. Labels come from the first (real) block, but every
    # occurrence must be stripped from the displayed/stored text, not
    # just the first.
    responses = [
        message(
            text_block(
                "Echoed block below, then the real one.\n\n"
                "[[quick-replies]]\n"
                "Stale option\n"
                "[[/quick-replies]]\n\n"
                "Which would you like?\n\n"
                "[[quick-replies]]\n"
                "Option A\n"
                "Option B\n"
                "[[/quick-replies]]"
            )
        )
    ]

    answer, _, _, quick_replies = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "how should I detect this?", [])

    assert "[[quick-replies]]" not in answer
    assert "[[/quick-replies]]" not in answer
    assert quick_replies == ["Option A", "Option B"]


async def test_answer_copilot_question_handles_a_long_cross_table_suggestion_chain() -> None:
    # Regression: a real cross-table request ("weight loss + elevated
    # sound together") exhausted the old cap of 4 tool-call iterations in
    # production. Queue a chain one shorter than the current cap to prove
    # it now fits comfortably.
    from app.ai.service import MAX_COPILOT_ITERATIONS

    responses = [
        message(tool_use_block("list_existing_rules", {})),
        message(tool_use_block("query_telemetry", {"sql": "SELECT avg(sound_level) FROM hive_metrics"})),
        message(tool_use_block("query_telemetry", {"sql": "SELECT avg(weight_kg) FROM hive_metrics"})),
        message(
            tool_use_block(
                "suggest_automation",
                {
                    "kind": "query_rule",
                    "name": "hornet-attack",
                    "severity": "high",
                    "identifiers": ["hive_id"],
                    "sql": "SELECT hive_id FROM hive_metrics GROUP BY hive_id HAVING avg(sound_level) > 65",
                    "schedule_interval": "5m",
                },
            )
        ),
        message(text_block("Drafted.")),
    ]
    assert len(responses) < MAX_COPILOT_ITERATIONS

    answer, _, suggestion, _ = await _service(
        _unused_ollama_handler, anthropic_responses=responses
    ).answer_copilot_question(uuid4(), "detect hornet attacks", [])

    assert answer.startswith("Drafted.")
    assert suggestion is not None
