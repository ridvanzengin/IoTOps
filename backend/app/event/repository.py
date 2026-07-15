import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as async_redis
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import TypeAdapter

from app.event.models import (
    Event,
    EventFlag,
    EventRuleCount,
    Occurrence,
    OccurrenceStatus,
    ProjectUnresolvedCount,
    ResolveMode,
)
from app.shared.exceptions import EntityNotFoundError, InvalidOperationError

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
        id=match.id,
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
        source_type=match.source_type,
        automater_id=match.automater_id,
        query_rule_id=match.query_rule_id,
        project_id=match.project_id,
        tags=match.tags,
        fields=match.fields,
        resolve_mode=match.resolve_mode,
        resolution_notes=resolved_by.resolution_notes if resolved_by is not None else None,
    )


def _firing_key(match: Event) -> str:
    """Reconstructs rule.go's firingKey() exactly, from the *match* Event's
    own captured rule_name/rule_id/tags/fields -- not the Rule's current
    live state, since a Rule can be renamed after it fires and the
    original key was built with the name at match time (rc.Name), not
    just the ID (see firingKey's own comment in rule.go).

    SHA-256 over UTF-8 bytes of "|".join(values), hex-encoded, where each
    value is identifier_keys[i] looked up in tags then fields, string-
    formatted -- mirrors Go's identifierValue()'s tag-then-field lookup
    and %v formatting. Numeric identifier values are a known, accepted
    edge case: Go's %v float formatting doesn't always byte-match Python's
    str(), so the hash (and thus the DEL below) can silently miss for a
    non-string identifier -- the firing key then just survives until its
    TTL naturally expires, a safe degradation, not a bug that corrupts
    state. In practice identifiers are almost always tags (strings), where
    this is a non-issue.
    """
    if not match.identifier_keys:
        return f"automater:firing:{match.rule_name}:{match.rule_id}"
    values: list[str] = []
    for key in match.identifier_keys:
        if key in match.tags:
            values.append(str(match.tags[key]))
        else:
            values.append(str(match.fields.get(key, "")))
    digest = hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()
    return f"automater:firing:{match.rule_name}:{match.rule_id}:{digest}"


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

    def __init__(
        self,
        database: AsyncIOMotorDatabase,
        pubsub_redis_client: async_redis.Redis | None = None,
        firing_redis_client: async_redis.Redis | None = None,
    ) -> None:
        self._collection = database["events"]
        # Both optional: only resolve_occurrence needs them, and existing
        # read-only call sites (tests, anywhere not wiring the manual-
        # resolve feature) shouldn't have to supply Redis clients they'll
        # never use.
        self._pubsub_redis_client = pubsub_redis_client
        self._firing_redis_client = firing_redis_client

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
    async def _query_occurrences(
        self,
        project_id: UUID | None,
        since: datetime | None,
        rule_ids: list[UUID] | None,
        status: OccurrenceStatus | None,
        search: str | None,
    ) -> list[Occurrence]:
        """Shared by list_occurrences and occurrence_counts_by_rule -- both
        need "every Occurrence matching these filters", just consumed
        differently (a sliced page vs. a per-rule tally), and computing it
        once here is what guarantees a page's `total` and a rule chip's
        count can never structurally drift apart the way the badge/list
        mismatch did before filtering was pushed server-side at all.

        `since` bounds the raw Mongo fetch to `matched_at >= since` --
        deliberately not a `[since, until]` window: "last 1h" means
        "occurrences whose match happened in the last hour", full stop, so
        there's never an upper bound to apply (a still-active occurrence's
        clear, if any, is always in the future relative to its match, and a
        resolved one's clear is irrelevant to whether the *match* falls in
        the window). This also bounds the read itself, not just the
        result -- a narrow window keeps the fetch+pair small regardless of
        a project's total history size, the same property that makes
        pagination here viable without a dedicated aggregation pipeline.

        `status` and `search` are both derived/text properties that can't
        be pushed into the Mongo query dict (see list_occurrences' own
        prior comment on `status`), so both are applied as a Python filter
        after pairing.
        """
        query: dict[str, Any] = {}
        if project_id is not None:
            query["project_id"] = str(project_id)
        if rule_ids:
            query["rule_id"] = {"$in": [str(rule_id) for rule_id in rule_ids]}
        if since is not None:
            query["matched_at"] = {"$gte": _serialize_datetime(since)}
        documents = await self._collection.find(query).sort("matched_at", 1).to_list(length=None)
        occurrences = _pair_occurrences([_from_document(document) for document in documents])
        if status is not None:
            occurrences = [o for o in occurrences if o.status == status]
        needle = search.strip().lower() if search else ""
        if needle:
            # rule_name/message/category/event_type alone under-match badly
            # whenever a rule was authored with placeholder/test names (e.g.
            # a scratch query rule literally named "sdf") -- the only thing
            # actually distinguishing one occurrence from another is then
            # its identifiers (the chips rendered on the card, e.g.
            # "hive_id: hive-5"), so those have to be searchable too, or
            # search silently stops working the moment rule naming stops
            # being descriptive.
            occurrences = [
                o
                for o in occurrences
                if needle in o.rule_name.lower()
                or needle in o.message.lower()
                or needle in o.category.lower()
                or needle in o.event_type.lower()
                or any(needle in key.lower() or needle in value.lower() for key, value in o.identifiers.items())
            ]
        occurrences.sort(key=lambda o: o.matched_at, reverse=True)
        return occurrences

    async def list_occurrences(
        self,
        project_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
        rule_ids: list[UUID] | None = None,
        status: OccurrenceStatus | None = None,
        since: datetime | None = None,
        search: str | None = None,
    ) -> tuple[list[Occurrence], int]:
        occurrences = await self._query_occurrences(project_id, since, rule_ids, status, search)
        return occurrences[offset : offset + limit], len(occurrences)

    async def occurrence_counts_by_rule(
        self,
        project_id: UUID,
        since: datetime | None = None,
        search: str | None = None,
    ) -> list[EventRuleCount]:
        """Same shape as counts_by_rule, but counts paired Occurrences, not
        raw match-flag documents -- these aren't the same number whenever
        _pair_occurrences defensively drops a repeat match received while
        one's already open (stale/duplicate data, or a dedup gap upstream).
        EventsPanel's rule filter chips need this one: a chip's count has
        to equal how many cards clicking it actually reveals, which is a
        count of Occurrences (also time/search-filtered the same way the
        list is), not Events. counts_by_rule itself is left alone --
        Home.tsx's "lifetime activity" stat is a legitimate, different
        question ("how many times has this fired ever"), and answering it
        as a real Mongo aggregation instead of a full fetch+pair is worth
        keeping fast for an unscoped, all-projects homepage load.

        Project-scoped only (unlike counts_by_rule, which also serves an
        all-projects call): status/pairing is a derived, cross-document
        property with no Mongo-side aggregation here, so answering this
        without a project_id would repeat a full-collection-scan cost on
        every call, not just once at home-page load.
        """
        occurrences = await self._query_occurrences(project_id, since, None, None, search)
        counts: dict[UUID, EventRuleCount] = {}
        for occurrence in occurrences:
            existing = counts.get(occurrence.rule_id)
            if existing is None:
                counts[occurrence.rule_id] = EventRuleCount(
                    project_id=occurrence.project_id,
                    rule_id=occurrence.rule_id,
                    rule_name=occurrence.rule_name,
                    count=1,
                )
            else:
                existing.count += 1
        return sorted(counts.values(), key=lambda c: c.count, reverse=True)

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

    async def create(self, event: Event) -> Event:
        """Writes a new match/clear Event and publishes it over the same
        `events:{project_id}` SSE channel resolve_occurrence/log_rule_match
        use, so an open sidebar reconciles it live with no new frontend
        logic. Used directly by writers that can share this repository's
        async motor client -- e.g. app/query_rule/service.py's scheduled
        evaluator -- unlike the Go-plugin path, which runs through a
        separate sync Celery worker that can't share it (see
        app/automater/tasks.py's own comment on why).
        """
        await self._collection.insert_one(to_document(event))
        if self._pubsub_redis_client is not None:
            channel = f"events:{event.project_id}"
            await self._pubsub_redis_client.publish(channel, event.model_dump_json())
        return event

    async def resolve_occurrence(self, match_event_id: UUID, notes: str) -> Occurrence:
        """Manually resolves a still-open occurrence from a manual-resolve
        Rule (see iotops-workspace/ROADMAP.md's "Event resolution mode"
        note) -- writes a synthetic `clear` Event (so this reuses
        _pair_occurrences/_occurrence_from exactly as an auto-clear would),
        deletes the underlying Redis firing key (DB 0, distinct from the
        pub/sub client's DB 1) so the rule can fire fresh immediately if
        the condition is still true, and publishes the synthetic event over
        the same SSE channel tasks.py's log_rule_match uses, so an open
        sidebar reconciles it live with no new frontend pairing logic.
        """
        document = await self._collection.find_one({"_id": str(match_event_id)})
        if document is None:
            raise EntityNotFoundError("Event", match_event_id)
        match = _from_document(document)
        if match.flag != EventFlag.MATCH:
            raise InvalidOperationError(f"Event {match_event_id} is not a match event")
        if match.resolve_mode != ResolveMode.MANUAL:
            raise InvalidOperationError(f"Rule {match.rule_name!r} is not manual-resolve")

        identifiers = {key: match.tags.get(key, "") for key in match.identifier_keys}
        group_key = tuple(sorted(identifiers.items()))
        later_events = await self._collection.find(
            {"rule_id": str(match.rule_id), "matched_at": {"$gt": document["matched_at"]}}
        ).to_list(length=None)
        for later_document in later_events:
            later = _from_document(later_document)
            later_identifiers = {key: later.tags.get(key, "") for key in later.identifier_keys}
            if later.flag == EventFlag.CLEAR and tuple(sorted(later_identifiers.items())) == group_key:
                raise InvalidOperationError(f"Occurrence {match_event_id} is already resolved")

        resolved_event = Event(
            project_id=match.project_id,
            source_type=match.source_type,
            automater_id=match.automater_id,
            query_rule_id=match.query_rule_id,
            rule_id=match.rule_id,
            rule_name=match.rule_name,
            table=match.table,
            category=match.category,
            severity=match.severity,
            event_type=match.event_type,
            message=match.message,
            flag=EventFlag.CLEAR,
            identifier_keys=match.identifier_keys,
            resolve_mode=match.resolve_mode,
            resolution_notes=notes,
            tags=match.tags,
            fields=match.fields,
            matched_at=datetime.now(timezone.utc),
        )
        if self._firing_redis_client is not None and match.source_type == "automater":
            # Firing keys only ever exist for Go-plugin-produced matches --
            # a query_rule-sourced occurrence has no Redis dedup key to
            # delete (its re-arm semantics come from the next scheduled
            # evaluation cycle instead, see app/query_rule/service.py).
            # Best-effort otherwise: see _firing_key's own comment on why a
            # miss here (non-string identifier formatting divergence) is a
            # safe degradation, not an error worth failing the resolve over.
            await self._firing_redis_client.delete(_firing_key(match))

        await self.create(resolved_event)

        return _occurrence_from(match, resolved_by=resolved_event)
