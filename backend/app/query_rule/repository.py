from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.query_rule.models import QueryRule
from app.shared.exceptions import EntityNotFoundError


def _to_document(query_rule: QueryRule) -> dict[str, Any]:
    document = query_rule.model_dump(mode="json")
    document["_id"] = document.pop("id")
    return document


def _from_document(document: dict[str, Any]) -> QueryRule:
    document = dict(document)
    document["id"] = document.pop("_id")
    return QueryRule.model_validate(document)


class QueryRuleRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["query_rules"]

    async def create(self, query_rule: QueryRule) -> QueryRule:
        await self._collection.insert_one(_to_document(query_rule))
        return query_rule

    async def get(self, query_rule_id: UUID) -> QueryRule:
        document = await self._collection.find_one({"_id": str(query_rule_id)})
        if document is None:
            raise EntityNotFoundError("QueryRule", query_rule_id)
        return _from_document(document)

    async def list(self, project_id: UUID | None = None) -> list[QueryRule]:
        query: dict[str, Any] = {}
        if project_id is not None:
            query["project_id"] = str(project_id)
        documents = await self._collection.find(query).to_list(length=None)
        return [_from_document(document) for document in documents]

    async def update(self, query_rule: QueryRule) -> QueryRule:
        query_rule.updated_at = datetime.now(timezone.utc)
        result = await self._collection.replace_one(
            {"_id": str(query_rule.id)}, _to_document(query_rule)
        )
        if result.matched_count == 0:
            raise EntityNotFoundError("QueryRule", query_rule.id)
        return query_rule

    async def delete(self, query_rule_id: UUID) -> None:
        result = await self._collection.delete_one({"_id": str(query_rule_id)})
        if result.deleted_count == 0:
            raise EntityNotFoundError("QueryRule", query_rule_id)
