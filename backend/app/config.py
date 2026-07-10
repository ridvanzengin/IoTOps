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


settings = Settings()
