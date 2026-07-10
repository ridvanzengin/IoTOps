from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.collector.models import Collector
from app.shared.models import InputPlugin, OutputPlugin
from app.collector.repository import CollectorRepository
from app.shared.exceptions import EntityNotFoundError


@pytest.fixture
def repository() -> CollectorRepository:
    database = AsyncMongoMockClient()["iotops"]
    return CollectorRepository(database)


def _collector(**overrides: object) -> Collector:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "name": "Hive Collector",
        "inputs": [InputPlugin(plugin_type="mqtt", name="hive-mqtt")],
        "outputs": [OutputPlugin(plugin_type="timescaledb")],
    }
    defaults.update(overrides)
    return Collector(**defaults)


async def test_create_and_get(repository: CollectorRepository) -> None:
    collector = _collector()

    await repository.create(collector)
    fetched = await repository.get(collector.id)

    assert fetched == collector


async def test_get_missing_raises(repository: CollectorRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.get(uuid4())


async def test_list_returns_all_created(repository: CollectorRepository) -> None:
    first = _collector(name="Hive A")
    second = _collector(name="Hive B")
    await repository.create(first)
    await repository.create(second)

    collectors = await repository.list()

    assert {c.id for c in collectors} == {first.id, second.id}


async def test_update_persists_changes(repository: CollectorRepository) -> None:
    collector = _collector()
    await repository.create(collector)

    collector.name = "Renamed Hive Collector"
    await repository.update(collector)
    fetched = await repository.get(collector.id)

    assert fetched.name == "Renamed Hive Collector"
    assert fetched.updated_at >= collector.created_at


async def test_update_missing_raises(repository: CollectorRepository) -> None:
    collector = _collector()

    with pytest.raises(EntityNotFoundError):
        await repository.update(collector)


async def test_delete_removes_collector(repository: CollectorRepository) -> None:
    collector = _collector()
    await repository.create(collector)

    await repository.delete(collector.id)

    with pytest.raises(EntityNotFoundError):
        await repository.get(collector.id)


async def test_delete_missing_raises(repository: CollectorRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.delete(uuid4())
