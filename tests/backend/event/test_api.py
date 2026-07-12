from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.dependencies import get_event_service
from app.event.models import Event, EventFlag
from app.event.repository import EventRepository, to_document
from app.event.service import EventService
from app.main import app


@pytest.fixture
def client() -> TestClient:
    database = AsyncMongoMockClient()["iotops"]
    service = EventService(repository=EventRepository(database))
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
    [occurrence] = response.json()
    assert occurrence["status"] == "resolved"
    assert occurrence["identifiers"] == {"hive_id": "hive-1"}


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
