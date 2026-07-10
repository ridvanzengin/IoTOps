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


class Condition(BaseModel):
    column: str
    operator: ConditionOperator
    value: float | str | bool


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

    # The hypertable this rule evaluates against -- a topic maps to exactly
    # one table (see custom-telegraf's outputs.postgresql create_templates,
    # which never creates more than one table per topic), and conditions
    # within a single rule always share one table (no cross-table
    # correlation, see iotops-workspace/ROADMAP.md), so this lives once per
    # Rule rather than being repeated on every Condition.
    table: str

    operator: RuleOperator = RuleOperator.AND
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


class Automater(AutomaterPluginsBase):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    status: CollectorStatus = CollectorStatus.CREATED
    docker: DockerConfig | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
