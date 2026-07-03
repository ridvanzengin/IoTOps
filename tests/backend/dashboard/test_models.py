from uuid import uuid4

import pytest

from app.dashboard.models import (
    Dashboard,
    GaugeChart,
    LineChart,
    Panel,
    PanelPosition,
    Query,
)


def _panel(**overrides: object) -> Panel:
    defaults: dict[str, object] = {
        "title": "Temperature",
        "chart": LineChart(title="Temperature", x_axis="time", y_axis="temperature"),
        "query": Query(sql="SELECT * FROM device_metrics"),
        "position": PanelPosition(x=0, y=0, width=6, height=4),
    }
    defaults.update(overrides)
    return Panel(**defaults)


def test_dashboard_defaults() -> None:
    dashboard = Dashboard(project_id=uuid4(), name="Hive Overview")

    assert dashboard.schema_version == 1
    assert dashboard.panels == []
    assert dashboard.variables == []
    assert dashboard.layout == {}


def test_chart_discriminates_by_type() -> None:
    panel = _panel(chart=GaugeChart(title="Weight", value_field="weight"))

    assert panel.chart.type == "gauge"
    assert isinstance(panel.chart, GaugeChart)


def test_dashboard_rejects_overlapping_panels() -> None:
    first = _panel(position=PanelPosition(x=0, y=0, width=6, height=4))
    second = _panel(position=PanelPosition(x=3, y=0, width=6, height=4))

    with pytest.raises(ValueError, match="overlaps"):
        Dashboard(project_id=uuid4(), name="Hive Overview", panels=[first, second])


def test_dashboard_allows_non_overlapping_panels() -> None:
    first = _panel(position=PanelPosition(x=0, y=0, width=6, height=4))
    second = _panel(position=PanelPosition(x=6, y=0, width=6, height=4))

    dashboard = Dashboard(project_id=uuid4(), name="Hive Overview", panels=[first, second])

    assert len(dashboard.panels) == 2


def test_dashboard_round_trips_through_json() -> None:
    dashboard = Dashboard(project_id=uuid4(), name="Hive Overview", panels=[_panel()])

    restored = Dashboard.model_validate_json(dashboard.model_dump_json())

    assert restored == dashboard
