from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.project.models import Project
from app.project.repository import ProjectRepository
from app.shared.exceptions import EntityNotFoundError


@pytest.fixture
def repository() -> ProjectRepository:
    database = AsyncMongoMockClient()["iotops"]
    return ProjectRepository(database)


def _project(**overrides: object) -> Project:
    defaults: dict[str, object] = {"name": "Beekeeping"}
    defaults.update(overrides)
    return Project(**defaults)


async def test_create_and_get(repository: ProjectRepository) -> None:
    project = _project()

    await repository.create(project)
    fetched = await repository.get(project.id)

    assert fetched == project


async def test_get_missing_raises(repository: ProjectRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.get(uuid4())


async def test_list_returns_all_created(repository: ProjectRepository) -> None:
    first = _project(name="Beekeeping")
    second = _project(name="Greenhouse")
    await repository.create(first)
    await repository.create(second)

    projects = await repository.list()

    assert {p.id for p in projects} == {first.id, second.id}


async def test_update_persists_changes(repository: ProjectRepository) -> None:
    project = _project()
    await repository.create(project)

    project.name = "Renamed Project"
    await repository.update(project)
    fetched = await repository.get(project.id)

    assert fetched.name == "Renamed Project"
    assert fetched.updated_at >= project.created_at


async def test_update_missing_raises(repository: ProjectRepository) -> None:
    project = _project()

    with pytest.raises(EntityNotFoundError):
        await repository.update(project)


async def test_delete_removes_project(repository: ProjectRepository) -> None:
    project = _project()
    await repository.create(project)

    await repository.delete(project.id)

    with pytest.raises(EntityNotFoundError):
        await repository.get(project.id)


async def test_delete_missing_raises(repository: ProjectRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.delete(uuid4())
