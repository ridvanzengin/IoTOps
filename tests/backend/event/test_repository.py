import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.event.models import Event, EventFlag, OccurrenceStatus, ResolveMode
from app.event.repository import EventRepository, to_document
from app.shared.exceptions import EntityNotFoundError, InvalidOperationError


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


async def _seeded_repository_with_redis(*events: Event) -> tuple[EventRepository, AsyncMock, AsyncMock]:
    database = AsyncMongoMockClient()["iotops"]
    collection = database["events"]
    for event in events:
        await collection.insert_one(to_document(event))
    pubsub_client = AsyncMock()
    firing_client = AsyncMock()
    repository = EventRepository(database, pubsub_redis_client=pubsub_client, firing_redis_client=firing_client)
    return repository, pubsub_client, firing_client


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


async def test_list_filters_by_since_and_until() -> None:
    now = datetime.now(timezone.utc)
    too_old = _event(matched_at=now - timedelta(hours=2))
    in_range = _event(matched_at=now - timedelta(minutes=30))
    too_new = _event(matched_at=now + timedelta(hours=1))
    repository = await _seeded_repository(too_old, in_range, too_new)

    events = await repository.list(since=now - timedelta(hours=1), until=now)

    assert [e.id for e in events] == [in_range.id]


async def test_list_filters_by_rule_ids() -> None:
    rule_a = uuid4()
    rule_b = uuid4()
    rule_c = uuid4()
    event_a = _event(rule_id=rule_a)
    event_b = _event(rule_id=rule_b)
    event_c = _event(rule_id=rule_c)
    repository = await _seeded_repository(event_a, event_b, event_c)

    events = await repository.list(rule_ids=[rule_a, rule_b])

    assert {e.id for e in events} == {event_a.id, event_b.id}


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


async def test_occurrence_counts_by_rule_counts_occurrences_not_raw_matches() -> None:
    # A repeat match while one's already open is defensively dropped by
    # _pair_occurrences (see its own docstring) -- counts_by_rule (raw
    # match-flag documents) would count 3, but there are only 2 real
    # Occurrences here, and that's what a rule filter chip's count has to
    # equal for the click-through card count to match it.
    project_id = uuid4()
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    repository = await _seeded_repository(
        _event(project_id=project_id, rule_id=rule_id, rule_name="swarm-alert", flag=EventFlag.MATCH, matched_at=now),
        _event(
            project_id=project_id,
            rule_id=rule_id,
            rule_name="swarm-alert",
            flag=EventFlag.MATCH,
            matched_at=now + timedelta(seconds=1),
        ),  # stray repeat match while the first is still open -- dropped
        _event(
            project_id=project_id,
            rule_id=rule_id,
            rule_name="swarm-alert",
            flag=EventFlag.CLEAR,
            matched_at=now + timedelta(minutes=1),
        ),
        _event(
            project_id=project_id,
            rule_id=rule_id,
            rule_name="swarm-alert",
            flag=EventFlag.MATCH,
            matched_at=now + timedelta(minutes=2),
        ),
    )

    counts = await repository.occurrence_counts_by_rule(project_id)
    occurrences, total = await repository.list_occurrences(project_id=project_id, rule_ids=[rule_id], limit=1000)

    assert len(counts) == 1
    assert counts[0].count == 2
    assert counts[0].count == total
    assert counts[0].count == len(occurrences)


async def test_occurrence_counts_by_rule_is_scoped_to_its_project() -> None:
    project_id = uuid4()
    other_project = uuid4()
    repository = await _seeded_repository(
        _event(project_id=project_id, rule_name="swarm-alert", flag=EventFlag.MATCH),
        _event(project_id=other_project, rule_name="humidity-alert", flag=EventFlag.MATCH),
    )

    counts = await repository.occurrence_counts_by_rule(project_id)

    assert len(counts) == 1
    assert counts[0].rule_name == "swarm-alert"


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

    occurrences, total = await repository.list_occurrences()

    assert len(occurrences) == 1
    assert total == 1
    occurrence = occurrences[0]
    assert occurrence.status == OccurrenceStatus.RESOLVED
    assert occurrence.matched_at == match.matched_at
    assert occurrence.resolved_at == clear.matched_at
    assert occurrence.identifiers == {"hive_id": "hive-1"}


async def test_list_occurrences_leaves_trailing_match_active() -> None:
    match = _event(identifier_keys=["hive_id"], tags={"hive_id": "hive-1"})
    repository = await _seeded_repository(match)

    occurrences, _total = await repository.list_occurrences()

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

    occurrences, _total = await repository.list_occurrences()

    assert len(occurrences) == 2
    assert {o.status for o in occurrences} == {OccurrenceStatus.RESOLVED, OccurrenceStatus.ACTIVE}


