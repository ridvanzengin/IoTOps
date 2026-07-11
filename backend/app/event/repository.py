from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.event.models import Event, EventFlag, EventRuleCount


def to_document(event: Event) -> dict[str, Any]:
    """Public, not the usual leading-underscore repository-private helper:
    app/automater/tasks.py's sync Celery-task writer needs this exact same
    document shape and reuses it directly, rather than duplicating it --
    see that module's own comment on why it can't just call through this
    (async-only) repository instead."""
    document = event.model_dump(mode="json")
    document["_id"] = document.pop("id")
    return document


def _from_document(document: dict[str, Any]) -> Event:
    document = dict(document)
    document["id"] = document.pop("_id")
    return Event.model_validate(document)


class EventRepository:
    """Read side only (async, motor) -- events are written by the Celery
    worker, a separate sync process that can't share this async client
    (see app/automater/tasks.py's own sync pymongo writer). Both read the
    same `events` collection; the write shape (Event.model_dump) is the
    only contract between them.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["events"]

    # Defined before `list` below: a `list[...]` annotation on a method
    # that comes *after* a method literally named `list` in this same
    # class body would resolve `list` against the class namespace (already
    # rebound to that method), not the builtin -- see AutomaterService
    # ._synthesize_rule_processor's own comment on the same gotcha.
    async def counts_by_rule(self, project_id: UUID | None = None) -> list[EventRuleCount]:
        # Counts *matches* only, not clears -- a match/clear pair is one
        # incident, and "event counts per rule" reads naturally as
        # "how many times has this rule fired", not double-counted per
        # transition. See app/event/models.py's Event docstring.
        match_stage: dict[str, Any] = {"flag": EventFlag.MATCH.value}
        if project_id is not None:
            match_stage["project_id"] = str(project_id)
        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": {"project_id": "$project_id", "rule_id": "$rule_id", "rule_name": "$rule_name"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
        ]
        results = await self._collection.aggregate(pipeline).to_list(length=None)
        return [
            EventRuleCount(
                project_id=row["_id"]["project_id"],
                rule_id=row["_id"]["rule_id"],
                rule_name=row["_id"]["rule_name"],
                count=row["count"],
            )
            for row in results
        ]

    async def list(self, project_id: UUID | None = None, limit: int = 50) -> list[Event]:
        query: dict[str, Any] = {}
        if project_id is not None:
            query["project_id"] = str(project_id)
        documents = (
            await self._collection.find(query)
            .sort("matched_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        return [_from_document(document) for document in documents]
