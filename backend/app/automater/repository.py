from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.automater.models import Automater
from app.shared.exceptions import EntityNotFoundError


def _to_document(automater: Automater) -> dict[str, Any]:
    document = automater.model_dump(mode="json")
    document["_id"] = document.pop("id")
    return document


def _from_document(document: dict[str, Any]) -> Automater:
    document = dict(document)
    document["id"] = document.pop("_id")
    return Automater.model_validate(document)


class AutomaterRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["automaters"]

    async def create(self, automater: Automater) -> Automater:
        await self._collection.insert_one(_to_document(automater))
        return automater

    async def get(self, automater_id: UUID) -> Automater:
        document = await self._collection.find_one({"_id": str(automater_id)})
        if document is None:
            raise EntityNotFoundError("Automater", automater_id)
        return _from_document(document)

    async def list(self) -> list[Automater]:
        documents = await self._collection.find().to_list(length=None)
        return [_from_document(document) for document in documents]

    async def update(self, automater: Automater) -> Automater:
        automater.updated_at = datetime.now(timezone.utc)
        result = await self._collection.replace_one(
            {"_id": str(automater.id)}, _to_document(automater)
        )
        if result.matched_count == 0:
            raise EntityNotFoundError("Automater", automater.id)
        return automater

    async def delete(self, automater_id: UUID) -> None:
        result = await self._collection.delete_one({"_id": str(automater_id)})
        if result.deleted_count == 0:
            raise EntityNotFoundError("Automater", automater_id)
