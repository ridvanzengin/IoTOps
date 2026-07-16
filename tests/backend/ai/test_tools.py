from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from mongomock_motor import AsyncMongoMockClient

from app.ai.tools import run_flag_missing_context, run_query_occurrences, run_query_telemetry
from app.event.models import Event, EventFlag, OccurrenceStatus
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
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
