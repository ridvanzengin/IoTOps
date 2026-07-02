from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.plugin.inputs.mqtt import MqttConsumerConfig
from app.plugin.models import Plugin, plugin_id
from app.plugin.outputs.timescaledb import TimescaleDBOutputConfig
from app.shared.enums import PluginCategory
from app.shared.exceptions import EntityNotFoundError, PluginConfigurationError


@dataclass(frozen=True)
class PluginDefinition:
    name: str
    category: PluginCategory
    telegraf_name: str
    config_model: type[BaseModel]
    description: str = ""
    version: str = "1.0.0"
    supported_platforms: list[str] = field(default_factory=list)

    def to_plugin(self) -> Plugin:
        return Plugin(
            id=plugin_id(self.name),
            name=self.name,
            category=self.category,
            telegraf_name=self.telegraf_name,
            version=self.version,
            description=self.description,
            configuration_schema=self.config_model.model_json_schema(),
            supported_platforms=list(self.supported_platforms),
        )


class PluginRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, PluginDefinition] = {}

    def register(self, definition: PluginDefinition) -> None:
        self._definitions[definition.name] = definition

    def get(self, plugin_type: str) -> Plugin:
        return self._get_definition(plugin_type).to_plugin()

    def list(self, category: PluginCategory | None = None) -> list[Plugin]:
        definitions = self._definitions.values()
        if category is not None:
            definitions = [d for d in definitions if d.category == category]
        return [d.to_plugin() for d in definitions]

    def validate_configuration(
        self, plugin_type: str, configuration: dict[str, Any]
    ) -> dict[str, Any]:
        definition = self._get_definition(plugin_type)
        try:
            validated = definition.config_model.model_validate(configuration)
        except ValidationError as exc:
            raise PluginConfigurationError(plugin_type, str(exc)) from exc
        return validated.model_dump(mode="json")

    def _get_definition(self, plugin_type: str) -> PluginDefinition:
        try:
            return self._definitions[plugin_type]
        except KeyError:
            raise EntityNotFoundError("Plugin", plugin_type) from None


def build_default_registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.register(
        PluginDefinition(
            name="mqtt",
            category=PluginCategory.INPUT,
            telegraf_name="mqtt_consumer",
            config_model=MqttConsumerConfig,
            description="Subscribes to an MQTT broker and ingests telemetry messages.",
            supported_platforms=["linux/amd64", "linux/arm64"],
        )
    )
    registry.register(
        PluginDefinition(
            name="timescaledb",
            category=PluginCategory.OUTPUT,
            telegraf_name="postgresql",
            config_model=TimescaleDBOutputConfig,
            description="Writes telemetry measurements into a TimescaleDB hypertable.",
            supported_platforms=["linux/amd64", "linux/arm64"],
        )
    )
    return registry
