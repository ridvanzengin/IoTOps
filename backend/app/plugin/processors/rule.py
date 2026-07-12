from uuid import UUID

from pydantic import Field

from app.automater.models import Rule
from app.plugin.common import CommonOpts, advanced_field


class DeployedRule(Rule):
    """A Rule plus the Automater/Project it's being deployed under.

    The persisted `Rule` domain model doesn't carry these -- a Rule's
    container is implicit via `Automater.rules`, and duplicating that back
    onto every stored Rule document would be redundant. But the Go plugin
    needs them to stamp onto every matched metric (see rule.go's
    annotate()), so the Celery event consumer can attribute an event back
    to a project without a reverse DB lookup. AutomaterService
    ._synthesize_rule_processor builds one of these per rule at TOML-
    generation time, from the Automater being deployed, not from user
    input -- this model is never user-facing.
    """

    automater_id: UUID
    project_id: UUID


class RuleProcessorConfig(CommonOpts):
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = advanced_field(default="")
    # Rule dedup state and the Celery broker (app/plugin/outputs/celery.py)
    # share one Redis instance in practice; separate default DBs (0 vs 1)
    # keep them from colliding without requiring two Redis deployments.
    redis_db: int = 0

    rules: list[DeployedRule] = Field(min_length=1)
