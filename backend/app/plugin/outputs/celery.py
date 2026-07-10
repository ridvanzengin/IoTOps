from app.plugin.common import CommonOpts, advanced_field


class CeleryOutputConfig(CommonOpts):
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = advanced_field(default="")
    # See RuleProcessorConfig.redis_db -- default DB 1 so the Celery broker
    # doesn't collide with the rule processor's dedup keys on the same
    # Redis instance.
    redis_db: int = 1

    target_queue: str = "celery"
    task_name: str
