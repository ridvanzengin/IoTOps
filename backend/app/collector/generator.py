from typing import Any

import tomli_w

from app.collector.models import Collector, InputPlugin, OutputPlugin, ProcessorPlugin
from app.plugin.registry import PluginRegistry

PluginInstance = InputPlugin | ProcessorPlugin | OutputPlugin


def generate_toml(collector: Collector, registry: PluginRegistry) -> str:
    document: dict[str, Any] = {
        "agent": {"interval": "10s", "flush_interval": "10s"},
    }
    _merge_section(document, "inputs", collector.inputs, registry)
    _merge_section(document, "processors", collector.processors, registry)
    _merge_section(document, "outputs", collector.outputs, registry)
    return tomli_w.dumps(document)


def _merge_section(
    document: dict[str, Any],
    section_name: str,
    plugin_instances: list[PluginInstance],
    registry: PluginRegistry,
) -> None:
    section: dict[str, list[dict[str, Any]]] = {}
    for instance in plugin_instances:
        if not instance.enabled:
            continue
        validated_configuration = registry.validate_configuration(
            instance.plugin_type, instance.configuration
        )
        plugin = registry.get(instance.plugin_type)
        section.setdefault(plugin.telegraf_name, []).append(validated_configuration)
    if section:
        document[section_name] = section
