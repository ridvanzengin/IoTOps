from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LineChart(BaseModel):
    type: Literal["line"] = "line"
    title: str
    x_axis: str
    y_axis: str
    series: list[str] = Field(default_factory=list)
    legend: bool = True
    tooltip: bool = True
    zoom: bool = False
    theme: str = "default"


class BarChart(BaseModel):
    type: Literal["bar"] = "bar"
    title: str
    x_axis: str
    y_axis: str
    series: list[str] = Field(default_factory=list)
    legend: bool = True
    tooltip: bool = True
    theme: str = "default"


class ScatterChart(BaseModel):
    type: Literal["scatter"] = "scatter"
    title: str
    x_axis: str
    y_axis: str
    series: list[str] = Field(default_factory=list)
    legend: bool = True
    tooltip: bool = True
    theme: str = "default"


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


class Variable(BaseModel):
    name: str
    label: str
    default: str | None = None
    type: str = "text"
    options: list[str] = Field(default_factory=list)


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
