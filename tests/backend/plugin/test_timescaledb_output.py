import pytest

from app.config import settings
from app.plugin.outputs.timescaledb import TimescaleDBOutputConfig


def test_create_templates_defaults_to_14_day_retention() -> None:
    config = TimescaleDBOutputConfig()

    [statement] = config.create_templates
    assert "create_hypertable('{{.table}}', 'time')" in statement
    assert "add_retention_policy('{{.table}}', INTERVAL '14 days', if_not_exists => true)" in statement


def test_create_templates_follows_retention_days_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "retention_days", 30)

    config = TimescaleDBOutputConfig()

    [statement] = config.create_templates
    assert "INTERVAL '30 days'" in statement


@pytest.mark.parametrize("demo", [True, False])
def test_retention_is_unconditional_regardless_of_demo_mode(
    demo: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo", demo)

    config = TimescaleDBOutputConfig()

    [statement] = config.create_templates
    assert "add_retention_policy" in statement
