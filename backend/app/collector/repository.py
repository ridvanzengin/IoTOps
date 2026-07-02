from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.collector.models import Collector
from app.shared.exceptions import EntityNotFoundError


def _to_document(collector: Collector) -> dict[str, Any]:
    document = collector.model_dump(mode="json")
    document["_id"] = document.pop("id")
    return document


def _from_document(document: dict[str, Any]) -> Collector:
    document = dict(document)
    document["id"] = document.pop("_id")
    return Collector.model_validate(document)


class CollectorRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["collectors"]

    async def create(self, collector: Collector) -> Collector:
        await self._collection.insert_one(_to_document(collector))
        return collector

    async def get(self, collector_id: UUID) -> Collector:
        document = await self._collection.find_one({"_id": str(collector_id)})
        if document is None:
            raise EntityNotFoundError("Collector", collector_id)
        return _from_document(document)

    async def list(self) -> list[Collector]:
        documents = await self._collection.find().to_list(length=None)
        return [_from_document(document) for document in documents]

    async def update(self, collector: Collector) -> Collector:
        collector.updated_at = datetime.now(timezone.utc)
        result = await self._collection.replace_one(
            {"_id": str(collector.id)}, _to_document(collector)
        )
        if result.matched_count == 0:
            raise EntityNotFoundError("Collector", collector.id)
        return collector

    async def delete(self, collector_id: UUID) -> None:
        result = await self._collection.delete_one({"_id": str(collector_id)})
        if result.deleted_count == 0:
            raise EntityNotFoundError("Collector", collector_id)
