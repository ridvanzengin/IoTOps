from typing import Literal

from pydantic import Field

from app.plugin.common import CommonOpts, advanced_field


class MqttConsumerConfig(CommonOpts):
    servers: list[str] = Field(default=["tcp://mosquitto:1883"], min_length=1)
    topics: list[str] = Field(default=["telemetry/#"], min_length=1)
    topic_tag: str | None = advanced_field()
    qos: Literal[0, 1, 2] = 0
    data_format: Literal["influx", "json", "value"] = "json"

    # Telegraf's JSON parser silently drops any string-valued key unless it's
    # listed here; without this, e.g. a device_id or status string vanishes
    # with no error. tag_keys promotes JSON keys to queryable tags instead.
    tag_keys: list[str] = Field(default=[])
    json_string_fields: list[str] = Field(default=[])

    json_time_key: str | None = advanced_field()
    json_time_format: str | None = advanced_field()
    json_timezone: str | None = advanced_field()

    # Required when data_format="value": tells the parser what type the raw
    # (non-JSON) payload bytes should be interpreted as.
    data_type: Literal["int", "float", "string", "bool"] | None = advanced_field()

    persistent_session: bool = advanced_field(default=False)
    client_id: str | None = advanced_field()

    connection_timeout: str = advanced_field(default="30s")
    keepalive: str = advanced_field(default="60s")
    ping_timeout: str = advanced_field(default="10s")
    max_undelivered_messages: int = advanced_field(default=1000)

    username: str | None = advanced_field()
    password: str | None = advanced_field()

    tls_ca: str | None = advanced_field()
    tls_cert: str | None = advanced_field()
    tls_key: str | None = advanced_field()
    insecure_skip_verify: bool = advanced_field(default=False)
    tls_server_name: str | None = advanced_field()
    tls_renegotiation_method: Literal["never", "once", "freely"] = advanced_field(default="never")

    client_trace: bool = advanced_field(default=False)
