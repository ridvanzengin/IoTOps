from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.automater.models import RuleSeverity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventFlag(str, Enum):
    MATCH = "match"
    CLEAR = "clear"


class Event(BaseModel):
    """One match/clear occurrence from a Rule, written by the Celery worker
    (app/automater/tasks.py's log_rule_match) from exactly the tags/fields
    the Go rule processor already stamped onto the metric (see rule.go's
    annotate()) -- this model doesn't invent any new data, it persists what
    was already arriving and previously only logged.

    Deliberately stored in Mongo, not TimescaleDB: an event is a discrete,
    variably-shaped structured document (its `tags`/`fields` snapshot
    differs per rule/table), not a continuous numeric series, and match/
    clear + TTL dedup already keeps volume low -- this is closer to the
    documents Mongo already stores for Collector/Automater config than to
    telemetry. See iotops-workspace/ROADMAP.md's "Events sidebar" note.
    """

    id: UUID = Field(default_factory=uuid4)

    # Attribution -- see the DeployedRule model (app/plugin/processors/
    # rule.py): the persisted Rule domain model doesn't carry these (a
    # Rule's container is implicit via Automater.rules), but the Go plugin
    # config generated at deploy time does, so every matched metric's tags
    # carry them back here.
    project_id: UUID
    automater_id: UUID
    rule_id: UUID
    rule_name: str

    table: str
    category: str = ""
    severity: RuleSeverity = RuleSeverity.LOW
    event_type: str = ""
    message: str = ""
    flag: EventFlag

    # Full snapshot of the matched metric, for anything not promoted to
    # its own field above (identifiers, other tags/fields the rule didn't
    # reference).
    tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)

    # The metric's own timestamp (when the underlying condition was
    # observed), distinct from created_at (when this Event document was
    # written -- always slightly later, once the message travels through
    # Redis and the Celery worker).
    matched_at: datetime
    created_at: datetime = Field(default_factory=_utcnow)


class EventRuleCount(BaseModel):
    project_id: UUID
    rule_id: UUID
    rule_name: str
    count: int
