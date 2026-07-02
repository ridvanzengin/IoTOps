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

    assert [plugin.name for plugin in inputs] == ["mqtt"]
    assert [plugin.name for plugin in outputs] == ["timescaledb"]


def test_list_without_category_returns_everything() -> None:
    registry = build_default_registry()

    assert len(registry.list()) == 2


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
