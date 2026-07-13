from typing import Literal

from pydantic import Field

from app.plugin.common import CommonOpts, advanced_field


class HttpListenerConfig(CommonOpts):
    """`http_listener_v2` -- a webhook-style push endpoint (Telegraf listens,
    the source pushes to it), not `inputs.http`'s poll-a-URL model. Matches
    this platform's existing push-based ingestion shape (MQTT subscribes,
    this listens) rather than adding an interval-driven pull source. See
    iotops-workspace/ROADMAP.md's data-sources note.
    """

    service_address: str = Field(default="tcp://:8080")
    paths: list[str] = Field(default=["/telegraf"], min_length=1)
    methods: list[str] = Field(default=["POST", "PUT"])
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

    path_tag: bool = advanced_field(default=False)
    http_success_code: int = advanced_field(default=204)
    read_timeout: str = advanced_field(default="10s")
    write_timeout: str = advanced_field(default="10s")
    max_body_size: str = advanced_field(default="500MB")
    data_source: Literal["body", "query"] = advanced_field(default="body")

    basic_username: str | None = advanced_field()
    basic_password: str | None = advanced_field()

    tls_cert: str | None = advanced_field()
    tls_key: str | None = advanced_field()
