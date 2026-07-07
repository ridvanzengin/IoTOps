from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.dashboard.models import (
    DashboardInput,
    DashboardLayoutInput,
    DashboardQueryPreview,
    LineChart,
    PanelInput,
    PanelLayoutUpdate,
    PanelPosition,
    PanelQueryOverrides,
    Query,
    Variable,
    VariableOptionsRequest,
)
from app.dashboard.repository import DashboardRepository
from app.dashboard.service import DashboardService
from app.shared.exceptions import EntityNotFoundError
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.telemetry.fakes import FakePool


def _service(query_results: dict | None = None) -> DashboardService:
    database = AsyncMongoMockClient()["iotops"]
    pool = FakePool(tables=["device_metrics"], query_results=query_results)
    telemetry_service = TelemetryService(repository=TelemetryRepository(pool))
    return DashboardService(
        repository=DashboardRepository(database), telemetry_service=telemetry_service
    )


def _panel_input(**overrides: object) -> PanelInput:
    defaults: dict[str, object] = {
        "title": "Temperature",
        "chart": LineChart(title="Temperature", x_axis="time", y_axis="temperature"),
        "query": Query(sql="SELECT * FROM device_metrics"),
        "position": PanelPosition(x=0, y=0, width=6, height=4),
    }
    defaults.update(overrides)
    return PanelInput(**defaults)


def _valid_input(**overrides: object) -> DashboardInput:
    defaults: dict[str, object] = {"project_id": uuid4(), "name": "Hive Overview"}
    defaults.update(overrides)
    return DashboardInput(**defaults)


async def test_create_persists_and_returns_dashboard() -> None:
    service = _service()

    dashboard = await service.create(_valid_input())

    fetched = await service.get(dashboard.id)
    assert fetched == dashboard


async def test_list_returns_all_dashboards() -> None:
    service = _service()
    await service.create(_valid_input(name="Hive Overview"))
    await service.create(_valid_input(name="Greenhouse Overview"))

    dashboards = await service.list()

    assert {d.name for d in dashboards} == {"Hive Overview", "Greenhouse Overview"}


async def test_update_replaces_editable_fields() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())

    updated = await service.update(dashboard.id, _valid_input(name="Renamed"))

    assert updated.name == "Renamed"
    assert updated.id == dashboard.id


async def test_update_missing_dashboard_raises() -> None:
    service = _service()

    with pytest.raises(EntityNotFoundError):
        await service.update(uuid4(), _valid_input())


async def test_add_panel_appends_panel() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())

    updated = await service.add_panel(dashboard.id, _panel_input())

    assert len(updated.panels) == 1
    assert updated.panels[0].title == "Temperature"


async def test_add_panel_rejects_overlap() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())
    await service.add_panel(dashboard.id, _panel_input())

    with pytest.raises(ValueError, match="overlaps"):
        await service.add_panel(
            dashboard.id, _panel_input(position=PanelPosition(x=0, y=0, width=6, height=4))
        )


async def test_update_panel_replaces_matching_panel() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())
    with_panel = await service.add_panel(dashboard.id, _panel_input())
    panel_id = with_panel.panels[0].id

    updated = await service.update_panel(
        dashboard.id, panel_id, _panel_input(title="Renamed Panel")
    )

    assert updated.panels[0].title == "Renamed Panel"
    assert updated.panels[0].id == panel_id


async def test_update_missing_panel_raises() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())

    with pytest.raises(EntityNotFoundError):
        await service.update_panel(dashboard.id, uuid4(), _panel_input())


async def test_remove_panel_deletes_it() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())
    with_panel = await service.add_panel(dashboard.id, _panel_input())
    panel_id = with_panel.panels[0].id

    updated = await service.remove_panel(dashboard.id, panel_id)

    assert updated.panels == []


async def test_remove_missing_panel_raises() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())

    with pytest.raises(EntityNotFoundError):
        await service.remove_panel(dashboard.id, uuid4())


async def test_save_layout_updates_positions() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())
    with_panel = await service.add_panel(dashboard.id, _panel_input())
    panel_id = with_panel.panels[0].id
    new_position = PanelPosition(x=6, y=0, width=6, height=4)

    updated = await service.save_layout(
        dashboard.id,
        DashboardLayoutInput(
            panels=[PanelLayoutUpdate(id=panel_id, position=new_position)],
            layout={"cols": 12},
        ),
    )

    assert updated.panels[0].position == new_position
    assert updated.layout == {"cols": 12}


