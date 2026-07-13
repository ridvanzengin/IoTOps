from typing import Any, Literal

from pydantic import Field

from app.plugin.common import CommonOpts, advanced_field

_JSON_PARSER_ONLY_FIELDS = (
    "tag_keys",
    "json_string_fields",
    "json_time_key",
    "json_time_format",
    "json_timezone",
    "data_type",
)


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

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        # tag_keys/json_string_fields/etc. are options parsers.json alone
        # understands. Telegraf's strict config validation crash-loops the
        # whole process if any of them are still present in the generated
        # TOML while data_format selects a different parser ("configuration
        # specified the fields [...], but they were not used") -- live-
        # verified while building the Collector-forwards-to-Automater fix
        # (see iotops-workspace/ROADMAP.md's "Automater fan-out strategy"
        # note, and AutomaterService._automater_scoped_configuration, which
        # forces data_format="influx" on the copy it hands to an Automater's
        # own listener). Stripped here rather than left to each caller to
        # remember, since the same crash would hit *any* http input a user
        # configures directly with a non-json data_format, not just a
        # forwarding-derived one.
        data = super().model_dump(**kwargs)
        if self.data_format != "json":
            for field_name in _JSON_PARSER_ONLY_FIELDS:
                data.pop(field_name, None)
        return data
