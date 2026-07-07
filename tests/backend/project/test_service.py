from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.project.models import ProjectInput
from app.project.repository import ProjectRepository
from app.project.service import ProjectService
from app.shared.exceptions import EntityNotFoundError


@pytest.fixture
def service() -> ProjectService:
    database = AsyncMongoMockClient()["iotops"]
    return ProjectService(repository=ProjectRepository(database))


def _valid_input(**overrides: object) -> ProjectInput:
    defaults: dict[str, object] = {"name": "Beekeeping"}
    defaults.update(overrides)
    return ProjectInput(**defaults)


async def test_create_persists_and_returns_project(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    fetched = await service.get(project.id)
    assert fetched == project


async def test_list_returns_all_projects(service: ProjectService) -> None:
    await service.create(_valid_input(name="Beekeeping"))
    await service.create(_valid_input(name="Greenhouse"))

    projects = await service.list()

    assert {p.name for p in projects} == {"Beekeeping", "Greenhouse"}


async def test_update_replaces_editable_fields(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    updated = await service.update(project.id, _valid_input(name="Renamed"))

    assert updated.name == "Renamed"
    assert updated.id == project.id


async def test_update_missing_project_raises(service: ProjectService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.update(uuid4(), _valid_input())


async def test_delete_removes_project(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    await service.delete(project.id)

    with pytest.raises(EntityNotFoundError):
        await service.get(project.id)
