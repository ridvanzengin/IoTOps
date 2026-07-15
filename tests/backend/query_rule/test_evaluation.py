from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.automater.models import ResolveMode
from app.event.models import EventFlag, OccurrenceStatus
from app.event.repository import EventRepository, to_document
from app.query_rule.models import QueryRule, QueryRuleSchedule
from app.query_rule.repository import QueryRuleRepository
from app.query_rule.service import QueryRuleService, _is_due, _parse_duration
from app.shared.exceptions import QueryExecutionError
from tests.backend.query_rule.fakes import FakeTelemetryRepository


def _query_rule(**overrides: object) -> QueryRule:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "name": "high-wind-scheduled",
        "sql": "SELECT station_id, wind_speed_kmh FROM weather_metrics",
        "identifiers": ["station_id"],
        "schedule": QueryRuleSchedule(interval="5m"),
    }
    defaults.update(overrides)
    return QueryRule(**defaults)


async def _service(
    query_rules: list[QueryRule] | None = None,
    rows_by_sql: dict[str, list[dict[str, Any]]] | None = None,
    error_sql: set[str] | None = None,
) -> tuple[QueryRuleService, QueryRuleRepository, EventRepository, FakeTelemetryRepository]:
    database = AsyncMongoMockClient()["iotops"]
    repository = QueryRuleRepository(database)
    for query_rule in query_rules or []:
        await repository.create(query_rule)
    event_repository = EventRepository(database)
    fake_telemetry = FakeTelemetryRepository(rows_by_sql, error_sql)
    service = QueryRuleService(
        repository=repository,
        telemetry_repository=fake_telemetry,  # type: ignore[arg-type]
        event_repository=event_repository,
    )
    return service, repository, event_repository, fake_telemetry


# --- _parse_duration ---


def test_parse_duration_accepts_seconds_minutes_hours() -> None:
    assert _parse_duration("30s") == timedelta(seconds=30)
    assert _parse_duration("5m") == timedelta(minutes=5)
    assert _parse_duration("2h") == timedelta(hours=2)


def test_parse_duration_rejects_unsupported_unit() -> None:
    from app.shared.exceptions import InvalidOperationError

    with pytest.raises(InvalidOperationError):
        _parse_duration("5d")


def test_parse_duration_rejects_non_numeric() -> None:
    from app.shared.exceptions import InvalidOperationError

    with pytest.raises(InvalidOperationError):
        _parse_duration("fivem")


# --- _is_due ---


def test_is_due_never_evaluated_is_always_due() -> None:
    query_rule = _query_rule()
    assert _is_due(query_rule, datetime.now(timezone.utc)) is True


def test_is_due_disabled_is_never_due() -> None:
    query_rule = _query_rule(enabled=False, last_evaluated_at=None)
    assert _is_due(query_rule, datetime.now(timezone.utc)) is False


def test_is_due_interval_not_yet_elapsed() -> None:
    now = datetime.now(timezone.utc)
    query_rule = _query_rule(last_evaluated_at=now - timedelta(minutes=1))
    assert _is_due(query_rule, now) is False


def test_is_due_interval_elapsed() -> None:
    now = datetime.now(timezone.utc)
    query_rule = _query_rule(last_evaluated_at=now - timedelta(minutes=10))
    assert _is_due(query_rule, now) is True


def test_is_due_cron_not_yet_matched() -> None:
    now = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
    query_rule = _query_rule(schedule=QueryRuleSchedule(cron="0 3 * * *"), last_evaluated_at=now)
    assert _is_due(query_rule, now) is False


def test_is_due_cron_matched() -> None:
    last_evaluated_at = datetime(2026, 7, 13, 3, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 14, 3, 1, tzinfo=timezone.utc)
    query_rule = _query_rule(schedule=QueryRuleSchedule(cron="0 3 * * *"), last_evaluated_at=last_evaluated_at)
    assert _is_due(query_rule, now) is True


# --- execute ---


async def test_execute_returns_rows() -> None:
    sql = "SELECT station_id FROM weather_metrics"
    service, *_ = await _service(rows_by_sql={sql: [{"station_id": "wx-01"}]})

    rows = await service.execute(sql)

    assert rows == [{"station_id": "wx-01"}]


async def test_execute_wraps_postgres_error() -> None:
    sql = "SELECT station_id FROM weather_metrics"
    service, *_ = await _service(error_sql={sql})

    with pytest.raises(QueryExecutionError):
        await service.execute(sql)


# --- evaluate: match/clear diffing ---


