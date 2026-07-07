from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.dashboard.models import Dashboard
from app.dashboard.repository import DashboardRepository
from app.shared.exceptions import DuplicateNameError, EntityNotFoundError


@pytest.fixture
def repository() -> DashboardRepository:
    database = AsyncMongoMockClient()["iotops"]
    return DashboardRepository(database)


def _dashboard(**overrides: object) -> Dashboard:
    defaults: dict[str, object] = {"project_id": uuid4(), "name": "Hive Overview"}
    defaults.update(overrides)
    return Dashboard(**defaults)


async def test_create_and_get(repository: DashboardRepository) -> None:
    dashboard = _dashboard()

    await repository.create(dashboard)
    fetched = await repository.get(dashboard.id)

    assert fetched == dashboard


async def test_create_rejects_duplicate_name(repository: DashboardRepository) -> None:
    await repository.create(_dashboard(name="Hive Overview"))

    with pytest.raises(DuplicateNameError):
        await repository.create(_dashboard(name="Hive Overview"))


async def test_get_missing_raises(repository: DashboardRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.get(uuid4())


async def test_list_returns_all_created(repository: DashboardRepository) -> None:
    first = _dashboard(name="Hive Overview")
    second = _dashboard(name="Greenhouse Overview")
    await repository.create(first)
    await repository.create(second)

    dashboards = await repository.list()

    assert {d.id for d in dashboards} == {first.id, second.id}


async def test_update_persists_changes(repository: DashboardRepository) -> None:
    dashboard = _dashboard()
    await repository.create(dashboard)

    dashboard.description = "Updated"
    await repository.update(dashboard)
    fetched = await repository.get(dashboard.id)

    assert fetched.description == "Updated"
    assert fetched.updated_at >= dashboard.created_at


async def test_update_rejects_rename_to_existing_name(repository: DashboardRepository) -> None:
    first = _dashboard(name="Hive Overview")
    second = _dashboard(name="Greenhouse Overview")
    await repository.create(first)
    await repository.create(second)

    second.name = "Hive Overview"
    with pytest.raises(DuplicateNameError):
        await repository.update(second)


async def test_update_missing_raises(repository: DashboardRepository) -> None:
    dashboard = _dashboard()

    with pytest.raises(EntityNotFoundError):
        await repository.update(dashboard)


async def test_delete_removes_dashboard(repository: DashboardRepository) -> None:
    dashboard = _dashboard()
    await repository.create(dashboard)

    await repository.delete(dashboard.id)

    with pytest.raises(EntityNotFoundError):
        await repository.get(dashboard.id)


async def test_delete_missing_raises(repository: DashboardRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.delete(uuid4())
