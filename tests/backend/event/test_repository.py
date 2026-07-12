from datetime import datetime, timedelta, timezone
from uuid import uuid4

from mongomock_motor import AsyncMongoMockClient

from app.event.models import Event, EventFlag, OccurrenceStatus
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


async def test_list_occurrences_pairs_match_with_its_clear() -> None:
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    match = _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"}, matched_at=now)
    clear = _event(
        rule_id=rule_id,
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-1"},
        flag=EventFlag.CLEAR,
        matched_at=now + timedelta(minutes=1),
    )
    repository = await _seeded_repository(match, clear)

    occurrences = await repository.list_occurrences()

    assert len(occurrences) == 1
    occurrence = occurrences[0]
    assert occurrence.status == OccurrenceStatus.RESOLVED
    assert occurrence.matched_at == match.matched_at
    assert occurrence.resolved_at == clear.matched_at
    assert occurrence.identifiers == {"hive_id": "hive-1"}


async def test_list_occurrences_leaves_trailing_match_active() -> None:
    match = _event(identifier_keys=["hive_id"], tags={"hive_id": "hive-1"})
    repository = await _seeded_repository(match)

    occurrences = await repository.list_occurrences()

    assert len(occurrences) == 1
    assert occurrences[0].status == OccurrenceStatus.ACTIVE
    assert occurrences[0].resolved_at is None


async def test_list_occurrences_repeat_fire_produces_two_rows() -> None:
    # Confirmed semantics: fires, clears, fires again -- two rows, one
    # resolved, one active. The re-fire is a *new* occurrence, not the
    # old one reopening.
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    events = [
        _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"}, matched_at=now),
        _event(
            rule_id=rule_id,
            identifier_keys=["hive_id"],
            tags={"hive_id": "hive-1"},
            flag=EventFlag.CLEAR,
            matched_at=now + timedelta(minutes=1),
        ),
        _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"}, matched_at=now + timedelta(minutes=2)),
    ]
    repository = await _seeded_repository(*events)

    occurrences = await repository.list_occurrences()

    assert len(occurrences) == 2
    assert {o.status for o in occurrences} == {OccurrenceStatus.RESOLVED, OccurrenceStatus.ACTIVE}


async def test_list_occurrences_groups_by_identifier_values_not_just_rule() -> None:
    rule_id = uuid4()
    hive1 = _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"})
    hive2 = _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-2"})
    repository = await _seeded_repository(hive1, hive2)

    occurrences = await repository.list_occurrences()

    assert len(occurrences) == 2
    assert {o.identifiers["hive_id"] for o in occurrences} == {"hive-1", "hive-2"}
    assert all(o.status == OccurrenceStatus.ACTIVE for o in occurrences)


async def test_list_occurrences_with_no_identifier_keys_groups_across_whole_rule() -> None:
    # Mirrors rule.go's firingKey zero-identifiers branch: a rule with no
    # configured identifiers shares one firing/occurrence group across
    # every instance of it, rather than accidentally splitting apart here.
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    first_match = _event(rule_id=rule_id, matched_at=now)
    clear = _event(rule_id=rule_id, flag=EventFlag.CLEAR, matched_at=now + timedelta(minutes=1))
    repository = await _seeded_repository(first_match, clear)

    occurrences = await repository.list_occurrences()

    assert len(occurrences) == 1
    assert occurrences[0].status == OccurrenceStatus.RESOLVED
    assert occurrences[0].identifiers == {}


async def test_unresolved_counts_by_project_counts_only_active_occurrences() -> None:
    project_a = uuid4()
    project_b = uuid4()
    now = datetime.now(timezone.utc)
    rule_a1 = uuid4()
    rule_a2 = uuid4()
    events = [
        # project_a: one resolved occurrence (rule_a1) + one active (rule_a2) -> count 1
        _event(project_id=project_a, rule_id=rule_a1, matched_at=now),
        _event(project_id=project_a, rule_id=rule_a1, flag=EventFlag.CLEAR, matched_at=now + timedelta(minutes=1)),
        _event(project_id=project_a, rule_id=rule_a2, matched_at=now),
        # project_b: one active occurrence -> count 1
        _event(project_id=project_b, rule_id=uuid4(), matched_at=now),
    ]
    repository = await _seeded_repository(*events)

    counts = await repository.unresolved_counts_by_project()

    by_project = {c.project_id: c.count for c in counts}
    assert by_project[project_a] == 1
    assert by_project[project_b] == 1
