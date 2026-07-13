import pytest
from pydantic import BaseModel

from app.plugin.registry import PluginDefinition, PluginRegistry, build_default_registry
from app.shared.enums import PluginCategory
from app.shared.exceptions import EntityNotFoundError, PluginConfigurationError


def test_default_registry_contains_builtin_plugins() -> None:
    registry = build_default_registry()

    mqtt = registry.get("mqtt")
    timescaledb = registry.get("timescaledb")

    assert mqtt.category == PluginCategory.INPUT
    assert timescaledb.category == PluginCategory.OUTPUT


def test_get_unknown_plugin_raises() -> None:
    registry = build_default_registry()

    with pytest.raises(EntityNotFoundError):
        registry.get("does-not-exist")


def test_list_filters_by_category() -> None:
    registry = build_default_registry()

    inputs = registry.list(category=PluginCategory.INPUT)
    outputs = registry.list(category=PluginCategory.OUTPUT)
    processors = registry.list(category=PluginCategory.PROCESSOR)

    assert [plugin.name for plugin in inputs] == ["mqtt", "kafka", "http", "amqp"]
    assert [plugin.name for plugin in outputs] == ["timescaledb", "celery", "http_forward"]
    assert [plugin.name for plugin in processors] == ["rule"]


def test_list_without_category_returns_everything() -> None:
    registry = build_default_registry()

    # mqtt/kafka/http/amqp (inputs), timescaledb + celery + http_forward
    # (outputs), rule (processor) -- see app/plugin/registry.py's
    # build_default_registry().
    assert len(registry.list()) == 8


def test_plugin_schema_exposes_field_defaults_for_form_prefill() -> None:
    registry = build_default_registry()

    mqtt = registry.get("mqtt")

    assert mqtt.configuration_schema["properties"]["servers"]["default"] == ["tcp://mosquitto:1883"]
    assert mqtt.configuration_schema["properties"]["qos"]["default"] == 0


def test_validate_configuration_fills_in_defaults() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration("mqtt", {"topics": ["hive/+"]})

    assert validated["servers"] == ["tcp://mosquitto:1883"]
    assert validated["topics"] == ["hive/+"]
    assert validated["qos"] == 0


def test_validate_configuration_rejects_constraint_violation() -> None:
    registry = build_default_registry()

    with pytest.raises(PluginConfigurationError):
        registry.validate_configuration("mqtt", {"servers": []})


def test_mqtt_schema_includes_common_opts_marked_advanced() -> None:
    registry = build_default_registry()

    mqtt = registry.get("mqtt")
    properties = mqtt.configuration_schema["properties"]

    assert properties["namepass"]["advanced"] is True
    assert properties["servers"].get("advanced") is None


def test_validate_configuration_excludes_unset_optional_fields() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration("mqtt", {})

    assert "username" not in validated
    assert "tls_ca" not in validated
    assert "servers" in validated


def test_kafka_registered_with_real_telegraf_plugin_name() -> None:
    registry = build_default_registry()

    kafka = registry.get("kafka")

    assert kafka.category == PluginCategory.INPUT
    assert kafka.telegraf_name == "kafka_consumer"


def test_kafka_validate_configuration_fills_in_defaults() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration("kafka", {"topics": ["device.telemetry"]})

    assert validated["brokers"] == ["localhost:9092"]
    assert validated["topics"] == ["device.telemetry"]
    assert validated["data_format"] == "json"


def test_http_registered_with_real_telegraf_plugin_name() -> None:
    registry = build_default_registry()

    http = registry.get("http")

    assert http.category == PluginCategory.INPUT
    assert http.telegraf_name == "http_listener_v2"


def test_http_validate_configuration_fills_in_defaults() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration("http", {})

    assert validated["service_address"] == "tcp://:8080"
    assert validated["paths"] == ["/telegraf"]
    assert validated["methods"] == ["POST", "PUT"]


def test_amqp_registered_with_real_telegraf_plugin_name() -> None:
    registry = build_default_registry()

    amqp = registry.get("amqp")

    assert amqp.category == PluginCategory.INPUT
    assert amqp.telegraf_name == "amqp_consumer"


def test_amqp_validate_configuration_fills_in_defaults() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration("amqp", {"queue": "device-events"})

    assert validated["brokers"] == ["amqp://localhost:5672/influxdb"]
    assert validated["exchange"] == "telegraf"
    assert validated["queue"] == "device-events"
    assert validated["binding_key"] == "#"


def test_http_forward_registered_with_real_telegraf_plugin_name() -> None:
    registry = build_default_registry()

    http_forward = registry.get("http_forward")

    assert http_forward.category == PluginCategory.OUTPUT
    assert http_forward.telegraf_name == "http"


def test_http_forward_validate_configuration_round_trips_url() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration(
        "http_forward", {"url": "http://iotops-automater-abc:8080/telegraf"}
    )

    assert validated["url"] == "http://iotops-automater-abc:8080/telegraf"
    assert validated["data_format"] == "influx"


def test_new_input_plugins_share_json_parser_field_pattern_with_mqtt() -> None:
    # tag_keys/json_string_fields are Telegraf's generic JSON-parser
    # options (see kafka.py's own comment), not MQTT-specific -- confirms
    # all three new input plugins expose them the same way mqtt does, so
    # AutomaterEditor's Dedup Identifiers prefill keeps working generically
    # regardless of which input plugin type produced a table.
    registry = build_default_registry()

    for plugin_name in ("kafka", "http", "amqp"):
        schema = registry.get(plugin_name).configuration_schema
        assert "tag_keys" in schema["properties"]
        assert "json_string_fields" in schema["properties"]


def test_timescaledb_schema_property_uses_telegraf_schema_alias() -> None:
    registry = build_default_registry()

    timescaledb = registry.get("timescaledb")

    assert "schema" in timescaledb.configuration_schema["properties"]
    assert "pgr_schema" not in timescaledb.configuration_schema["properties"]


def test_validate_configuration_dumps_schema_field_by_alias() -> None:
    registry = build_default_registry()

    validated = registry.validate_configuration("timescaledb", {"schema": "analytics"})

    assert validated["schema"] == "analytics"
    assert "pgr_schema" not in validated


def test_register_overrides_existing_plugin_of_same_name() -> None:
    class CustomConfig(BaseModel):
        value: str = "default"

    registry = PluginRegistry()
    first = PluginDefinition(
        name="custom",
        category=PluginCategory.PROCESSOR,
        telegraf_name="custom",
        config_model=CustomConfig,
        version="1.0.0",
    )
    second = PluginDefinition(
        name="custom",
        category=PluginCategory.PROCESSOR,
        telegraf_name="custom",
        config_model=CustomConfig,
        version="2.0.0",
    )

    registry.register(first)
    registry.register(second)

    assert registry.get("custom").version == "2.0.0"
    assert len(registry.list()) == 1
