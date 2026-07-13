from pathlib import Path
from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.collector.docker import CollectorDockerManager
from app.collector.models import CollectorInput
from app.shared.models import InputPlugin, OutputPlugin
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
from app.plugin.registry import build_default_registry
from app.shared.enums import CollectorStatus
from app.shared.exceptions import EntityNotFoundError, PluginConfigurationError
from tests.backend.collector.test_docker import FakeDockerClient


@pytest.fixture
def service(tmp_path: Path) -> CollectorService:
    database = AsyncMongoMockClient()["iotops"]
    docker_manager = CollectorDockerManager(
        client=FakeDockerClient(),  # type: ignore[arg-type]
        runtime_dir=tmp_path / "runtime",
        host_runtime_dir=Path("/host/runtime"),
    )
    return CollectorService(
        repository=CollectorRepository(database),
        registry=build_default_registry(),
        docker_manager=docker_manager,
    )


def _valid_input(**overrides: object) -> CollectorInput:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "name": "Hive Collector",
        "inputs": [
            InputPlugin(
                plugin_type="mqtt",
                name="hive-mqtt",
                configuration={"servers": ["tcp://mosquitto:1883"], "topics": ["hive/+"]},
            )
        ],
        "outputs": [
            OutputPlugin(
                plugin_type="timescaledb",
                configuration={
                    "connection": "postgres://iotops:iotops@timescaledb:5432/iotops",
                },
            )
        ],
    }
    defaults.update(overrides)
    return CollectorInput(**defaults)


async def test_create_persists_and_returns_collector(service: CollectorService) -> None:
    collector = await service.create(_valid_input())

    fetched = await service.get(collector.id)
    assert fetched == collector


async def test_create_rejects_invalid_plugin_configuration(service: CollectorService) -> None:
    invalid_input = _valid_input(
        inputs=[
            InputPlugin(plugin_type="mqtt", name="hive-mqtt", configuration={"servers": []})
        ]
    )

    with pytest.raises(PluginConfigurationError):
        await service.create(invalid_input)


async def test_create_fills_in_plugin_defaults(service: CollectorService) -> None:
    created = await service.create(
        _valid_input(
            inputs=[InputPlugin(plugin_type="mqtt", name="hive-mqtt", configuration={})]
        )
    )

    assert created.inputs[0].configuration["servers"] == ["tcp://mosquitto:1883"]
    assert created.inputs[0].configuration["qos"] == 0


async def test_list_returns_all_collectors(service: CollectorService) -> None:
    await service.create(_valid_input(name="Hive A"))
    await service.create(_valid_input(name="Hive B"))

    collectors = await service.list()

    assert {c.name for c in collectors} == {"Hive A", "Hive B"}


async def test_update_replaces_editable_fields(service: CollectorService) -> None:
    collector = await service.create(_valid_input())

    updated = await service.update(collector.id, _valid_input(name="Renamed Hive"))

    assert updated.name == "Renamed Hive"
    assert updated.id == collector.id


async def test_update_missing_collector_raises(service: CollectorService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.update(uuid4(), _valid_input())


async def test_deploy_starts_container_and_persists_status(service: CollectorService) -> None:
    collector = await service.create(_valid_input())

    deployed = await service.deploy(collector.id)

    assert deployed.status == CollectorStatus.RUNNING
    assert deployed.docker is not None
    fetched = await service.get(collector.id)
    assert fetched.status == CollectorStatus.RUNNING


async def test_stop_updates_persisted_status(service: CollectorService) -> None:
    collector = await service.create(_valid_input())
    await service.deploy(collector.id)

    stopped = await service.stop(collector.id)

    assert stopped.status == CollectorStatus.STOPPED


async def test_redeploy_if_running_persists_without_deploying_when_not_running(
    service: CollectorService,
) -> None:
    collector = await service.create(_valid_input())
    assert collector.docker is None
    collector.outputs.append(OutputPlugin(plugin_type="timescaledb", configuration={}))

    result = await service.redeploy_if_running(collector)

    assert result.docker is None
    fetched = await service.get(collector.id)
    assert len(fetched.outputs) == 2


async def test_redeploy_if_running_redeploys_when_already_running(
    service: CollectorService,
) -> None:
    collector = await service.create(_valid_input())
    collector = await service.deploy(collector.id)
    assert collector.docker is not None
    collector.outputs.append(OutputPlugin(plugin_type="timescaledb", configuration={}))

    result = await service.redeploy_if_running(collector)

    assert result.status == CollectorStatus.RUNNING
    fetched = await service.get(collector.id)
    assert len(fetched.outputs) == 2


async def test_delete_removes_collector(service: CollectorService) -> None:
    collector = await service.create(_valid_input())
    await service.deploy(collector.id)

    await service.delete(collector.id)

    with pytest.raises(EntityNotFoundError):
        await service.get(collector.id)
