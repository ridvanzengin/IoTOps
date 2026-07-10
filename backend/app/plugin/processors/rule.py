from pydantic import Field

from app.automater.models import Rule
from app.plugin.common import CommonOpts, advanced_field


class RuleProcessorConfig(CommonOpts):
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = advanced_field(default="")
    # Rule dedup state and the Celery broker (app/plugin/outputs/celery.py)
    # share one Redis instance in practice; separate default DBs (0 vs 1)
    # keep them from colliding without requiring two Redis deployments.
    redis_db: int = 0

    rules: list[Rule] = Field(min_length=1)
