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

    # Names (not values -- those are already in `tags` under their own
    # keys) of the Rule's configured dedup identifiers, stamped by
    # rule.go's annotate() as the identifier_keys tag. Lets a consumer
    # tell which of `tags` are the rule's identifiers vs. incidental tags
    # like `host`, needed to group raw match/clear events into
    # occurrences (see iotops-workspace/ROADMAP.md's "Events sidebar
    # polish" note). Empty for events written before this field existed,
    # or for a rule with no configured identifiers.
    identifier_keys: list[str] = Field(default_factory=list)

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


class OccurrenceStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class Occurrence(BaseModel):
    """One match/clear pair (or a lone trailing match, if it hasn't
    cleared yet) -- what the events list actually renders, not the raw
    `Event` stream. See EventRepository._pair_occurrences for how these
    are built and iotops-workspace/ROADMAP.md's "Events sidebar polish"
    note for the settled semantics: an occurrence never reopens once
    resolved -- the same rule/identifiers firing again after a clear is a
    new occurrence, not the old one flipping back to active.
    """

    rule_id: UUID
    rule_name: str
    category: str
    severity: RuleSeverity
    event_type: str
    message: str
    identifiers: dict[str, str]
    status: OccurrenceStatus
    matched_at: datetime
    resolved_at: datetime | None = None

    # Beyond the roadmap's originally-proposed minimal shape: the card
    # redesign's detail drawer needs raw tags/fields and attribution ids,
    # and baking them in here (from the match event) avoids a second
    # lazy-fetch endpoint for a payload-size concern that's not worth
    # optimizing at this feature's scale (same stance already taken on
    # pairing cost/retention).
    automater_id: UUID
    project_id: UUID
    tags: dict[str, str]
    fields: dict[str, Any]


class ProjectUnresolvedCount(BaseModel):
    project_id: UUID
    count: int
