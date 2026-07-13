from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.shared.enums import CollectorStatus
from app.shared.models import DockerConfig, Pipeline


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuleOperator(str, Enum):
    AND = "AND"
    OR = "OR"


class ConditionOperator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="


class RuleSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolveMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class Condition(BaseModel):
    column: str
    operator: ConditionOperator
    value: float | str | bool

    # How this condition combines with the running result of every
    # condition before it in the Rule's list -- evaluated strictly
    # left-to-right, no precedence, no parentheses ("a AND b OR c" is
    # always (a AND b) OR c). Ignored for a Rule's first condition, since
    # there's no prior result yet to combine with. Lives on Condition, not
    # Rule, so mixed chains like "a==1 AND b>3 OR c<5" are expressible --
    # a single per-Rule operator (the original flat design) could only ever
    # be all-AND or all-OR. See ROADMAP.md's per-condition join note.
    join: RuleOperator = RuleOperator.AND


class Rule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str = ""
    category: str = ""
    event_type: str = ""
    severity: RuleSeverity = RuleSeverity.LOW
    message: str = ""
    enabled: bool = True
    priority: int = 0

    # auto (default): a clear event auto-fires the moment the condition
    # stops matching, same as every rule behaved before this field
    # existed. manual: custom-telegraf's rule.go never auto-clears --
    # the occurrence stays active until a human resolves it from the
    # Events sidebar. See iotops-workspace/ROADMAP.md's "Event resolution
    # mode" note. Flows straight through to RuleConfig's `toml:"resolve_mode"`
    # tag (see app/plugin/processors/rule.py, rule.go's RuleConfig).
    resolve_mode: ResolveMode = ResolveMode.AUTO

    # The hypertable this rule evaluates against -- a topic maps to exactly
    # one table (see custom-telegraf's outputs.postgresql create_templates,
    # which never creates more than one table per topic), and conditions
    # within a single rule always share one table (no cross-table
    # correlation, see iotops-workspace/ROADMAP.md), so this lives once per
    # Rule rather than being repeated on every Condition.
    table: str

    conditions: list[Condition]

    # Dedup parameters, per rule (see iotops-workspace/ROADMAP.md's Redis
    # dedup mechanics) -- not part of the original domain-models.md Rule
    # sketch, needed once rule matches actually reach a Redis-backed
    # processor rather than staying a documented-only shape.
    identifiers: list[str] = Field(default_factory=list)
    ttl: str = "5m"

    @model_validator(mode="after")
    def _validate_conditions(self) -> "Rule":
        if not self.conditions:
            raise ValueError("Rule must contain at least one condition")
        return self


class AutomaterPluginsBase(Pipeline):
    rules: list[Rule]

    @model_validator(mode="after")
    def _validate_rules(self) -> "AutomaterPluginsBase":
        if not self.rules:
            raise ValueError("Automater must contain at least one rule")
        return self


class AutomaterInput(AutomaterPluginsBase):
    pass


class CreateRuleRequest(BaseModel):
    project_id: UUID
    rule: Rule

    # Either automater_id (attach to an existing Automater in this
    # project) or automater_name (+ collector_id, to derive the new
    # Automater's input) must be given -- enforced in
    # AutomaterService.create_rule, not here, since it's a cross-field
    # business rule rather than a shape constraint.
    automater_id: UUID | None = None
    automater_name: str | None = None
    automater_description: str = ""
    collector_id: UUID | None = None


class SetRuleEnabledRequest(BaseModel):
    enabled: bool


class Automater(AutomaterPluginsBase):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    status: CollectorStatus = CollectorStatus.CREATED
    docker: DockerConfig | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
