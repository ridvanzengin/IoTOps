from uuid import uuid4

import pytest

from app.plugin.models import Plugin
from app.plugin.registry import PluginRegistry, build_default_registry
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


def test_validate_configuration_accepts_matching_schema() -> None:
    registry = build_default_registry()

    registry.validate_configuration(
        "mqtt", {"servers": ["tcp://mosquitto:1883"], "topics": ["hive/+"]}
    )


def test_validate_configuration_rejects_missing_required_field() -> None:
    registry = build_default_registry()

    with pytest.raises(PluginConfigurationError):
        registry.validate_configuration("mqtt", {"servers": ["tcp://mosquitto:1883"]})


def test_register_overrides_existing_plugin_of_same_name() -> None:
    registry = PluginRegistry()
    first = Plugin(
        id=uuid4(),
        name="custom",
        category=PluginCategory.PROCESSOR,
        telegraf_name="custom",
        version="1.0.0",
        configuration_schema={"type": "object"},
    )
    second = Plugin(
        id=uuid4(),
        name="custom",
        category=PluginCategory.PROCESSOR,
        telegraf_name="custom",
        version="2.0.0",
        configuration_schema={"type": "object"},
    )

    registry.register(first)
    registry.register(second)

    assert registry.get("custom").version == "2.0.0"
    assert len(registry.list()) == 1
