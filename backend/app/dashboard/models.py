import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SeriesConfig(BaseModel):
    field: str
    label: str | None = None
    axis: Literal["left", "right"] = "left"
    type: Literal["line", "bar", "scatter"] | None = None


def _validate_series_fields(y_axis: str, series: list[SeriesConfig]) -> None:
    fields = [y_axis, *[s.field for s in series]]
    seen: set[str] = set()
    for field in fields:
        if field in seen:
            raise ValueError(f"Duplicate series field '{field}'")
        seen.add(field)


def _validate_series_by(series_by: str | None, series: list[SeriesConfig]) -> None:
    if series_by and series:
        raise ValueError("series_by and series are mutually exclusive")


class LineChart(BaseModel):
    type: Literal["line"] = "line"
    title: str
    x_axis: str
    y_axis: str
    series: list[SeriesConfig] = Field(default_factory=list)
    series_by: str | None = None
    legend: bool = True
    tooltip: bool = True
    zoom: bool = False
    theme: str = "default"

    @model_validator(mode="after")
    def _validate_series(self) -> "LineChart":
        _validate_series_by(self.series_by, self.series)
        _validate_series_fields(self.y_axis, self.series)
        return self


class BarChart(BaseModel):
    type: Literal["bar"] = "bar"
    title: str
    x_axis: str
    y_axis: str
    series: list[SeriesConfig] = Field(default_factory=list)
    series_by: str | None = None
    legend: bool = True
    tooltip: bool = True
    theme: str = "default"

    @model_validator(mode="after")
    def _validate_series(self) -> "BarChart":
        _validate_series_by(self.series_by, self.series)
        _validate_series_fields(self.y_axis, self.series)
        return self


class ScatterChart(BaseModel):
    type: Literal["scatter"] = "scatter"
    title: str
    x_axis: str
    y_axis: str
    series: list[SeriesConfig] = Field(default_factory=list)
    series_by: str | None = None
    legend: bool = True
    tooltip: bool = True
    theme: str = "default"

    @model_validator(mode="after")
    def _validate_series(self) -> "ScatterChart":
        _validate_series_by(self.series_by, self.series)
        _validate_series_fields(self.y_axis, self.series)
        return self


class PieChart(BaseModel):
    type: Literal["pie"] = "pie"
    title: str
    label_field: str
    value_field: str
    legend: bool = True
    tooltip: bool = True
    theme: str = "default"


class GaugeChart(BaseModel):
    type: Literal["gauge"] = "gauge"
    title: str
    value_field: str
    min: float = 0
    max: float = 100
    theme: str = "default"


Chart = Annotated[
    LineChart | BarChart | ScatterChart | PieChart | GaugeChart,
    Field(discriminator="type"),
]


class Query(BaseModel):
    sql: str
    variables: dict[str, str] = Field(default_factory=dict)
    limit: int = 1000
    timezone: str = "UTC"


_RESERVED_VARIABLE_NAMES = {"__timeFrom", "__timeTo"}
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Variable(BaseModel):
    name: str
    label: str
    table: str
    value_column: str
    predicate_column: str | None = None
    predicate_variable: str | None = None

    @field_validator("name")
    @classmethod
    def _valid_token(cls, value: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("Variable name must be a valid identifier")
        if value in _RESERVED_VARIABLE_NAMES:
            raise ValueError("Variable name is reserved")
        return value

    @field_validator("table", "value_column", "predicate_column")
    @classmethod
    def _valid_identifier(cls, value: str | None) -> str | None:
        if value is not None and not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("Must be a valid identifier")
        return value

    @model_validator(mode="after")
    def _predicate_requires_pair(self) -> "Variable":
        if (self.predicate_column is None) != (self.predicate_variable is None):
            raise ValueError("predicate_column and predicate_variable must be set together")
        return self


def build_variable_source_sql(
    table: str,
    value_column: str,
    predicate_column: str | None,
    predicate_variable: str | None,
) -> str:
    sql = f'SELECT DISTINCT "{value_column}" FROM "{table}"'
    if predicate_column and predicate_variable:
        sql += f' WHERE "{predicate_column}" = ${predicate_variable}'
    return sql


def validate_variables(variables: list[Variable]) -> None:
    seen: set[str] = set()
    for variable in variables:
        if variable.name in seen:
            raise ValueError(f"Duplicate variable name '{variable.name}'")
        if variable.predicate_variable and variable.predicate_variable not in seen:
            raise ValueError(
                f"Variable '{variable.name}' references undefined or later-defined "
                f"variable '{variable.predicate_variable}'"
            )
        seen.add(variable.name)


class PanelPosition(BaseModel):
    x: int
    y: int
    width: int
    height: int


class PanelInput(BaseModel):
    title: str
    chart: Chart
    query: Query
    time_range: str = "1h"
    refresh_interval: int = 0
    position: PanelPosition


class Panel(PanelInput):
    id: UUID = Field(default_factory=uuid4)


def _panels_overlap(a: PanelPosition, b: PanelPosition) -> bool:
    return (
        a.x < b.x + b.width
        and a.x + a.width > b.x
        and a.y < b.y + b.height
        and a.y + a.height > b.y
    )


def validate_panel_positions(panels: list[Panel]) -> None:
    for index, panel in enumerate(panels):
        for other in panels[index + 1 :]:
            if _panels_overlap(panel.position, other.position):
                raise ValueError(
                    f"Panel '{panel.title}' overlaps with panel '{other.title}'"
                )


class DashboardInput(BaseModel):
    project_id: UUID
    name: str
    description: str = ""
    variables: list[Variable] = Field(default_factory=list)
    panels: list[Panel] = Field(default_factory=list)
    layout: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_panels(self) -> "DashboardInput":
        validate_panel_positions(self.panels)
        validate_variables(self.variables)
        return self


class Dashboard(DashboardInput):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class PanelLayoutUpdate(BaseModel):
    id: UUID
    position: PanelPosition


class DashboardLayoutInput(BaseModel):
    panels: list[PanelLayoutUpdate] = Field(default_factory=list)
    layout: dict[str, Any] = Field(default_factory=dict)


class PanelQueryOverrides(BaseModel):
    time_range: str | None = None
    variable_values: dict[str, str] = Field(default_factory=dict)


class DashboardQueryPreview(BaseModel):
    sql: str
    limit: int = 100
    time_range: str = "1h"
    variable_values: dict[str, str] = Field(default_factory=dict)


class VariableOptionsRequest(BaseModel):
    table: str
    value_column: str
    predicate_column: str | None = None
    predicate_variable: str | None = None
    variable_values: dict[str, str] = Field(default_factory=dict)


class VariableOptionsResult(BaseModel):
    options: list[str]