async def test_list_occurrences_status_filter_matches_unresolved_counts() -> None:
    # The EventsPanel "Active" filter and the ActivityBar badge must agree
    # on the same project: both ultimately pair the same documents, so a
    # status=active-filtered list_occurrences() and
    # unresolved_counts_by_project()'s count for that project should never
    # diverge -- this is the fix for the badge/list mismatch bug.
    rule_id = uuid4()
    project_id = uuid4()
    now = datetime.now(timezone.utc)
    events = [
        _event(project_id=project_id, rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"}, matched_at=now),
        _event(
            project_id=project_id,
            rule_id=rule_id,
            identifier_keys=["hive_id"],
            tags={"hive_id": "hive-1"},
            flag=EventFlag.CLEAR,
            matched_at=now + timedelta(minutes=1),
        ),
        _event(project_id=project_id, rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-2"}, matched_at=now),
        _event(project_id=project_id, rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-3"}, matched_at=now),
    ]
    repository = await _seeded_repository(*events)

    active, active_total = await repository.list_occurrences(project_id=project_id, status=OccurrenceStatus.ACTIVE)
    resolved, resolved_total = await repository.list_occurrences(
        project_id=project_id, status=OccurrenceStatus.RESOLVED
    )
    unresolved_counts = await repository.unresolved_counts_by_project()

    assert len(active) == 2
    assert active_total == 2
    assert all(o.status == OccurrenceStatus.ACTIVE for o in active)
    assert len(resolved) == 1
    assert resolved_total == 1
    assert resolved[0].status == OccurrenceStatus.RESOLVED
    assert next(c.count for c in unresolved_counts if c.project_id == project_id) == active_total


async def test_list_occurrences_rule_ids_filter_scopes_the_query() -> None:
    other_rule_events_dont_leak = _event(rule_id=uuid4())
    rule_id = uuid4()
    match = _event(rule_id=rule_id)
    repository = await _seeded_repository(other_rule_events_dont_leak, match)

    occurrences, total = await repository.list_occurrences(rule_ids=[rule_id])

    assert len(occurrences) == 1
    assert total == 1
    assert occurrences[0].rule_id == rule_id


async def test_list_occurrences_groups_by_identifier_values_not_just_rule() -> None:
    rule_id = uuid4()
    hive1 = _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"})
    hive2 = _event(rule_id=rule_id, identifier_keys=["hive_id"], tags={"hive_id": "hive-2"})
    repository = await _seeded_repository(hive1, hive2)

    occurrences, _total = await repository.list_occurrences()

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

    occurrences, _total = await repository.list_occurrences()

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


async def test_resolve_occurrence_resolves_and_stores_notes() -> None:
    match = _event(
        resolve_mode=ResolveMode.MANUAL,
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-1"},
    )
    repository, pubsub_client, firing_client = await _seeded_repository_with_redis(match)

    occurrence = await repository.resolve_occurrence(match.id, "checked on the hive, false alarm")

    assert occurrence.status == OccurrenceStatus.RESOLVED
    assert occurrence.resolution_notes == "checked on the hive, false alarm"
    assert occurrence.resolved_at is not None

    occurrences, _total = await repository.list_occurrences()
    assert len(occurrences) == 1
    assert occurrences[0].status == OccurrenceStatus.RESOLVED


async def test_resolve_occurrence_deletes_firing_key_and_publishes() -> None:
    match = _event(resolve_mode=ResolveMode.MANUAL, identifier_keys=["hive_id"], tags={"hive_id": "hive-1"})
    repository, pubsub_client, firing_client = await _seeded_repository_with_redis(match)

    await repository.resolve_occurrence(match.id, "")

    firing_client.delete.assert_awaited_once()
    (deleted_key,) = firing_client.delete.await_args.args
    # Independently reconstructs rule.go's firingKey() -- see
    # EventRepository._firing_key's own comment for the algorithm.
    digest = hashlib.sha256(b"hive-1").hexdigest()
    assert deleted_key == f"automater:firing:{match.rule_name}:{match.rule_id}:{digest}"

    pubsub_client.publish.assert_awaited_once()
    channel, _payload = pubsub_client.publish.await_args.args
    assert channel == f"events:{match.project_id}"


async def test_resolve_occurrence_skips_firing_key_deletion_for_query_rule_source() -> None:
    # A query_rule-sourced match has no Redis firing key -- only the Go
    # plugin ever creates one. Deleting a key that was never set is
    # harmless in itself, but attempting it signals a design mismatch, so
    # this is guarded explicitly rather than left as a silent no-op miss.
    match = _event(
        source_type="query_rule",
        automater_id=None,
        query_rule_id=uuid4(),
        resolve_mode=ResolveMode.MANUAL,
        identifier_keys=["station_id"],
        tags={"station_id": "wx-01"},
    )
    repository, pubsub_client, firing_client = await _seeded_repository_with_redis(match)

    occurrence = await repository.resolve_occurrence(match.id, "false alarm")

    assert occurrence.status == OccurrenceStatus.RESOLVED
    firing_client.delete.assert_not_awaited()
    pubsub_client.publish.assert_awaited_once()


async def test_resolve_occurrence_rejects_auto_resolve_rule() -> None:
    match = _event()  # resolve_mode defaults to AUTO
    repository, _pubsub_client, _firing_client = await _seeded_repository_with_redis(match)

    with pytest.raises(InvalidOperationError):
        await repository.resolve_occurrence(match.id, "")


async def test_resolve_occurrence_rejects_unknown_event() -> None:
    repository, _pubsub_client, _firing_client = await _seeded_repository_with_redis()

    with pytest.raises(EntityNotFoundError):
        await repository.resolve_occurrence(uuid4(), "")


async def test_resolve_occurrence_rejects_already_resolved() -> None:
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    match = _event(
        rule_id=rule_id,
        resolve_mode=ResolveMode.MANUAL,
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-1"},
        matched_at=now,
    )
    clear = _event(
        rule_id=rule_id,
        resolve_mode=ResolveMode.MANUAL,
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-1"},
        flag=EventFlag.CLEAR,
        matched_at=now + timedelta(minutes=1),
    )
    repository, _pubsub_client, _firing_client = await _seeded_repository_with_redis(match, clear)

    with pytest.raises(InvalidOperationError):
        await repository.resolve_occurrence(match.id, "")
