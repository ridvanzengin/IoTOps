from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from mongomock_motor import AsyncMongoMockClient

from app.ai.tools import (
    run_flag_missing_context,
    run_list_existing_rules,
    run_query_occurrences,
    run_query_telemetry,
    run_suggest_automation,
)
from app.automater.models import Automater, Condition, Rule
from app.event.models import Event, EventFlag, OccurrenceStatus
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.query_rule.models import QueryRule, QueryRuleSchedule
from app.shared.models import InputPlugin, OutputPlugin
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import FakeAutomaterService, FakeQueryRuleService
from tests.backend.telemetry.fakes import FakePool


async def _event_service_with(*events: Event) -> EventService:
    database = AsyncMongoMockClient()["iotops"]
    for event in events:
        await database["events"].insert_one(to_document(event))
    return EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )


def _event(project_id, rule_name: str = "swarm-alert", **overrides) -> Event:
    defaults: dict = {
        "project_id": project_id,
        "automater_id": uuid4(),
        "rule_id": uuid4(),
        "rule_name": rule_name,
        "table": "hive_metrics",
        "flag": EventFlag.MATCH,
        "matched_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Event(**defaults)


async def test_query_occurrences_filters_by_rule_name() -> None:
    project_id = uuid4()
    service = await _event_service_with(
        _event(project_id, rule_name="swarm-alert"),
        _event(project_id, rule_name="low-battery"),
    )

    result = await run_query_occurrences(service, project_id, {"rule_name": "swarm"})

    assert "swarm-alert" in result
    assert "low-battery" not in result


async def test_query_occurrences_filters_by_since_hours() -> None:
    project_id = uuid4()
    service = await _event_service_with(
        _event(project_id, matched_at=datetime.now(timezone.utc) - timedelta(hours=48)),
    )

    result = await run_query_occurrences(service, project_id, {"since_hours": 1})

    assert "No occurrences found" in result


async def test_query_occurrences_caps_limit_at_max() -> None:
    project_id = uuid4()
    service = await _event_service_with(*[_event(project_id) for _ in range(3)])

    # Should not raise despite requesting far more than the cap -- just
    # silently clamps, same as the API's own limit handling elsewhere.
    result = await run_query_occurrences(service, project_id, {"limit": 10_000})

    assert "swarm-alert" in result


async def test_query_occurrences_rejects_invalid_status() -> None:
    project_id = uuid4()
    service = await _event_service_with(_event(project_id))

    result = await run_query_occurrences(service, project_id, {"status": "BOGUS"})

    assert "Invalid status" in result


async def test_query_occurrences_filters_by_valid_status() -> None:
    project_id = uuid4()
    service = await _event_service_with(_event(project_id))

    result = await run_query_occurrences(project_id=project_id, event_service=service, input_={"status": "ACTIVE"})

    assert "swarm-alert" in result
    assert OccurrenceStatus.ACTIVE.value in result


def _telemetry_service(**kwargs) -> TelemetryService:
    pool = FakePool(tables=["device_metrics"], **kwargs)
    return TelemetryService(repository=TelemetryRepository(pool))


async def test_query_telemetry_rejects_non_select_sql() -> None:
    service = _telemetry_service()

    result = await run_query_telemetry(service, {"sql": "DELETE FROM device_metrics"})

    assert "Query rejected" in result


async def test_query_telemetry_returns_formatted_rows() -> None:
    sql = "SELECT temperature FROM device_metrics"
    service = _telemetry_service(query_results={sql: [{"temperature": 21.5}, {"temperature": 22.0}]})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "temperature" in result
    assert "21.5" in result
    assert "22.0" in result


async def test_query_telemetry_reports_no_rows() -> None:
    sql = "SELECT temperature FROM device_metrics WHERE 1=0"
    service = _telemetry_service(query_results={sql: []})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "no rows" in result


async def test_query_telemetry_reports_database_errors() -> None:
    sql = "SELECT bogus_column FROM device_metrics"
    service = _telemetry_service(query_errors={sql: "column does not exist"})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "Query failed" in result


async def test_query_telemetry_reports_timeout() -> None:
    sql = "SELECT * FROM device_metrics"
    service = _telemetry_service(query_timeouts={sql})

    result = await run_query_telemetry(service, {"sql": sql})

    assert "Query failed" in result


def test_flag_missing_context_returns_an_ack() -> None:
    # Purely a structural signal (see AiService.answer_copilot_question,
    # which reads the tool_use's own input, not this return value) -- the
    # model still needs a tool_result to continue the loop.
    result = run_flag_missing_context({"column": "val1", "reason": "no unit given"})

    assert isinstance(result, str)
    assert result


def _automater(project_id, rules: list[Rule]) -> Automater:
    return Automater(
        project_id=project_id,
        name="Test Automater",
        inputs=[InputPlugin(plugin_type="mqtt_consumer", name="in")],
        outputs=[OutputPlugin(plugin_type="celery", name="out")],
        rules=rules,
    )


def _rule(**overrides) -> Rule:
    defaults: dict = {
        "name": "High temperature",
        "table": "device_metrics",
        "conditions": [Condition(column="temperature", operator=">", value=90)],
        "identifiers": ["device_id"],
    }
    defaults.update(overrides)
    return Rule(**defaults)


def _query_rule(project_id, **overrides) -> QueryRule:
    defaults: dict = {
        "project_id": project_id,
        "name": "High average vibration",
        "sql": "SELECT machine_id FROM machine_metrics GROUP BY machine_id HAVING AVG(vibration) > 5",
        "identifiers": ["machine_id"],
        "schedule": QueryRuleSchedule(interval="15m"),
    }
    defaults.update(overrides)
    return QueryRule(**defaults)


async def test_list_existing_rules_reports_none_when_project_has_no_rules() -> None:
    result = await run_list_existing_rules(FakeAutomaterService(), FakeQueryRuleService(), uuid4())

    assert "no existing" in result.lower()


async def test_list_existing_rules_filters_automaters_by_project() -> None:
    project_id = uuid4()
    other_project_automater = _automater(uuid4(), [_rule(name="Other project's rule")])
    this_project_automater = _automater(project_id, [_rule(name="High temperature")])
    automater_service = FakeAutomaterService([other_project_automater, this_project_automater])

    result = await run_list_existing_rules(automater_service, FakeQueryRuleService(), project_id)

    assert "High temperature" in result
    assert "Other project's rule" not in result
    assert "device_metrics" in result
    assert "device_id" in result


async def test_list_existing_rules_includes_query_rules() -> None:
    project_id = uuid4()
    query_rule_service = FakeQueryRuleService([_query_rule(project_id)])

    result = await run_list_existing_rules(FakeAutomaterService(), query_rule_service, project_id)

    assert "High average vibration" in result
    assert "every 15m" in result
    assert "machine_id" in result


def test_suggest_automation_builds_automater_rule_suggestion() -> None:
    project_id = uuid4()

    ack, suggestion = run_suggest_automation(
        project_id,
        {
            "kind": "automater_rule",
            "name": "High hive temperature",
            "severity": "high",
            "identifiers": ["hive_id"],
            "table": "hive_metrics",
            "conditions": [{"column": "temperature", "operator": ">", "value": 38, "join": "AND"}],
        },
    )

    assert isinstance(ack, str) and ack
    assert suggestion is not None
    assert suggestion.kind == "automater_rule"
    assert suggestion.state.project_id == project_id
    assert suggestion.state.table == "hive_metrics"
    assert suggestion.state.conditions[0].column == "temperature"


def test_suggest_automation_builds_query_rule_suggestion() -> None:
    project_id = uuid4()

    ack, suggestion = run_suggest_automation(
        project_id,
        {
            "kind": "query_rule",
            "name": "High average vibration",
            "severity": "medium",
            "identifiers": ["machine_id"],
            "sql": "SELECT machine_id FROM machine_metrics GROUP BY machine_id HAVING AVG(vibration) > 5",
            "schedule_interval": "15m",
        },
    )

    assert isinstance(ack, str) and ack
    assert suggestion is not None
    assert suggestion.kind == "query_rule"
    assert suggestion.state.schedule.interval == "15m"
    assert suggestion.state.schedule.cron is None


def test_suggest_automation_query_rule_supports_cron_schedule() -> None:
    project_id = uuid4()

    _, suggestion = run_suggest_automation(
        project_id,
        {
            "kind": "query_rule",
            "name": "Daily rollup",
            "severity": "low",
            "identifiers": [],
            "sql": "SELECT 1",
            "schedule_cron": "0 3 * * *",
        },
    )

    assert suggestion is not None
    assert suggestion.state.schedule.cron == "0 3 * * *"
    assert suggestion.state.schedule.interval is None


def test_suggest_automation_returns_error_text_and_none_on_invalid_input() -> None:
    ack, suggestion = run_suggest_automation(
        uuid4(),
        {"kind": "automater_rule", "name": "Missing table/conditions", "severity": "low", "identifiers": []},
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()


def test_suggest_automation_returns_error_text_on_unknown_kind() -> None:
    ack, suggestion = run_suggest_automation(
        uuid4(), {"kind": "bogus", "name": "x", "severity": "low", "identifiers": []}
    )

    assert suggestion is None
    assert "couldn't build" in ack.lower()
