from collections.abc import AsyncIterator
from uuid import UUID

import redis.asyncio as async_redis
from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_async_redis_client, get_event_service
from app.event.models import Event, EventRuleCount
from app.event.service import EventService

router = APIRouter(prefix="/api/event", tags=["event"])


@router.get("", response_model=list[Event])
async def list_events(
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    service: EventService = Depends(get_event_service),
) -> list[Event]:
    return await service.list(project_id, limit)


@router.get("/counts", response_model=list[EventRuleCount])
async def get_event_counts(
    project_id: UUID | None = Query(default=None),
    service: EventService = Depends(get_event_service),
) -> list[EventRuleCount]:
    return await service.counts_by_rule(project_id)


@router.get("/stream")
async def stream_events(
    project_id: UUID,
    redis_client: async_redis.Redis = Depends(get_async_redis_client),
) -> EventSourceResponse:
    return EventSourceResponse(_subscribe(redis_client, project_id))


async def _subscribe(redis_client: async_redis.Redis, project_id: UUID) -> AsyncIterator[dict[str, str]]:
    # Channel name must match app/automater/tasks.py's _events_channel() --
    # that's the only contract between the Celery worker (publisher) and
    # this endpoint (subscriber); they never call into each other directly.
    channel = f"events:{project_id}"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            yield {"event": "event", "data": data.decode() if isinstance(data, bytes) else data}
    finally:
        # Runs when the client disconnects (EventSourceResponse cancels
        # this generator) -- without it, every closed browser tab would
        # leak a subscription on this Redis connection forever.
        await pubsub.unsubscribe(channel)
        await pubsub.close()
