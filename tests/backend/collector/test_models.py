import pytest

from app.collector.models import Collector, InputPlugin, OutputPlugin
from app.shared.enums import CollectorStatus


def _input() -> InputPlugin:
    return InputPlugin(plugin_type="mqtt", name="hive-mqtt", configuration={"topic": "hive/+"})


def _output() -> OutputPlugin:
    return OutputPlugin(plugin_type="timescaledb", configuration={"connection": "postgres://"})


def test_collector_defaults() -> None:
    collector = Collector(name="Hive Collector", inputs=[_input()], outputs=[_output()])

    assert collector.status == CollectorStatus.CREATED
    assert collector.enabled is True
    assert collector.schema_version == 1
    assert collector.processors == []
    assert collector.docker is None


def test_collector_requires_at_least_one_input() -> None:
    with pytest.raises(ValueError, match="at least one input"):
        Collector(name="No Input", inputs=[], outputs=[_output()])


def test_collector_requires_at_least_one_output() -> None:
    with pytest.raises(ValueError, match="at least one output"):
        Collector(name="No Output", inputs=[_input()], outputs=[])


def test_collector_round_trips_through_json() -> None:
    collector = Collector(name="Hive Collector", inputs=[_input()], outputs=[_output()])

    restored = Collector.model_validate_json(collector.model_dump_json())

    assert restored == collector
