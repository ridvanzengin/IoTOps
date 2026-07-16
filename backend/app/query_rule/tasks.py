import asyncio
import logging

import asyncpg
import redis.asyncio as async_redis
from motor.motor_asyncio import AsyncIOMotorClient

from app.celery_app import celery_app
from app.config import settings
from app.event.repository import EventRepository
from app.query_rule.repository import QueryRuleRepository
from app.query_rule.service import QueryRuleService
from app.telemetry.repository import TelemetryRepository

logger = logging.getLogger(__name__)

# One fixed-cadence tick, not a dynamic per-QueryRule Celery Beat schedule
# -- no dynamic Beat scheduler exists in this stack (nothing like
# django-celery-beat/celery-redbeat), and each QueryRule already knows its
# own due-ness (QueryRuleService.evaluate_due checks every enabled rule's
# stored interval/cron against its last_evaluated_at). 30s gives
# reasonable precision for realistic (1m+) QueryRule intervals without
# hammering Mongo. See iotops-workspace/ROADMAP.md's "Query Rules" note.
celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule["evaluate-due-query-rules"] = {
    "task": "query_rule.tasks.evaluate_due_query_rules",
    "schedule": 30.0,
}


@celery_app.task(name="query_rule.tasks.evaluate_due_query_rules")
def evaluate_due_query_rules() -> None:
    asyncio.run(_evaluate_due_query_rules())


async def _evaluate_due_query_rules() -> None:
    # Fresh clients per tick, not the FastAPI app's shared singletons
    # (app/database.py, app/dependencies.py) -- those are bound to that
    # process's own event loop, and asyncio.run() spins up a new one on
    # every call, so reusing a pool/client created under a different loop
    # would break. A connection-setup cost every 30s is a non-issue at
    # this scale (same stance already taken elsewhere in this codebase --
    # see the events-pairing-on-every-read comment in ROADMAP.md).
    mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri)
    # Small pool, not asyncpg's default (min_size=10, max_size=10) -- this
    # opens and closes every 30s alongside the backend's own long-lived
    # pool (app/database.py) on the same connection-constrained shared
    # TimescaleDB instance (see the production deployment plan).
    timescale_pool = await asyncpg.create_pool(
        settings.timescale_uri, min_size=1, max_size=3
    )
    redis_client = async_redis.from_url(settings.redis_uri)
    try:
        database = mongo_client.get_default_database()
        service = QueryRuleService(
            repository=QueryRuleRepository(database),
            telemetry_repository=TelemetryRepository(timescale_pool),
            event_repository=EventRepository(database, pubsub_redis_client=redis_client),
        )
        await service.evaluate_due()
    except Exception:
        logger.exception("evaluate_due_query_rules tick failed")
    finally:
        await timescale_pool.close()
        await redis_client.aclose()
        mongo_client.close()
