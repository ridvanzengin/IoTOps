from uuid import UUID

from app.project.models import Project, ProjectInput
from app.project.repository import ProjectRepository


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    async def create(self, payload: ProjectInput) -> Project:
        project = Project(**payload.model_dump())
        return await self._repository.create(project)

    async def get(self, project_id: UUID) -> Project:
        return await self._repository.get(project_id)

    async def list(self) -> list[Project]:
        return await self._repository.list()

    async def update(self, project_id: UUID, payload: ProjectInput) -> Project:
        existing = await self._repository.get(project_id)
        updated = existing.model_copy(
            update={
                "name": payload.name,
                "description": payload.description,
            }
        )
        return await self._repository.update(updated)

    async def delete(self, project_id: UUID) -> None:
        await self._repository.delete(project_id)
