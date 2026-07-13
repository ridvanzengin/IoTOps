from typing import Literal

from pydantic import Field

from app.plugin.common import CommonOpts, advanced_field


class KafkaConsumerConfig(CommonOpts):
    brokers: list[str] = Field(default=["localhost:9092"], min_length=1)
    topics: list[str] = Field(default=["telegraf"], min_length=1)
    topic_tag: str | None = advanced_field()
    consumer_group: str = advanced_field(default="telegraf_metrics_consumers")
    offset: Literal["oldest", "newest"] = advanced_field(default="oldest")
    data_format: Literal["influx", "json", "value"] = "json"

    # Same generic Telegraf JSON-parser options as MqttConsumerConfig --
    # not Kafka-specific, these get inlined into any input plugin's TOML
    # table when data_format="json" (see DATA_FORMATS_INPUT.md). Mirrored
    # per-plugin rather than factored into CommonOpts so each plugin's
    # config schema stays self-contained and independently form-renderable.
    tag_keys: list[str] = Field(default=[])
    json_string_fields: list[str] = Field(default=[])

    json_time_key: str | None = advanced_field()
    json_time_format: str | None = advanced_field()
    json_timezone: str | None = advanced_field()

    data_type: Literal["int", "float", "string", "bool"] | None = advanced_field()

    client_id: str | None = advanced_field(default="Telegraf")
    max_undelivered_messages: int = advanced_field(default=1000)

    sasl_username: str | None = advanced_field()
    sasl_password: str | None = advanced_field()
    sasl_mechanism: str | None = advanced_field()

    enable_tls: bool = advanced_field(default=False)
    tls_ca: str | None = advanced_field()
    tls_cert: str | None = advanced_field()
    tls_key: str | None = advanced_field()
    insecure_skip_verify: bool = advanced_field(default=False)
