from pathlib import Path
from uuid import uuid4

import pytest

from app.automater.models import Condition, ConditionOperator, Rule
from app.collector.models import CollectorInput
from app.dashboard.models import DashboardInput
from app.project.models import ProjectInput
from app.project.service import ProjectService
from app.query_rule.models import QueryRuleInput, QueryRuleSchedule
from app.shared.exceptions import EntityNotFoundError
from app.shared.models import InputPlugin, OutputPlugin
from tests.backend.project.fakes import build_project_service


@pytest.fixture
def service(tmp_path: Path) -> ProjectService:
    return build_project_service(tmp_path)


def _valid_input(**overrides: object) -> ProjectInput:
    defaults: dict[str, object] = {"name": "Beekeeping"}
    defaults.update(overrides)
    return ProjectInput(**defaults)


async def test_create_persists_and_returns_project(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    fetched = await service.get(project.id)
    assert fetched == project


async def test_list_returns_all_projects(service: ProjectService) -> None:
    await service.create(_valid_input(name="Beekeeping"))
    await service.create(_valid_input(name="Greenhouse"))

    projects = await service.list()

    assert {p.name for p in projects} == {"Beekeeping", "Greenhouse"}


async def test_update_replaces_editable_fields(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    updated = await service.update(project.id, _valid_input(name="Renamed"))

    assert updated.name == "Renamed"
    assert updated.id == project.id


async def test_update_missing_project_raises(service: ProjectService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.update(uuid4(), _valid_input())


async def test_update_sets_default_dashboard_id(service: ProjectService) -> None:
    project = await service.create(_valid_input())
    dashboard_id = uuid4()

    updated = await service.update(project.id, _valid_input(default_dashboard_id=dashboard_id))

    assert updated.default_dashboard_id == dashboard_id


async def test_update_clears_default_dashboard_id(service: ProjectService) -> None:
    project = await service.create(_valid_input(default_dashboard_id=uuid4()))

    updated = await service.update(project.id, _valid_input(default_dashboard_id=None))

    assert updated.default_dashboard_id is None


async def test_delete_removes_project(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    await service.delete(project.id)

    with pytest.raises(EntityNotFoundError):
        await service.get(project.id)


async def test_delete_cascades_to_everything_the_project_owns(service: ProjectService) -> None:
    project = await service.create(_valid_input())

    collector = await service._collector_service.create(
        CollectorInput(
            project_id=project.id,
            name="Hive Collector",
            inputs=[
                InputPlugin(
                    plugin_type="mqtt",
                    name="hive-mqtt",
                    configuration={"topics": ["hive/+"], "name_override": "hive_metrics"},
                )
            ],
            outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
        )
    )
    automater = await service._automater_service.create_rule(
        project_id=project.id,
        rule=Rule(
            name="swarm-alert",
            table="hive_metrics",
            conditions=[Condition(column="temperature", operator=ConditionOperator.GT, value=30.0)],
        ),
        automater_id=None,
        automater_name="Apiary Automater",
        automater_description="",
        collector_id=collector.id,
    )
    dashboard = await service._dashboard_service.create(
        DashboardInput(project_id=project.id, name="Apiary Overview")
    )
    query_rule = await service._query_rule_service.create(
        QueryRuleInput(
            project_id=project.id,
            name="swarm-risk",
            sql="SELECT hive_id FROM hive_metrics",
            schedule=QueryRuleSchedule(interval="5m"),
        )
    )

    await service.delete(project.id)

    with pytest.raises(EntityNotFoundError):
        await service._collector_service.get(collector.id)
    with pytest.raises(EntityNotFoundError):
        await service._automater_service.get(automater.id)
    with pytest.raises(EntityNotFoundError):
        await service._dashboard_service.get(dashboard.id)
    with pytest.raises(EntityNotFoundError):
        await service._query_rule_service.get(query_rule.id)
    with pytest.raises(EntityNotFoundError):
        await service.get(project.id)