async def test_evaluate_writes_match_for_new_identifier() -> None:
    query_rule = _query_rule()
    rows = [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]
    service, _repo, event_repository, _telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: rows}
    )

    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert len(events) == 1
    assert events[0].flag == EventFlag.MATCH
    assert events[0].tags == {"station_id": "wx-01"}
    assert events[0].fields == {"wind_speed_kmh": 75.0}
    assert events[0].source_type == "query_rule"
    assert events[0].query_rule_id == query_rule.id
    assert events[0].automater_id is None


async def test_evaluate_suppresses_repeat_match_for_already_open_identifier() -> None:
    query_rule = _query_rule()
    rows = [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]
    service, _repo, event_repository, _telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: rows}
    )

    await service.evaluate(query_rule)
    await service.evaluate(query_rule)  # same result set again

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert len(events) == 1  # still just the one match, not a duplicate


async def test_evaluate_writes_clear_when_identifier_drops_out() -> None:
    query_rule = _query_rule()
    sql = query_rule.sql
    database = AsyncMongoMockClient()["iotops"]
    repository = QueryRuleRepository(database)
    await repository.create(query_rule)
    event_repository = EventRepository(database)
    fake_telemetry = FakeTelemetryRepository({sql: [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]})
    service = QueryRuleService(
        repository=repository, telemetry_repository=fake_telemetry, event_repository=event_repository  # type: ignore[arg-type]
    )
    await service.evaluate(query_rule)

    fake_telemetry.rows_by_sql[sql] = []  # station no longer matches
    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert {e.flag for e in events} == {EventFlag.MATCH, EventFlag.CLEAR}
    occurrences, _total = await event_repository.list_occurrences(rule_ids=[query_rule.id])
    assert occurrences[0].status == OccurrenceStatus.RESOLVED


async def test_evaluate_interpolates_message_placeholders_on_match() -> None:
    # QueryRules never go through custom-telegraf's rule.go (the real-time
    # path's interpolateMessage) -- this is the Python-side equivalent, so
    # {column} placeholders in a QueryRule's message must resolve the same
    # way a real-time Rule's message already does.
    query_rule = _query_rule(message="Station {station_id} wind: {wind_speed_kmh} km/h")
    rows = [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]
    service, _repo, event_repository, _telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: rows}
    )

    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert events[0].message == "Station wx-01 wind: 75.0 km/h"


async def test_evaluate_interpolation_leaves_unresolvable_placeholder_blank() -> None:
    query_rule = _query_rule(message="Station {station_id}: {unknown_column}")
    rows = [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]
    service, _repo, event_repository, _telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: rows}
    )

    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert events[0].message == "Station wx-01: "


async def test_evaluate_interpolates_message_on_clear_from_identifiers() -> None:
    # No fresh row is available at clear time (the entity dropped out of
    # the result set) -- only identifiers survive from the original match,
    # so a clear message can only interpolate identifier columns.
    query_rule = _query_rule(message="Station {station_id} cleared")
    sql = query_rule.sql
    service, _repo, event_repository, fake_telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={sql: [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]}
    )
    await service.evaluate(query_rule)

    fake_telemetry.rows_by_sql[sql] = []
    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    clear_event = next(e for e in events if e.flag == EventFlag.CLEAR)
    assert clear_event.message == "Station wx-01 cleared"


async def test_evaluate_manual_resolve_mode_never_auto_clears() -> None:
    query_rule = _query_rule(resolve_mode=ResolveMode.MANUAL)
    sql = query_rule.sql
    database = AsyncMongoMockClient()["iotops"]
    repository = QueryRuleRepository(database)
    await repository.create(query_rule)
    event_repository = EventRepository(database)
    fake_telemetry = FakeTelemetryRepository({sql: [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]})
    service = QueryRuleService(
        repository=repository, telemetry_repository=fake_telemetry, event_repository=event_repository  # type: ignore[arg-type]
    )
    await service.evaluate(query_rule)

    fake_telemetry.rows_by_sql[sql] = []  # station no longer matches
    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert all(e.flag == EventFlag.MATCH for e in events)  # no auto-clear written
    occurrences, _total = await event_repository.list_occurrences(rule_ids=[query_rule.id])
    assert occurrences[0].status == OccurrenceStatus.ACTIVE


async def test_evaluate_groups_by_full_identifier_tuple() -> None:
    query_rule = _query_rule(identifiers=["station_id"])
    rows = [
        {"station_id": "wx-01", "wind_speed_kmh": 75.0},
        {"station_id": "wx-02", "wind_speed_kmh": 80.0},
    ]
    service, _repo, event_repository, _telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: rows}
    )

    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert {e.tags["station_id"] for e in events} == {"wx-01", "wx-02"}


