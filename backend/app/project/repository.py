from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.project.models import Project
from app.shared.exceptions import EntityNotFoundError


def _to_document(project: Project) -> dict[str, Any]:
    document = project.model_dump(mode="json")
    document["_id"] = document.pop("id")
    return document


def _from_document(document: dict[str, Any]) -> Project:
    document = dict(document)
    document["id"] = document.pop("_id")
    return Project.model_validate(document)


class ProjectRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["projects"]

    async def create(self, project: Project) -> Project:
        await self._collection.insert_one(_to_document(project))
        return project

    async def get(self, project_id: UUID) -> Project:
        document = await self._collection.find_one({"_id": str(project_id)})
        if document is None:
            raise EntityNotFoundError("Project", project_id)
        return _from_document(document)

    async def list(self) -> list[Project]:
        documents = await self._collection.find().to_list(length=None)
        return [_from_document(document) for document in documents]

    async def update(self, project: Project) -> Project:
        project.updated_at = datetime.now(timezone.utc)
        result = await self._collection.replace_one(
            {"_id": str(project.id)}, _to_document(project)
        )
        if result.matched_count == 0:
            raise EntityNotFoundError("Project", project.id)
        return project

    async def delete(self, project_id: UUID) -> None:
        result = await self._collection.delete_one({"_id": str(project_id)})
        if result.deleted_count == 0:
            raise EntityNotFoundError("Project", project_id)