async def test_run_panel_query_substitutes_variables_and_executes() -> None:
    service = _service(
        query_results={"SELECT * FROM device_metrics WHERE hive = 'A'": [{"temperature": 21.5}]}
    )
    dashboard = await service.create(_valid_input())
    with_panel = await service.add_panel(
        dashboard.id,
        _panel_input(
            query=Query(
                sql="SELECT * FROM device_metrics WHERE hive = $hive",
                variables={"hive": "'A'"},
            )
        ),
    )

    result = await service.run_panel_query(with_panel.panels[0])

    assert result.rows == [{"temperature": 21.5}]


async def test_run_panel_query_substitutes_dashboard_variables() -> None:
    service = _service(
        query_results={"SELECT * FROM device_metrics WHERE hive = 'A'": [{"temperature": 21.5}]}
    )
    dashboard = await service.create(_valid_input())
    with_panel = await service.add_panel(
        dashboard.id,
        _panel_input(query=Query(sql="SELECT * FROM device_metrics WHERE hive = $hive")),
    )

    result = await service.run_panel_query(
        with_panel.panels[0],
        dashboard_variables=[Variable(name="hive", label="Hive", table="device_metrics", value_column="hive")],
        variable_values={"hive": "A"},
    )

    assert result.rows == [{"temperature": 21.5}]


async def test_run_panel_query_by_id_resolves_panel_and_dashboard_variables() -> None:
    service = _service(
        query_results={"SELECT * FROM device_metrics WHERE hive = 'A'": [{"temperature": 21.5}]}
    )
    dashboard = await service.create(
        _valid_input(
            variables=[Variable(name="hive", label="Hive", table="device_metrics", value_column="hive")]
        )
    )
    with_panel = await service.add_panel(
        dashboard.id,
        _panel_input(query=Query(sql="SELECT * FROM device_metrics WHERE hive = $hive")),
    )
    panel_id = with_panel.panels[0].id

    result = await service.run_panel_query_by_id(
        dashboard.id, panel_id, PanelQueryOverrides(variable_values={"hive": "A"})
    )

    assert result.rows == [{"temperature": 21.5}]


async def test_run_panel_query_by_id_missing_panel_raises() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())

    with pytest.raises(EntityNotFoundError):
        await service.run_panel_query_by_id(dashboard.id, uuid4(), PanelQueryOverrides())


async def test_preview_query_runs_ad_hoc_sql_with_dashboard_variables() -> None:
    service = _service(
        query_results={"SELECT * FROM device_metrics WHERE hive = 'A'": [{"temperature": 21.5}]}
    )
    dashboard = await service.create(
        _valid_input(
            variables=[Variable(name="hive", label="Hive", table="device_metrics", value_column="hive")]
        )
    )

    result = await service.preview_query(
        dashboard.id,
        DashboardQueryPreview(
            sql="SELECT * FROM device_metrics WHERE hive = $hive",
            variable_values={"hive": "A"},
        ),
    )

    assert result.rows == [{"temperature": 21.5}]


async def test_resolve_variable_options_returns_first_column_values() -> None:
    service = _service(
        query_results={
            'SELECT DISTINCT "hive" FROM "device_metrics"': [{"hive": "A"}, {"hive": "B"}]
        }
    )
    dashboard = await service.create(_valid_input())

    result = await service.resolve_variable_options(
        dashboard.id,
        VariableOptionsRequest(table="device_metrics", value_column="hive"),
    )

    assert result.options == ["A", "B"]


async def test_resolve_variable_options_substitutes_chained_variable() -> None:
    service = _service(
        query_results={
            'SELECT DISTINCT "hive" FROM "device_metrics" WHERE "project" = \'X\'': [{"hive": "A"}]
        }
    )
    dashboard = await service.create(
        _valid_input(
            variables=[Variable(name="project", label="Project", table="projects", value_column="project")]
        )
    )

    result = await service.resolve_variable_options(
        dashboard.id,
        VariableOptionsRequest(
            table="device_metrics",
            value_column="hive",
            predicate_column="project",
            predicate_variable="project",
            variable_values={"project": "X"},
        ),
    )

    assert result.options == ["A"]


async def test_resolve_variable_options_empty_result() -> None:
    service = _service()
    dashboard = await service.create(_valid_input())

    result = await service.resolve_variable_options(
        dashboard.id,
        VariableOptionsRequest(table="device_metrics", value_column="hive"),
    )

    assert result.options == []