async def test_evaluate_with_zero_identifiers_shares_one_occurrence_group() -> None:
    # Mirrors rule.go's own zero-identifiers branch (already covered for
    # the real-time path by EventRepository's own
    # test_list_occurrences_with_no_identifier_keys_groups_across_whole_rule)
    # -- every row shares one group, not one per row.
    query_rule = _query_rule(identifiers=[])
    rows = [
        {"total_errors": 42},
        {"total_errors": 43},  # a second row would collapse into the same key
    ]
    service, _repo, event_repository, _telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: rows}
    )

    await service.evaluate(query_rule)

    events = await event_repository.list(rule_ids=[query_rule.id])
    assert len(events) == 1
    assert events[0].tags == {}
    occurrences, _total = await event_repository.list_occurrences(rule_ids=[query_rule.id])
    assert occurrences[0].identifiers == {}


async def test_evaluate_with_zero_identifiers_clears_when_no_rows_match() -> None:
    query_rule = _query_rule(identifiers=[])
    sql = query_rule.sql
    database = AsyncMongoMockClient()["iotops"]
    repository = QueryRuleRepository(database)
    await repository.create(query_rule)
    event_repository = EventRepository(database)
    fake_telemetry = FakeTelemetryRepository({sql: [{"total_errors": 42}]})
    service = QueryRuleService(
        repository=repository, telemetry_repository=fake_telemetry, event_repository=event_repository  # type: ignore[arg-type]
    )
    await service.evaluate(query_rule)

    fake_telemetry.rows_by_sql[sql] = []
    await service.evaluate(query_rule)

    occurrences, _total = await event_repository.list_occurrences(rule_ids=[query_rule.id])
    assert occurrences[0].status == OccurrenceStatus.RESOLVED


# --- preview ---


async def test_preview_returns_columns_and_rows() -> None:
    sql = "SELECT station_id, wind_speed_kmh FROM weather_metrics"
    service, *_ = await _service(rows_by_sql={sql: [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]})

    result = await service.preview(sql)

    assert result.columns == ["station_id", "wind_speed_kmh"]
    assert result.rows == [{"station_id": "wx-01", "wind_speed_kmh": 75.0}]


async def test_preview_returns_empty_columns_for_no_rows() -> None:
    sql = "SELECT station_id FROM weather_metrics"
    service, *_ = await _service(rows_by_sql={sql: []})

    result = await service.preview(sql)

    assert result.columns == []
    assert result.rows == []


async def test_preview_wraps_postgres_error() -> None:
    sql = "SELECT station_id FROM weather_metrics"
    service, *_ = await _service(error_sql={sql})

    with pytest.raises(QueryExecutionError):
        await service.preview(sql)


# --- evaluate_due ---


async def test_evaluate_due_skips_not_due_rules() -> None:
    now = datetime.now(timezone.utc)
    query_rule = _query_rule(last_evaluated_at=now - timedelta(seconds=10))
    service, repository, _event_repository, fake_telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: []}
    )

    await service.evaluate_due()

    assert fake_telemetry.calls == []
    fetched = await repository.get(query_rule.id)
    assert fetched.last_evaluated_at == query_rule.last_evaluated_at


async def test_evaluate_due_evaluates_and_stamps_due_rules() -> None:
    query_rule = _query_rule()  # never evaluated -- always due
    service, repository, _event_repository, fake_telemetry = await _service(
        query_rules=[query_rule], rows_by_sql={query_rule.sql: []}
    )

    await service.evaluate_due()

    assert len(fake_telemetry.calls) == 1
    fetched = await repository.get(query_rule.id)
    assert fetched.last_evaluated_at is not None


async def test_evaluate_due_stamps_even_on_failure_and_continues() -> None:
    failing = _query_rule(name="failing-rule", sql="SELECT station_id FROM broken_table")
    healthy = _query_rule(name="healthy-rule", sql="SELECT station_id FROM weather_metrics")
    database = AsyncMongoMockClient()["iotops"]
    repository = QueryRuleRepository(database)
    await repository.create(failing)
    await repository.create(healthy)
    event_repository = EventRepository(database)
    fake_telemetry = FakeTelemetryRepository(
        rows_by_sql={healthy.sql: []}, error_sql={failing.sql}
    )
    service = QueryRuleService(
        repository=repository, telemetry_repository=fake_telemetry, event_repository=event_repository  # type: ignore[arg-type]
    )

    await service.evaluate_due()

    refetched_failing = await repository.get(failing.id)
    refetched_healthy = await repository.get(healthy.id)
    assert refetched_failing.last_evaluated_at is not None
    assert refetched_healthy.last_evaluated_at is not None
