from typing import Any

import jsonschema

from app.plugin.models import Plugin, plugin_id
from app.shared.enums import PluginCategory
from app.shared.exceptions import EntityNotFoundError, PluginConfigurationError


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, plugin_type: str) -> Plugin:
        try:
            return self._plugins[plugin_type]
        except KeyError:
            raise EntityNotFoundError("Plugin", plugin_type) from None

    def list(self, category: PluginCategory | None = None) -> list[Plugin]:
        plugins = list(self._plugins.values())
        if category is not None:
            plugins = [plugin for plugin in plugins if plugin.category == category]
        return plugins

    def validate_configuration(self, plugin_type: str, configuration: dict[str, Any]) -> None:
        plugin = self.get(plugin_type)
        try:
            jsonschema.validate(configuration, plugin.configuration_schema)
        except jsonschema.ValidationError as exc:
            raise PluginConfigurationError(plugin_type, exc.message) from exc


def _mqtt_input_plugin() -> Plugin:
    return Plugin(
        id=plugin_id("mqtt"),
        name="mqtt",
        category=PluginCategory.INPUT,
        telegraf_name="mqtt_consumer",
        description="Subscribes to an MQTT broker and ingests telemetry messages.",
        configuration_schema={
            "type": "object",
            "required": ["servers", "topics"],
            "properties": {
                "servers": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "topics": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "qos": {"type": "integer", "minimum": 0, "maximum": 2},
                "data_format": {"type": "string"},
            },
        },
        supported_platforms=["linux/amd64", "linux/arm64"],
    )


def _timescaledb_output_plugin() -> Plugin:
    return Plugin(
        id=plugin_id("timescaledb"),
        name="timescaledb",
        category=PluginCategory.OUTPUT,
        telegraf_name="postgresql",
        description="Writes telemetry measurements into a TimescaleDB hypertable.",
        configuration_schema={
            "type": "object",
            "required": ["connection", "table"],
            "properties": {
                "connection": {"type": "string"},
                "table": {"type": "string"},
            },
        },
        supported_platforms=["linux/amd64", "linux/arm64"],
    )


def build_default_registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.register(_mqtt_input_plugin())
    registry.register(_timescaledb_output_plugin())
    return registry
