from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.dashboard.models import (
    Dashboard,
    GaugeChart,
    LineChart,
    Panel,
    PanelPosition,
    Query,
    SeriesConfig,
    Variable,
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


def test_panel_defaults_to_no_event_overlay() -> None:
    panel = _panel()

    assert panel.event_rule_ids == []


def test_panel_accepts_event_rule_ids() -> None:
    rule_id = uuid4()

    panel = _panel(event_rule_ids=[rule_id])

    assert panel.event_rule_ids == [rule_id]


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


def test_variable_rejects_invalid_name() -> None:
    with pytest.raises(ValidationError, match="valid identifier"):
        Variable(name="1bad", label="Bad", table="hives", value_column="id")


def test_variable_rejects_reserved_name() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        Variable(name="__timeFrom", label="Reserved", table="hives", value_column="id")


def test_variable_requires_table_and_value_column() -> None:
    with pytest.raises(ValidationError):
        Variable(name="hive", label="Hive")


def test_variable_predicate_column_requires_predicate_variable() -> None:
    with pytest.raises(ValidationError, match="must be set together"):
        Variable(
            name="hive",
            label="Hive",
            table="hives",
            value_column="id",
            predicate_column="project_id",
        )


def test_variable_predicate_variable_requires_predicate_column() -> None:
    with pytest.raises(ValidationError, match="must be set together"):
        Variable(
            name="hive",
            label="Hive",
            table="hives",
            value_column="id",
            predicate_variable="project",
        )


def test_variable_allows_predicate_column_and_variable_together() -> None:
    variable = Variable(
        name="hive",
        label="Hive",
        table="hives",
        value_column="id",
        predicate_column="project_id",
        predicate_variable="project",
    )

    assert variable.predicate_column == "project_id"
    assert variable.predicate_variable == "project"


def test_dashboard_rejects_duplicate_variable_names() -> None:
    variables = [
        Variable(name="hive", label="Hive A", table="hives", value_column="id"),
        Variable(name="hive", label="Hive B", table="hives", value_column="id"),
    ]

    with pytest.raises(ValueError, match="Duplicate variable name"):
        Dashboard(project_id=uuid4(), name="Hive Overview", variables=variables)


def test_dashboard_rejects_variable_referencing_later_predicate_variable() -> None:
    variables = [
        Variable(
            name="device",
            label="Device",
            table="devices",
            value_column="device_id",
            predicate_column="project_id",
            predicate_variable="project",
        ),
        Variable(name="project", label="Project", table="projects", value_column="project_id"),
    ]

    with pytest.raises(ValueError, match="references undefined or later-defined"):
        Dashboard(project_id=uuid4(), name="Hive Overview", variables=variables)


def test_dashboard_allows_variable_referencing_earlier_predicate_variable() -> None:
    variables = [
        Variable(name="project", label="Project", table="projects", value_column="project_id"),
        Variable(
            name="device",
            label="Device",
            table="devices",
            value_column="device_id",
            predicate_column="project_id",
            predicate_variable="project",
        ),
    ]

    dashboard = Dashboard(project_id=uuid4(), name="Hive Overview", variables=variables)

    assert len(dashboard.variables) == 2


def test_line_chart_allows_additional_series_with_dual_axis() -> None:
    chart = LineChart(
        title="Temp + Humidity",
        x_axis="time",
        y_axis="temperature",
        series=[SeriesConfig(field="humidity", axis="right", type="bar")],
    )

    assert chart.series[0].field == "humidity"
    assert chart.series[0].axis == "right"
    assert chart.series[0].type == "bar"


def test_series_default_axis_is_left_and_type_inherits() -> None:
    series = SeriesConfig(field="humidity")

    assert series.axis == "left"
    assert series.type is None


def test_chart_rejects_series_field_duplicating_y_axis() -> None:
    with pytest.raises(ValidationError, match="Duplicate series field"):
        LineChart(
            title="Temp",
            x_axis="time",
            y_axis="temperature",
            series=[SeriesConfig(field="temperature")],
        )


def test_chart_rejects_duplicate_series_fields() -> None:
    with pytest.raises(ValidationError, match="Duplicate series field"):
        LineChart(
            title="Temp",
            x_axis="time",
            y_axis="temperature",
            series=[SeriesConfig(field="humidity"), SeriesConfig(field="humidity")],
        )


def test_chart_rejects_series_by_combined_with_series() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        LineChart(
            title="Metrics",
            x_axis="time",
            y_axis="value",
            series_by="device_id",
            series=[SeriesConfig(field="humidity")],
        )


def test_chart_accepts_series_by_alone() -> None:
    chart = LineChart(title="Metrics", x_axis="time", y_axis="value", series_by="device_id")

    assert chart.series_by == "device_id"
    assert chart.series == []
