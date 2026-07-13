from typing import Literal

from pydantic import Field

from app.plugin.common import CommonOpts, advanced_field


class AmqpConsumerConfig(CommonOpts):
    brokers: list[str] = Field(default=["amqp://localhost:5672/influxdb"], min_length=1)
    exchange: str = Field(default="telegraf")
    queue: str = Field(default="telegraf")
    # If unset, no binding is created between exchange and queue -- "#"
    # (match everything) is a sane default so a fresh Collector actually
    # receives messages without the user needing to know AMQP routing-key
    # syntax first.
    binding_key: str = Field(default="#")
    data_format: Literal["influx", "json", "value"] = "json"

    # Same generic Telegraf JSON-parser options as MqttConsumerConfig/
    # KafkaConsumerConfig -- see kafka.py's comment for why these are
    # mirrored per-plugin rather than shared.
    tag_keys: list[str] = Field(default=[])
    json_string_fields: list[str] = Field(default=[])

    json_time_key: str | None = advanced_field()
    json_time_format: str | None = advanced_field()
    json_timezone: str | None = advanced_field()

    data_type: Literal["int", "float", "string", "bool"] | None = advanced_field()

    exchange_type: Literal["direct", "fanout", "topic", "header", "x-consistent-hash"] = advanced_field(
        default="topic"
    )
    exchange_durability: Literal["transient", "durable"] = advanced_field(default="durable")
    queue_durability: Literal["transient", "durable"] = advanced_field(default="durable")

    prefetch_count: int = advanced_field(default=50)
    max_undelivered_messages: int = advanced_field(default=1000)
    timeout: str = advanced_field(default="30s")

    username: str | None = advanced_field()
    password: str | None = advanced_field()
    auth_method: Literal["PLAIN", "EXTERNAL"] = advanced_field(default="PLAIN")

    tls_ca: str | None = advanced_field()
    tls_cert: str | None = advanced_field()
    tls_key: str | None = advanced_field()
    insecure_skip_verify: bool = advanced_field(default=False)
