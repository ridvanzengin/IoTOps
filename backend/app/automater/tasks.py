import logging
from typing import Any

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery("automater", broker=settings.redis_uri)


# The only Celery action v1.1 ships: structured logging of a rule
# match/clear transition. See iotops-workspace/ROADMAP.md's "already
# decided" list -- send-email/webhook/MQTT-publish actions are deferred.
# Kwargs match exactly what custom-telegraf's outputs/celery plugin puts in
# the task body (measurement name, tags -- including the matched_rule/
# flag/rule_* tags the rule processor stamped on -- fields, and timestamp).
# `flag` is "match" (this occurrence just started firing) or "clear" (it
# just stopped) -- both go through this one task, distinguished by tag,
# rather than separate tasks, since both are still just structured logging.
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
