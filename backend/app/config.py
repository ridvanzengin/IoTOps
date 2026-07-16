from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://mongo:27017/iotops"
    timescale_uri: str = "postgresql://iotops:iotops@timescaledb:5432/iotops"
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    # The Celery broker URL -- db 1, matching CeleryOutputConfig's own
    # default `redis_db` (see app/plugin/outputs/celery.py), since that's
    # the database the rule/celery Telegraf plugins actually enqueue tasks
    # into by default. Used by the celery-worker service (app/automater/
    # tasks.py), which is what actually consumes them.
    redis_uri: str = "redis://redis:6379/1"
    # DB 0 -- matches RuleProcessorConfig's own `redis_db` default (see
    # app/plugin/processors/rule.py), the dedup/firing-key database rule.go
    # actually writes to. Only used by EventRepository.resolve_occurrence
    # to delete a firing key on manual resolve -- separate from redis_uri
    # (DB 1, the Celery broker/SSE-pubsub database) since they're different
    # logical databases on the same Redis instance.
    automater_firing_redis_uri: str = "redis://redis:6379/0"
    frontend_origin: str = "http://localhost:5173"
    runtime_dir: str = "runtime"
    host_runtime_dir: str = ""
    docker_network: str = "iotops"
    telegraf_image: str = "telegraf:1.32-alpine"
    automater_telegraf_image: str = "custom-telegraf:latest"
    # host.docker.internal, not localhost: the backend runs inside a
    # container (see docker-compose.yml), so "localhost" would mean the
    # container itself, not the host machine running Ollama.
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "gemma4:latest"
    # False by default -- full read/write functionality out of the box for
    # local dev and self-hosters. The public demo deployment sets DEMO=true
    # explicitly in its own environment; this is not the repo's default.
    demo: bool = False
    # Lets examples/demo/seed.py's own provisioning requests through
    # block_in_demo_mode() (app/dependencies.py) without weakening the
    # public-facing gate itself. Empty by default -- only a production
    # deployment sets this (matching the value it also passes to
    # demo-showcase's DEMO_SEED_TOKEN env var).
    demo_seed_token: str = ""
    # Independent of demo/DEMO -- applied to every new hypertable regardless
    # of mode. 14 days is a sane out-of-the-box default so telemetry doesn't
    # grow unbounded by default; override via env for a different window.
    retention_days: int = 14


settings = Settings()
