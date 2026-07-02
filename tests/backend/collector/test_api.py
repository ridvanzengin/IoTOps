from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.collector.docker import CollectorDockerManager
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
from app.dependencies import get_collector_service
from app.main import app
from app.plugin.registry import build_default_registry
from tests.backend.collector.test_docker import FakeDockerClient

VALID_PAYLOAD = {
    "name": "Hive Collector",
    "inputs": [
        {
            "plugin_type": "mqtt",
            "name": "hive-mqtt",
            "configuration": {"servers": ["tcp://mosquitto:1883"], "topics": ["hive/+"]},
        }
    ],
    "outputs": [
        {
            "plugin_type": "timescaledb",
            "configuration": {
                "connection": "postgres://iotops:iotops@timescaledb:5432/iotops",
            },
        }
    ],
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    database = AsyncMongoMockClient()["iotops"]
    docker_manager = CollectorDockerManager(
        client=FakeDockerClient(),  # type: ignore[arg-type]
        runtime_dir=tmp_path / "runtime",
        host_runtime_dir=Path("/host/runtime"),
    )
    service = CollectorService(
        repository=CollectorRepository(database),
        registry=build_default_registry(),
        docker_manager=docker_manager,
    )
    app.dependency_overrides[get_collector_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_collector_returns_201(client: TestClient) -> None:
    response = client.post("/api/collector", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["name"] == "Hive Collector"
    assert response.json()["status"] == "created"


def test_create_collector_with_invalid_plugin_config_returns_422(client: TestClient) -> None:
    payload = {
        **VALID_PAYLOAD,
        "inputs": [{"plugin_type": "mqtt", "name": "hive-mqtt", "configuration": {"servers": []}}],
    }

    response = client.post("/api/collector", json=payload)

    assert response.status_code == 422


def test_create_collector_fills_in_plugin_defaults(client: TestClient) -> None:
    payload = {
        **VALID_PAYLOAD,
        "inputs": [{"plugin_type": "mqtt", "name": "hive-mqtt", "configuration": {}}],
    }

    response = client.post("/api/collector", json=payload)

    assert response.status_code == 201
    assert response.json()["inputs"][0]["configuration"]["servers"] == ["tcp://mosquitto:1883"]


def test_create_collector_without_inputs_returns_422(client: TestClient) -> None:
    payload = {**VALID_PAYLOAD, "inputs": []}

    response = client.post("/api/collector", json=payload)

    assert response.status_code == 422


def test_get_missing_collector_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/collector/{uuid4()}")

    assert response.status_code == 404


def test_list_collectors_returns_created_collector(client: TestClient) -> None:
    created = client.post("/api/collector", json=VALID_PAYLOAD).json()

    response = client.get("/api/collector")

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [created["id"]]


def test_update_collector_renames_it(client: TestClient) -> None:
    created = client.post("/api/collector", json=VALID_PAYLOAD).json()

    response = client.put(
        f"/api/collector/{created['id']}",
        json={**VALID_PAYLOAD, "name": "Renamed Hive"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Hive"


def test_deploy_collector_starts_container(client: TestClient) -> None:
    created = client.post("/api/collector", json=VALID_PAYLOAD).json()

    response = client.post(f"/api/collector/{created['id']}/deployment")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["docker"] is not None


def test_stop_collector_deployment(client: TestClient) -> None:
    created = client.post("/api/collector", json=VALID_PAYLOAD).json()
    client.post(f"/api/collector/{created['id']}/deployment")

    response = client.delete(f"/api/collector/{created['id']}/deployment")

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_delete_collector_removes_it(client: TestClient) -> None:
    created = client.post("/api/collector", json=VALID_PAYLOAD).json()

    response = client.delete(f"/api/collector/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/collector/{created['id']}").status_code == 404
