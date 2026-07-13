from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import TypeAdapter

from app.event.models import (
    Event,
    EventFlag,
    EventRuleCount,
    Occurrence,
    OccurrenceStatus,
    ProjectUnresolvedCount,
)

_datetime_adapter = TypeAdapter(datetime)


def _serialize_datetime(value: datetime) -> str:
    """matched_at is stored as the ISO-8601 string Event.model_dump
    (mode="json") produces (see to_document below) -- not a native BSON
    date -- so a $gte/$lte range bound has to be formatted identically
    (same Pydantic datetime serializer) for string comparison to line up
    with what's actually stored."""
    return _datetime_adapter.dump_python(value, mode="json")


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


def _occurrence_from(match: Event, resolved_by: Event | None) -> Occurrence:
    identifiers = {key: match.tags.get(key, "") for key in match.identifier_keys}
    return Occurrence(
        rule_id=match.rule_id,
        rule_name=match.rule_name,
        category=match.category,
        severity=match.severity,
        event_type=match.event_type,
        message=match.message,
        identifiers=identifiers,
        status=OccurrenceStatus.RESOLVED if resolved_by is not None else OccurrenceStatus.ACTIVE,
        matched_at=match.matched_at,
        resolved_at=resolved_by.matched_at if resolved_by is not None else None,
        automater_id=match.automater_id,
        project_id=match.project_id,
        tags=match.tags,
        fields=match.fields,
    )


def _pair_occurrences(events: list[Event]) -> list[Occurrence]:
    """Groups events by (rule_id, identifier values) and walks each group
    pairing a match with the next clear after it. `events` must already be
    sorted by matched_at ascending.

    The group key mirrors rule.go's firingKey grouping exactly, including
    its empty-identifiers behavior: an event with no identifier_keys
    groups under (rule_id, ()) alone, so firing state -- and occurrence
    identity -- is shared across every instance of that rule, same as
    firingKey's zero-identifiers branch. Diverging from that grouping
    here would silently produce different occurrences than what the Go
    plugin's Redis dedup actually enforces.

    A repeat match while one is already open, or a stray clear with
    nothing open, shouldn't happen given Go's firing-state suppression --
    handled defensively (ignored) rather than raising, since this reads
    from whatever's actually in Mongo, not a source this code controls.
    """
    groups: dict[tuple[UUID, tuple[tuple[str, str], ...]], list[Event]] = defaultdict(list)
    for event in events:
        identifiers = {key: event.tags.get(key, "") for key in event.identifier_keys}
        group_key = (event.rule_id, tuple(sorted(identifiers.items())))
        groups[group_key].append(event)

    occurrences: list[Occurrence] = []
    for group_events in groups.values():
        open_match: Event | None = None
        for event in group_events:
            if event.flag == EventFlag.MATCH:
                if open_match is None:
                    open_match = event
            elif open_match is not None:
                occurrences.append(_occurrence_from(open_match, resolved_by=event))
                open_match = None
        if open_match is not None:
            occurrences.append(_occurrence_from(open_match, resolved_by=None))
    return occurrences


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

    # Also defined before `list` below, same reasoning as counts_by_rule
    # above.
    async def list_occurrences(self, project_id: UUID | None = None, limit: int = 50) -> list[Occurrence]:
        query: dict[str, Any] = {}
        if project_id is not None:
            query["project_id"] = str(project_id)
        documents = await self._collection.find(query).sort("matched_at", 1).to_list(length=None)
        occurrences = _pair_occurrences([_from_document(document) for document in documents])
        occurrences.sort(key=lambda o: o.resolved_at or o.matched_at, reverse=True)
        return occurrences[:limit]

    async def unresolved_counts_by_project(self) -> list[ProjectUnresolvedCount]:
        # Not project-scoped -- the activity bar needs every project's
        # count in one call. New aggregation logic, not a reuse of
        # counts_by_rule (which counts lifetime matches, not currently-
        # open occurrences) -- see iotops-workspace/ROADMAP.md's
        # "Events sidebar polish" gotcha note.
        documents = await self._collection.find({}).sort("matched_at", 1).to_list(length=None)
        occurrences = _pair_occurrences([_from_document(document) for document in documents])
        counts: dict[UUID, int] = defaultdict(int)
        for occurrence in occurrences:
            if occurrence.status == OccurrenceStatus.ACTIVE:
                counts[occurrence.project_id] += 1
        return [ProjectUnresolvedCount(project_id=project_id, count=count) for project_id, count in counts.items()]

    async def list(
        self,
        project_id: UUID | None = None,
        limit: int = 50,
        since: datetime | None = None,
        until: datetime | None = None,
        rule_ids: list[UUID] | None = None,
    ) -> list[Event]:
        query: dict[str, Any] = {}
        if project_id is not None:
            query["project_id"] = str(project_id)
        if rule_ids:
            query["rule_id"] = {"$in": [str(rule_id) for rule_id in rule_ids]}
        matched_at_range: dict[str, Any] = {}
        if since is not None:
            matched_at_range["$gte"] = _serialize_datetime(since)
        if until is not None:
            matched_at_range["$lte"] = _serialize_datetime(until)
        if matched_at_range:
            query["matched_at"] = matched_at_range
        documents = (
            await self._collection.find(query)
            .sort("matched_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        return [_from_document(document) for document in documents]
