from datetime import datetime, timedelta, timezone
from uuid import uuid4

from mongomock_motor import AsyncMongoMockClient

from app.event.models import Event, EventFlag
from app.event.repository import EventRepository, to_document


def _event(**overrides: object) -> Event:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "automater_id": uuid4(),
        "rule_id": uuid4(),
        "rule_name": "swarm-alert",
        "table": "hive_metrics",
        "flag": EventFlag.MATCH,
        "matched_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Event(**defaults)


async def _seeded_repository(*events: Event) -> EventRepository:
    database = AsyncMongoMockClient()["iotops"]
    collection = database["events"]
    for event in events:
        await collection.insert_one(to_document(event))
    return EventRepository(database)


async def test_list_returns_events_newest_first() -> None:
    now = datetime.now(timezone.utc)
    older = _event(matched_at=now - timedelta(minutes=5))
    newer = _event(matched_at=now)
    repository = await _seeded_repository(older, newer)

    events = await repository.list()

    assert [e.id for e in events] == [newer.id, older.id]


async def test_list_filters_by_project_id() -> None:
    project_a = uuid4()
    project_b = uuid4()
    event_a = _event(project_id=project_a)
    event_b = _event(project_id=project_b)
    repository = await _seeded_repository(event_a, event_b)

    events = await repository.list(project_id=project_a)

    assert [e.id for e in events] == [event_a.id]


async def test_list_respects_limit() -> None:
    events = [_event() for _ in range(5)]
    repository = await _seeded_repository(*events)

    result = await repository.list(limit=2)

    assert len(result) == 2


async def test_counts_by_rule_counts_matches_not_clears() -> None:
    project_id = uuid4()
    rule_id = uuid4()
    repository = await _seeded_repository(
        _event(project_id=project_id, rule_id=rule_id, rule_name="swarm-alert", flag=EventFlag.MATCH),
        _event(project_id=project_id, rule_id=rule_id, rule_name="swarm-alert", flag=EventFlag.MATCH),
        _event(project_id=project_id, rule_id=rule_id, rule_name="swarm-alert", flag=EventFlag.CLEAR),
    )

    counts = await repository.counts_by_rule(project_id=project_id)

    assert len(counts) == 1
    assert counts[0].rule_id == rule_id
    assert counts[0].count == 2


async def test_counts_by_rule_separates_different_rules() -> None:
    project_id = uuid4()
    repository = await _seeded_repository(
        _event(project_id=project_id, rule_name="swarm-alert", flag=EventFlag.MATCH),
        _event(project_id=project_id, rule_name="humidity-alert", flag=EventFlag.MATCH),
    )

    counts = await repository.counts_by_rule(project_id=project_id)

    assert {c.rule_name for c in counts} == {"swarm-alert", "humidity-alert"}


async def test_counts_by_rule_without_project_id_covers_all_projects() -> None:
    repository = await _seeded_repository(
        _event(project_id=uuid4(), flag=EventFlag.MATCH),
        _event(project_id=uuid4(), flag=EventFlag.MATCH),
    )

    counts = await repository.counts_by_rule()

    assert len(counts) == 2
