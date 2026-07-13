from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

import redis.asyncio as async_redis
from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_async_redis_client, get_event_service
from app.event.models import Event, EventRuleCount, Occurrence, ProjectUnresolvedCount
from app.event.service import EventService

router = APIRouter(prefix="/api/event", tags=["event"])


@router.get("", response_model=list[Event])
async def list_events(
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    # Repeated ?rule_id=...&rule_id=... query params -- used by the
    # Panel-overlay feature to fetch a specific set of Rules' events for
    # a panel's resolved time window. See iotops-workspace/ROADMAP.md's
    # "Events-as-overlay on Panel charts" note.
    rule_id: list[UUID] | None = Query(default=None),
    service: EventService = Depends(get_event_service),
) -> list[Event]:
    return await service.list(project_id, limit, since, until, rule_id)


@router.get("/counts", response_model=list[EventRuleCount])
async def get_event_counts(
    project_id: UUID | None = Query(default=None),
    service: EventService = Depends(get_event_service),
) -> list[EventRuleCount]:
    return await service.counts_by_rule(project_id)


@router.get("/occurrences", response_model=list[Occurrence])
async def list_occurrences(
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    service: EventService = Depends(get_event_service),
) -> list[Occurrence]:
    return await service.list_occurrences(project_id, limit)


@router.get("/unresolved-counts", response_model=list[ProjectUnresolvedCount])
async def get_unresolved_counts(
    service: EventService = Depends(get_event_service),
) -> list[ProjectUnresolvedCount]:
    return await service.unresolved_counts_by_project()


@router.get("/stream")
async def stream_events(
    redis_client: async_redis.Redis = Depends(get_async_redis_client),
) -> EventSourceResponse:
    # No project_id -- one connection per session (opened once at the app
    # shell root), not one per project panel. See iotops-workspace/
    # ROADMAP.md's "Events sidebar polish" note: feeds both the activity
    # bar's per-project unresolved counts and whichever project's panel
    # is currently open, client-side filtered by project_id.
    return EventSourceResponse(_subscribe(redis_client))


async def _subscribe(redis_client: async_redis.Redis) -> AsyncIterator[dict[str, str]]:
    # Pattern subscribe across every project's channel -- app/automater/
    # tasks.py's _events_channel() is unchanged (still publishes to
    # events:{project_id} per project), only how this endpoint listens
    # changed. PSUBSCRIBE messages carry type == "pmessage", not
    # "message" -- easy to miss when switching from subscribe(), and
    # missing it makes the stream connect successfully but silently
    # deliver nothing.
    pattern = "events:*"
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe(pattern)
    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            data = message["data"]
            yield {"event": "event", "data": data.decode() if isinstance(data, bytes) else data}
    finally:
        # Runs when the client disconnects (EventSourceResponse cancels
        # this generator) -- without it, every closed browser tab would
        # leak a subscription on this Redis connection forever.
        await pubsub.punsubscribe(pattern)
        await pubsub.close()
