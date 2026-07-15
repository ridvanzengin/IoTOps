from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.dependencies import get_event_service
from app.event.models import Event, EventFlag, ResolveMode
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.main import app


@pytest.fixture
def client() -> TestClient:
    database = AsyncMongoMockClient()["iotops"]
    service = EventService(
        repository=EventRepository(database, pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock())
    )
    app.dependency_overrides[get_event_service] = lambda: service
    app.state.test_collection = database["events"]
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


async def _seed(client: TestClient, **overrides: object) -> Event:
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
    event = Event(**defaults)
    await client.app.state.test_collection.insert_one(to_document(event))
    return event


async def test_list_events_returns_seeded_event(client: TestClient) -> None:
    event = await _seed(client)

    response = client.get("/api/event")

    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == [str(event.id)]


async def test_list_events_filters_by_project_id(client: TestClient) -> None:
    project_id = uuid4()
    matching = await _seed(client, project_id=project_id)
    await _seed(client, project_id=uuid4())

    response = client.get("/api/event", params={"project_id": str(project_id)})

    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == [str(matching.id)]


async def test_list_events_filters_by_rule_id_and_time_range(client: TestClient) -> None:
    now = datetime.now(timezone.utc)
    rule_id = uuid4()
    matching = await _seed(client, rule_id=rule_id, matched_at=now)
    await _seed(client, rule_id=uuid4(), matched_at=now)  # wrong rule
    await _seed(client, rule_id=rule_id, matched_at=now - timedelta(hours=2))  # out of range

    response = client.get(
        "/api/event",
        params={
            "rule_id": [str(rule_id)],
            "since": (now - timedelta(hours=1)).isoformat(),
            "until": (now + timedelta(hours=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == [str(matching.id)]


async def test_get_event_counts_groups_by_rule(client: TestClient) -> None:
    project_id = uuid4()
    rule_id = uuid4()
    await _seed(client, project_id=project_id, rule_id=rule_id, rule_name="swarm-alert", flag=EventFlag.MATCH)
    await _seed(client, project_id=project_id, rule_id=rule_id, rule_name="swarm-alert", flag=EventFlag.MATCH)

    response = client.get("/api/event/counts", params={"project_id": str(project_id)})

    assert response.status_code == 200
    [count] = response.json()
    assert count["rule_name"] == "swarm-alert"
    assert count["count"] == 2


async def test_list_occurrences_returns_paired_occurrence(client: TestClient) -> None:
    project_id = uuid4()
    rule_id = uuid4()
    await _seed(
        client,
        project_id=project_id,
        rule_id=rule_id,
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-1"},
        flag=EventFlag.MATCH,
    )
    await _seed(
        client,
        project_id=project_id,
        rule_id=rule_id,
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-1"},
        flag=EventFlag.CLEAR,
    )

    response = client.get("/api/event/occurrences", params={"project_id": str(project_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    [occurrence] = body["items"]
    assert occurrence["status"] == "resolved"
    assert occurrence["identifiers"] == {"hive_id": "hive-1"}


async def test_list_occurrences_status_query_param_filters_to_active(client: TestClient) -> None:
    project_id = uuid4()
    resolved_rule = uuid4()
    active_rule = uuid4()
    await _seed(client, project_id=project_id, rule_id=resolved_rule, flag=EventFlag.MATCH)
    await _seed(client, project_id=project_id, rule_id=resolved_rule, flag=EventFlag.CLEAR)
    await _seed(client, project_id=project_id, rule_id=active_rule, flag=EventFlag.MATCH)

    response = client.get(
        "/api/event/occurrences", params={"project_id": str(project_id), "status": "active"}
    )

    assert response.status_code == 200
    [occurrence] = response.json()["items"]
    assert occurrence["status"] == "active"
    assert occurrence["rule_id"] == str(active_rule)


async def test_list_occurrences_status_active_ignores_range_even_when_older_than_max_range(
    client: TestClient,
) -> None:
    # Active means "still unresolved", full stop -- it must surface
    # regardless of age, the same way GET /api/event/unresolved-counts
    # (used for the ActivityBar badge) never applies a time bound at all.
    # 10 days is deliberately past 7d, the widest option the frontend's
    # own range selector offers (constants/timeRanges.ts) -- there is no
    # range value a user could pick that would otherwise reach this.
    project_id = uuid4()
    now = datetime.now(timezone.utc)
    old_active = await _seed(client, project_id=project_id, matched_at=now - timedelta(days=10))

    response = client.get(
        "/api/event/occurrences",
        params={"project_id": str(project_id), "status": "active", "range": "1h"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(old_active.id)


async def test_list_occurrences_resolved_status_still_respects_range(client: TestClient) -> None:
    # The active-ignores-range carve-out shouldn't leak into browsing
    # history by other statuses -- a resolved occurrence from 10 days ago
    # should still be excluded by the default/explicit range, same as
    # before this change.
    project_id = uuid4()
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    await _seed(client, project_id=project_id, rule_id=rule_id, flag=EventFlag.MATCH, matched_at=now - timedelta(days=10))
    await _seed(client, project_id=project_id, rule_id=rule_id, flag=EventFlag.CLEAR, matched_at=now - timedelta(days=10))

    response = client.get(
        "/api/event/occurrences",
        params={"project_id": str(project_id), "status": "resolved", "range": "1h"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_occurrences_rule_id_query_param_scopes_results(client: TestClient) -> None:
    project_id = uuid4()
    wanted_rule = uuid4()
    await _seed(client, project_id=project_id, rule_id=uuid4(), flag=EventFlag.MATCH)
    await _seed(client, project_id=project_id, rule_id=wanted_rule, flag=EventFlag.MATCH)

    response = client.get(
        "/api/event/occurrences", params={"project_id": str(project_id), "rule_id": str(wanted_rule)}
    )

    assert response.status_code == 200
    [occurrence] = response.json()["items"]
    assert occurrence["rule_id"] == str(wanted_rule)


async def test_list_occurrences_default_range_excludes_events_older_than_1h(client: TestClient) -> None:
    project_id = uuid4()
    now = datetime.now(timezone.utc)
    recent = await _seed(client, project_id=project_id, matched_at=now - timedelta(minutes=30))
    await _seed(client, project_id=project_id, matched_at=now - timedelta(hours=2))

    response = client.get("/api/event/occurrences", params={"project_id": str(project_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [o["id"] for o in body["items"]] == [str(recent.id)]


async def test_list_occurrences_range_param_widens_the_window(client: TestClient) -> None:
    project_id = uuid4()
    now = datetime.now(timezone.utc)
    await _seed(client, project_id=project_id, matched_at=now - timedelta(minutes=30))
    await _seed(client, project_id=project_id, matched_at=now - timedelta(hours=2))

    response = client.get("/api/event/occurrences", params={"project_id": str(project_id), "range": "24h"})

    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_list_occurrences_search_param_matches_rule_name(client: TestClient) -> None:
    project_id = uuid4()
    wanted = await _seed(client, project_id=project_id, rule_name="high-vibration")
    await _seed(client, project_id=project_id, rule_name="low-fuel")

    response = client.get("/api/event/occurrences", params={"project_id": str(project_id), "search": "vibration"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(wanted.id)


async def test_list_occurrences_search_param_matches_identifier_values(client: TestClient) -> None:
    # A rule with placeholder/test naming (rule_name/message/category all
    # generic) still has to be searchable by what actually distinguishes
    # its occurrences -- the identifier chips rendered on the card.
    project_id = uuid4()
    wanted = await _seed(
        client,
        project_id=project_id,
        rule_name="sdf",
        category="sdf",
        message="dxv",
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-5"},
    )
    await _seed(
        client,
        project_id=project_id,
        rule_name="sdf",
        category="sdf",
        message="dxv",
        identifier_keys=["hive_id"],
        tags={"hive_id": "hive-6"},
    )

    response = client.get("/api/event/occurrences", params={"project_id": str(project_id), "search": "hive-5"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(wanted.id)


async def test_list_occurrences_pagination_offset_and_total(client: TestClient) -> None:
    project_id = uuid4()
    now = datetime.now(timezone.utc)
    for i in range(5):
        await _seed(client, project_id=project_id, matched_at=now - timedelta(minutes=i))

    first_page = client.get(
        "/api/event/occurrences", params={"project_id": str(project_id), "limit": 2, "offset": 0}
    ).json()
    second_page = client.get(
        "/api/event/occurrences", params={"project_id": str(project_id), "limit": 2, "offset": 2}
    ).json()

    assert first_page["total"] == 5
    assert second_page["total"] == 5
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 2
    first_ids = {item["id"] for item in first_page["items"]}
    second_ids = {item["id"] for item in second_page["items"]}
    assert first_ids.isdisjoint(second_ids)


async def test_get_occurrence_counts_by_rule_respects_range_and_search(client: TestClient) -> None:
    # Two distinct machines both matching "high-vibration" -- distinct
    # identifiers, so these are two real, independent Occurrences (not a
    # "repeat match while one's already open", which _pair_occurrences
    # would defensively collapse to one -- see the repository-level test
    # for that behavior specifically).
    project_id = uuid4()
    rule_id = uuid4()
    now = datetime.now(timezone.utc)
    await _seed(
        client,
        project_id=project_id,
        rule_id=rule_id,
        rule_name="high-vibration",
        identifier_keys=["machine_id"],
        tags={"machine_id": "lathe-01"},
        matched_at=now - timedelta(minutes=10),
    )
    await _seed(
        client,
        project_id=project_id,
        rule_id=rule_id,
        rule_name="high-vibration",
        identifier_keys=["machine_id"],
        tags={"machine_id": "lathe-02"},
        matched_at=now - timedelta(hours=3),
    )
    await _seed(client, project_id=project_id, rule_name="low-fuel", matched_at=now - timedelta(minutes=10))

    default_range = client.get("/api/event/occurrence-counts", params={"project_id": str(project_id)}).json()
    assert {c["rule_name"]: c["count"] for c in default_range} == {"high-vibration": 1, "low-fuel": 1}

    widened_range = client.get(
        "/api/event/occurrence-counts", params={"project_id": str(project_id), "range": "24h"}
    ).json()
    assert {c["rule_name"]: c["count"] for c in widened_range} == {"high-vibration": 2, "low-fuel": 1}

    searched = client.get(
        "/api/event/occurrence-counts", params={"project_id": str(project_id), "range": "24h", "search": "vibration"}
    ).json()
    assert {c["rule_name"]: c["count"] for c in searched} == {"high-vibration": 2}


async def test_get_unresolved_counts_covers_all_projects(client: TestClient) -> None:
    project_a = uuid4()
    project_b = uuid4()
    await _seed(client, project_id=project_a, flag=EventFlag.MATCH)
    await _seed(client, project_id=project_b, flag=EventFlag.MATCH)

    response = client.get("/api/event/unresolved-counts")

    assert response.status_code == 200
    by_project = {c["project_id"]: c["count"] for c in response.json()}
    assert by_project[str(project_a)] == 1
    assert by_project[str(project_b)] == 1


async def test_resolve_occurrence_returns_resolved_occurrence(client: TestClient) -> None:
    match = await _seed(client, resolve_mode=ResolveMode.MANUAL)

    response = client.post(f"/api/event/occurrences/{match.id}/resolve", json={"notes": "handled"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolution_notes"] == "handled"


async def test_resolve_occurrence_on_auto_rule_is_rejected(client: TestClient) -> None:
    match = await _seed(client)  # resolve_mode defaults to auto

    response = client.post(f"/api/event/occurrences/{match.id}/resolve", json={"notes": ""})

    assert response.status_code == 400


async def test_resolve_occurrence_on_unknown_event_is_404(client: TestClient) -> None:
    response = client.post(f"/api/event/occurrences/{uuid4()}/resolve", json={"notes": ""})

    assert response.status_code == 404
