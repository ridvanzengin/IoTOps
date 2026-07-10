from pathlib import Path
from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.automater.docker import AutomaterDockerManager
from app.automater.models import Condition, Rule
from app.automater.repository import AutomaterRepository
from app.automater.service import AutomaterService
from app.collector.models import Collector
from app.collector.repository import CollectorRepository
from app.plugin.registry import build_default_registry
from app.shared.enums import CollectorStatus
from app.shared.exceptions import InvalidOperationError
from app.shared.models import InputPlugin, OutputPlugin
from tests.backend.collector.test_docker import FakeDockerClient


@pytest.fixture
def collector_repository() -> CollectorRepository:
    database = AsyncMongoMockClient()["iotops"]
    return CollectorRepository(database)


@pytest.fixture
def service(tmp_path: Path, collector_repository: CollectorRepository) -> AutomaterService:
    database = AsyncMongoMockClient()["iotops"]
    docker_manager = AutomaterDockerManager(
        client=FakeDockerClient(),  # type: ignore[arg-type]
        runtime_dir=tmp_path / "runtime",
        host_runtime_dir=Path("/host/runtime"),
    )
    return AutomaterService(
        repository=AutomaterRepository(database),
        registry=build_default_registry(),
        docker_manager=docker_manager,
        collector_repository=collector_repository,
    )


def _condition(**overrides: object) -> Condition:
    defaults: dict[str, object] = {"column": "temperature", "operator": ">", "value": 30.0}
    defaults.update(overrides)
    return Condition(**defaults)


def _rule(**overrides: object) -> Rule:
    defaults: dict[str, object] = {
        "name": "swarm-alert",
        "table": "hive_metrics",
        "conditions": [_condition()],
    }
    defaults.update(overrides)
    return Rule(**defaults)


async def _seed_collector(
    collector_repository: CollectorRepository, project_id: object, *tables: str
) -> Collector:
    """A Collector with one mqtt input per table name given, mirroring how
    a real multi-input Collector (one input per topic/table) looks."""
    collector = Collector(
        project_id=project_id,
        name="Hive Collector",
        inputs=[
            InputPlugin(
                plugin_type="mqtt",
                name=f"{table}-input",
                configuration={"name_override": table, "topics": [f"beekeeping/{table}"]},
            )
            for table in tables
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    return await collector_repository.create(collector)


async def test_create_rule_creates_new_automater_deployed_and_running(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    assert automater.status == CollectorStatus.RUNNING
    assert len(automater.inputs) == 1
    assert automater.inputs[0].configuration["name_override"] == "hive_metrics"
    assert [r.name for r in automater.rules] == ["swarm-alert"]


async def test_create_rule_new_automater_requires_automater_name(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")

    with pytest.raises(InvalidOperationError, match="automater_name is required"):
        await service.create_rule(
            project_id=project_id,
            rule=_rule(),
            automater_id=None,
            automater_name=None,
            automater_description="",
            collector_id=collector.id,
        )


async def test_create_rule_new_automater_requires_collector_id(service: AutomaterService) -> None:
    with pytest.raises(InvalidOperationError, match="collector_id is required"):
        await service.create_rule(
            project_id=uuid4(),
            rule=_rule(),
            automater_id=None,
            automater_name="New Automater",
            automater_description="",
            collector_id=None,
        )


async def test_create_rule_raises_when_collector_has_no_matching_table(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "device_status")

    with pytest.raises(InvalidOperationError, match="no mqtt input for table"):
        await service.create_rule(
            project_id=project_id,
            rule=_rule(table="hive_metrics"),
            automater_id=None,
            automater_name="New Automater",
            automater_description="",
            collector_id=collector.id,
        )


async def test_create_rule_existing_automater_reuses_matching_input_without_collector_id(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(name="first-rule"),
        automater_id=None,
        automater_name="Shared Automater",
        automater_description="",
        collector_id=collector.id,
    )

    updated = await service.create_rule(
        project_id=project_id,
        rule=_rule(name="second-rule"),
        automater_id=automater.id,
        automater_name=None,
        automater_description="",
        collector_id=None,  # not needed -- the Automater already covers hive_metrics
    )

    assert len(updated.inputs) == 1
    assert {r.name for r in updated.rules} == {"first-rule", "second-rule"}


async def test_create_rule_existing_automater_adds_new_input_for_uncovered_table(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # Regression test: an Automater used to have exactly one fixed input,
    # so a second rule on a *different* table would silently deploy dead
    # (the Go plugin only evaluates a rule against metrics whose name
    # equals its table -- see rule.go's evaluateConditions). An Automater
    # can now watch more than one table; create_rule must add the second
    # input, not just append the rule.
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics", "device_status")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(table="hive_metrics", name="hive-rule"),
        automater_id=None,
        automater_name="Shared Automater",
        automater_description="",
        collector_id=collector.id,
    )

    updated = await service.create_rule(
        project_id=project_id,
        rule=_rule(
            table="device_status",
            name="status-rule",
            conditions=[_condition(column="connection", operator="==", value="offline")],
        ),
        automater_id=automater.id,
        automater_name=None,
        automater_description="",
        collector_id=collector.id,
    )

    table_names = {i.configuration["name_override"] for i in updated.inputs}
    assert table_names == {"hive_metrics", "device_status"}
    assert {r.name for r in updated.rules} == {"hive-rule", "status-rule"}


async def test_create_rule_existing_automater_requires_collector_id_for_uncovered_table(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics", "device_status")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(table="hive_metrics"),
        automater_id=None,
        automater_name="Shared Automater",
        automater_description="",
        collector_id=collector.id,
    )

    with pytest.raises(InvalidOperationError, match="collector_id is required to add one"):
        await service.create_rule(
            project_id=project_id,
            rule=_rule(table="device_status", name="status-rule"),
            automater_id=automater.id,
            automater_name=None,
            automater_description="",
            collector_id=None,
        )


async def test_create_rule_rejects_automater_from_a_different_project(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="Shared Automater",
        automater_description="",
        collector_id=collector.id,
    )

    with pytest.raises(InvalidOperationError, match="does not belong to project"):
        await service.create_rule(
            project_id=uuid4(),
            rule=_rule(name="other-project-rule"),
            automater_id=automater.id,
            automater_name=None,
            automater_description="",
            collector_id=None,
        )


async def test_set_rule_enabled_toggles_only_that_field(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="Automater",
        automater_description="",
        collector_id=collector.id,
    )
    rule_id = automater.rules[0].id

    updated = await service.set_rule_enabled(automater.id, rule_id, False)

    assert updated.rules[0].enabled is False
    assert updated.rules[0].table == "hive_metrics"
    assert updated.rules[0].conditions == automater.rules[0].conditions
    # No enabled rules left -> Automater stops rather than redeploying.
    assert updated.status == CollectorStatus.STOPPED


async def test_delete_rule_removes_rule(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(name="first-rule"),
        automater_id=None,
        automater_name="Automater",
        automater_description="",
        collector_id=collector.id,
    )
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(name="second-rule"),
        automater_id=automater.id,
        automater_name=None,
        automater_description="",
        collector_id=None,
    )
    first_rule_id = automater.rules[0].id

    updated = await service.delete_rule(automater.id, first_rule_id)

    assert [r.name for r in updated.rules] == ["second-rule"]


async def test_delete_rule_refuses_to_delete_last_rule(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")
    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="Automater",
        automater_description="",
        collector_id=collector.id,
    )

    with pytest.raises(InvalidOperationError, match="last rule"):
        await service.delete_rule(automater.id, automater.rules[0].id)
