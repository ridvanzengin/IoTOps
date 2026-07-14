from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.automater.models import ResolveMode, RuleSeverity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QueryRuleSchedule(BaseModel):
    """Exactly one of `interval`/`cron` must be set. `interval` reuses the
    same duration-string convention `Rule.ttl` already uses (e.g. "5m",
    "1h") -- parsed by app/query_rule/service.py's own small parser, not a
    new dependency. `cron` is a standard 5-field cron expression, parsed
    via croniter for real next-run semantics (day-of-week/month boundaries
    aren't worth hand-rolling). See iotops-workspace/ROADMAP.md's "Query
    Rules" note.
    """

    interval: str | None = None
    cron: str | None = None

    @model_validator(mode="after")
    def _validate_exactly_one(self) -> "QueryRuleSchedule":
        if (self.interval is None) == (self.cron is None):
            raise ValueError("QueryRuleSchedule requires exactly one of interval or cron")
        return self


class QueryRule(BaseModel):
    """A scheduled, cross-table SQL query evaluated periodically against
    TimescaleDB directly -- never through Telegraf/Collector/Automater
    (see app/automater/ for that, real-time, single-table path). Produces
    Event documents identical in shape to a real-time Rule's, just with
    source_type="query_rule" (app/event/models.py) -- the downstream
    Events pipeline (pairing, SSE, Panel overlays) needs no changes. See
    iotops-workspace/ROADMAP.md's "Query Rules" note for the full design.
    """

    id: UUID = Field(default_factory=uuid4)
    schema_version: int = 1
    project_id: UUID
    name: str
    description: str = ""

    sql: str
    # Kept for display/re-edit if this query was AI-generated -- None for
    # hand-written SQL.
    nl_prompt: str | None = None

    # Which SELECTed columns key a match -- the query's result rows are
    # the current match set, one row per matching entity. These columns'
    # values become the Occurrence's `identifiers`, exactly mirroring
    # Rule.identifiers (same "Identifiers" label at the UI layer too,
    # same optionality: Rule.identifiers also defaults to `[]` with no
    # "must have at least one" constraint -- a query with none is treated
    # as a single system-wide check, sharing one occurrence group across
    # every row it returns, mirroring rule.go's own zero-identifiers
    # branch (already covered for the real-time path by
    # test_list_occurrences_with_no_identifier_keys_groups_across_whole_rule).
    # A query intended to produce more than one independent match should
    # give at least one identifier column; that's on the author, not
    # something this field enforces.
    identifiers: list[str] = Field(default_factory=list)

    category: str = ""
    severity: RuleSeverity = RuleSeverity.LOW
    event_type: str = ""
    message: str = ""
    resolve_mode: ResolveMode = ResolveMode.AUTO

    schedule: QueryRuleSchedule
    enabled: bool = True
    # Stamped by the Celery Beat evaluator (app/query_rule/service.py) --
    # None until the first evaluation cycle runs.
    last_evaluated_at: datetime | None = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class QueryRuleInput(BaseModel):
    """Create/update payload -- mirrors AutomaterInput's pattern (plain
    fields the service copies onto a new/existing QueryRule). Simpler
    than Automater's own input: no "attach to existing X vs. create new"
    branching, a QueryRule is plain CRUD.
    """

    project_id: UUID
    name: str
    description: str = ""
    sql: str
    nl_prompt: str | None = None
    identifiers: list[str] = Field(default_factory=list)
    category: str = ""
    severity: RuleSeverity = RuleSeverity.LOW
    event_type: str = ""
    message: str = ""
    resolve_mode: ResolveMode = ResolveMode.AUTO
    schedule: QueryRuleSchedule
    enabled: bool = True


class QueryRulePreviewRequest(BaseModel):
    # Preview runs the SQL as typed, ahead of saving -- lets the author see
    # it's actually returning what they expect (and which columns exist to
    # pick as Identifiers) before committing to a schedule.
    sql: str
