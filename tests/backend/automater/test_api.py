from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.automater.docker import AutomaterDockerManager
from app.automater.repository import AutomaterRepository
from app.automater.service import AutomaterService
from app.collector.docker import CollectorDockerManager
from app.collector.models import Collector
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
from app.dependencies import get_automater_service
from app.main import app
from app.plugin.registry import build_default_registry
from app.shared.models import InputPlugin, OutputPlugin
from tests.backend.collector.test_docker import FakeDockerClient


@pytest.fixture
def collector_repository() -> CollectorRepository:
    database = AsyncMongoMockClient()["iotops"]
    return CollectorRepository(database)


@pytest.fixture
def client(tmp_path: Path, collector_repository: CollectorRepository) -> TestClient:
    database = AsyncMongoMockClient()["iotops"]
    docker_manager = AutomaterDockerManager(
        client=FakeDockerClient(),  # type: ignore[arg-type]
        runtime_dir=tmp_path / "runtime",
        host_runtime_dir=Path("/host/runtime"),
    )
    collector_service = CollectorService(
        repository=collector_repository,
        registry=build_default_registry(),
        docker_manager=CollectorDockerManager(
            client=FakeDockerClient(),  # type: ignore[arg-type]
            runtime_dir=tmp_path / "collector-runtime",
            host_runtime_dir=Path("/host/collector-runtime"),
        ),
    )
    service = AutomaterService(
        repository=AutomaterRepository(database),
        registry=build_default_registry(),
        docker_manager=docker_manager,
        collector_service=collector_service,
    )
    app.dependency_overrides[get_automater_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


async def _seed_collector(collector_repository: CollectorRepository, project_id: str) -> str:
    collector = Collector(
        project_id=project_id,
        name="Hive Collector",
        inputs=[
            InputPlugin(
                plugin_type="mqtt",
                name="hive-mqtt",
                configuration={"name_override": "hive_metrics", "topics": ["beekeeping/hive"]},
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    created = await collector_repository.create(collector)
    return str(created.id)


def _rule_payload(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "name": "swarm-alert",
        "table": "hive_metrics",
        "conditions": [{"column": "temperature", "operator": ">", "value": 30.0}],
    }
    defaults.update(overrides)
    return defaults


async def test_create_rule_returns_201(client: TestClient, collector_repository: CollectorRepository) -> None:
    project_id = str(uuid4())
    collector_id = await _seed_collector(collector_repository, project_id)

    response = client.post(
        "/api/automater/rules",
        json={
            "project_id": project_id,
            "rule": _rule_payload(),
            "automater_name": "New Automater",
            "collector_id": collector_id,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "running"
    assert [r["name"] for r in response.json()["rules"]] == ["swarm-alert"]


async def test_create_rule_missing_automater_name_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/automater/rules",
        json={"project_id": str(uuid4()), "rule": _rule_payload()},
    )

    assert response.status_code == 400


def test_full_rule_replace_endpoint_no_longer_exists(client: TestClient) -> None:
    # Regression test for the removed general-purpose "replace any rule
    # field" endpoint: its only real caller only ever toggled `enabled`,
    # and a full replace let `table` change with none of create_rule's
    # input-matching validation applied -- silently deploying a rule that
    # could never fire. Only DELETE remains at this path now.
    response = client.put(
        f"/api/automater/{uuid4()}/rules/{uuid4()}",
        json={"name": "x", "table": "hive_metrics", "conditions": []},
    )

    assert response.status_code == 405


async def test_set_rule_enabled_toggles_the_flag(
    client: TestClient, collector_repository: CollectorRepository
) -> None:
    project_id = str(uuid4())
    collector_id = await _seed_collector(collector_repository, project_id)
    created = client.post(
        "/api/automater/rules",
        json={
            "project_id": project_id,
            "rule": _rule_payload(),
            "automater_name": "New Automater",
            "collector_id": collector_id,
        },
    ).json()
    automater_id = created["id"]
    rule_id = created["rules"][0]["id"]

    response = client.put(
        f"/api/automater/{automater_id}/rules/{rule_id}/enabled",
        json={"enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["rules"][0]["enabled"] is False
    assert response.json()["status"] == "stopped"


async def test_delete_last_rule_returns_400(
    client: TestClient, collector_repository: CollectorRepository
) -> None:
    project_id = str(uuid4())
    collector_id = await _seed_collector(collector_repository, project_id)
    created = client.post(
        "/api/automater/rules",
        json={
            "project_id": project_id,
            "rule": _rule_payload(),
            "automater_name": "New Automater",
            "collector_id": collector_id,
        },
    ).json()

    response = client.delete(f"/api/automater/{created['id']}/rules/{created['rules'][0]['id']}")

    assert response.status_code == 400
