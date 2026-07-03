from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dashboard.models import Dashboard
from app.shared.exceptions import DuplicateNameError, EntityNotFoundError


def _to_document(dashboard: Dashboard) -> dict[str, Any]:
    document = dashboard.model_dump(mode="json")
    document["_id"] = document.pop("id")
    return document


def _from_document(document: dict[str, Any]) -> Dashboard:
    document = dict(document)
    document["id"] = document.pop("_id")
    return Dashboard.model_validate(document)


class DashboardRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["dashboards"]

    async def create(self, dashboard: Dashboard) -> Dashboard:
        if await self._collection.find_one({"name": dashboard.name}):
            raise DuplicateNameError("Dashboard", dashboard.name)
        await self._collection.insert_one(_to_document(dashboard))
        return dashboard

    async def get(self, dashboard_id: UUID) -> Dashboard:
        document = await self._collection.find_one({"_id": str(dashboard_id)})
        if document is None:
            raise EntityNotFoundError("Dashboard", dashboard_id)
        return _from_document(document)

    async def list(self) -> list[Dashboard]:
        documents = await self._collection.find().to_list(length=None)
        return [_from_document(document) for document in documents]

    async def update(self, dashboard: Dashboard) -> Dashboard:
        existing_with_name = await self._collection.find_one({"name": dashboard.name})
        if existing_with_name is not None and existing_with_name["_id"] != str(dashboard.id):
            raise DuplicateNameError("Dashboard", dashboard.name)

        dashboard.updated_at = datetime.now(timezone.utc)
        result = await self._collection.replace_one(
            {"_id": str(dashboard.id)}, _to_document(dashboard)
        )
        if result.matched_count == 0:
            raise EntityNotFoundError("Dashboard", dashboard.id)
        return dashboard

    async def delete(self, dashboard_id: UUID) -> None:
        result = await self._collection.delete_one({"_id": str(dashboard_id)})
        if result.deleted_count == 0:
            raise EntityNotFoundError("Dashboard", dashboard_id)
