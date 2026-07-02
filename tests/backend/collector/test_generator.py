import tomllib

import pytest

from app.collector.generator import generate_toml
from app.collector.models import Collector, InputPlugin, OutputPlugin
from app.plugin.registry import build_default_registry
from app.shared.exceptions import PluginConfigurationError


def _collector(**overrides: object) -> Collector:
    defaults: dict[str, object] = {
        "name": "Hive Collector",
        "inputs": [
            InputPlugin(
                plugin_type="mqtt",
                name="hive-mqtt",
                configuration={"servers": ["tcp://mosquitto:1883"], "topics": ["hive/+"]},
            )
        ],
        "outputs": [
            OutputPlugin(
                plugin_type="timescaledb",
                configuration={
                    "connection": "postgres://iotops:iotops@timescaledb:5432/iotops",
                    "table": "telemetry",
                },
            )
        ],
    }
    defaults.update(overrides)
    return Collector(**defaults)


def test_generate_toml_includes_inputs_and_outputs() -> None:
    registry = build_default_registry()
    collector = _collector()

    toml_str = generate_toml(collector, registry)
    document = tomllib.loads(toml_str)

    assert document["inputs"]["mqtt_consumer"][0]["servers"] == ["tcp://mosquitto:1883"]
    assert document["outputs"]["postgresql"][0]["table"] == "telemetry"


def test_generate_toml_skips_disabled_plugins() -> None:
    registry = build_default_registry()
    collector = _collector(
        inputs=[
            InputPlugin(
                plugin_type="mqtt",
                name="hive-mqtt",
                enabled=False,
                configuration={"servers": ["tcp://mosquitto:1883"], "topics": ["hive/+"]},
            )
        ]
    )

    toml_str = generate_toml(collector, registry)
    document = tomllib.loads(toml_str)

    assert "inputs" not in document


def test_generate_toml_rejects_invalid_configuration() -> None:
    registry = build_default_registry()
    collector = _collector(
        inputs=[
            InputPlugin(
                plugin_type="mqtt",
                name="hive-mqtt",
                configuration={"servers": ["tcp://mosquitto:1883"]},
            )
        ]
    )

    with pytest.raises(PluginConfigurationError):
        generate_toml(collector, registry)
