import logging
from typing import Any

import pymongo
import redis
from celery import Celery

from app.config import settings
from app.event.models import Event
from app.event.repository import to_document

logger = logging.getLogger(__name__)

celery_app = Celery("automater", broker=settings.redis_uri)

# Sync clients, deliberately separate from the rest of the app's async
# motor/redis clients (app/database.py, app/dependencies.py) -- a Celery
# worker task runs synchronously, so it can't share an async client without
# spinning up an event loop per call. Both still point at the same Mongo
# database and Redis instance as the rest of the app; only the client type
# differs. Lazily constructed at import time (module-level, like
# celery_app itself), reused across every task invocation in this worker
# process.
_mongo_client: pymongo.MongoClient = pymongo.MongoClient(settings.mongo_uri)
_events_collection = _mongo_client.get_default_database()["events"]
_redis_client: redis.Redis = redis.Redis.from_url(settings.redis_uri)


def _events_channel(project_id: str) -> str:
    return f"events:{project_id}"


# The only Celery action v1.1 ships: structured logging of a rule
# match/clear transition, now persisted (not just logged) so the frontend's
# per-project Events sidebar and Overview summary have something to read.
# See iotops-workspace/ROADMAP.md's "Events sidebar" note for the Mongo-
# not-TimescaleDB reasoning. Kwargs match exactly what custom-telegraf's
# outputs/celery plugin puts in the task body (measurement name, tags --
# including matched_rule/matched_rule_id/automater_id/project_id/flag/
# rule_* the rule processor stamped on, see rule.go's annotate() -- fields,
# and timestamp). `flag` is "match" (this occurrence just started firing)
# or "clear" (it just stopped) -- both go through this one task,
# distinguished by tag, rather than separate tasks, since both are still
# just one Event document with a different `flag`.
@celery_app.task(name="automater.tasks.log_rule_match")
def log_rule_match(
    measurement: str,
    tags: dict[str, Any],
    fields: dict[str, Any],
    timestamp: str,
) -> None:
    logger.info(
        "rule %s: rule=%s severity=%s table=%s at=%s tags=%s fields=%s",
        tags.get("flag"),
        tags.get("matched_rule"),
        tags.get("rule_severity"),
        measurement,
        timestamp,
        tags,
        fields,
    )

    event = Event(
        project_id=tags["project_id"],
        automater_id=tags["automater_id"],
        rule_id=tags["matched_rule_id"],
        rule_name=tags.get("matched_rule", ""),
        table=measurement,
        category=tags.get("rule_category", ""),
        severity=tags.get("rule_severity", "low"),
        event_type=tags.get("rule_event_type", ""),
        message=fields.get("rule_message", ""),
        flag=tags["flag"],
        identifier_keys=[k for k in tags.get("identifier_keys", "").split(",") if k],
        resolve_mode=tags.get("resolve_mode", "auto"),
        tags=tags,
        fields=fields,
        matched_at=timestamp,
    )
    _events_collection.insert_one(to_document(event))

    # Fire-and-forget: if nobody's subscribed (no dashboard open for this
    # project right now), PUBLISH is a no-op -- the event is already
    # durably in Mongo either way, so a missed live update just means the
    # sidebar catches up on its next fetch, not lost data.
    _redis_client.publish(_events_channel(str(event.project_id)), event.model_dump_json())
