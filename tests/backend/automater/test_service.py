from pathlib import Path
from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.automater.docker import AutomaterDockerManager, automater_container_name
from app.automater.models import AutomaterInput, Condition, Rule
from app.automater.repository import AutomaterRepository
from app.automater.service import AutomaterService
from app.collector.docker import CollectorDockerManager
from app.collector.models import Collector
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
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
def collector_service(tmp_path: Path, collector_repository: CollectorRepository) -> CollectorService:
    return CollectorService(
        repository=collector_repository,
        registry=build_default_registry(),
        docker_manager=CollectorDockerManager(
            client=FakeDockerClient(),  # type: ignore[arg-type]
            runtime_dir=tmp_path / "collector-runtime",
            host_runtime_dir=Path("/host/collector-runtime"),
        ),
    )


@pytest.fixture
def service(tmp_path: Path, collector_service: CollectorService) -> AutomaterService:
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
        collector_service=collector_service,
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

    with pytest.raises(InvalidOperationError, match="no input for table"):
        await service.create_rule(
            project_id=project_id,
            rule=_rule(table="hive_metrics"),
            automater_id=None,
            automater_name="New Automater",
            automater_description="",
            collector_id=collector.id,
        )


async def test_create_rule_derives_input_from_a_non_mqtt_collector_input(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # An Automater's input isn't scoped to plugin_type == "mqtt" -- any of a
    # Collector's input plugins (kafka, http, amqp, ...) can back a rule, as
    # long as its name_override matches the rule's table. See
    # iotops-workspace/ROADMAP.md's data-sources note.
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="Kafka Collector",
        inputs=[
            InputPlugin(
                plugin_type="kafka",
                name="hive_metrics-input",
                configuration={"name_override": "hive_metrics", "topics": ["hive.metrics"]},
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    assert automater.inputs[0].plugin_type == "kafka"
    assert automater.inputs[0].configuration["name_override"] == "hive_metrics"


async def test_create_rule_scopes_kafka_consumer_group_distinct_from_collector(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # Kafka consumer groups are competing-consumer, not broadcast -- if the
    # Automater's derived input reused the Collector's exact
    # consumer_group, the two would split messages between them instead of
    # each getting a full copy. See _automater_scoped_configuration's own
    # comment and iotops-workspace/ROADMAP.md's data-sources note.
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="Kafka Collector",
        inputs=[
            InputPlugin(
                plugin_type="kafka",
                name="hive_metrics-input",
                configuration={
                    "name_override": "hive_metrics",
                    "topics": ["hive.metrics"],
                    "consumer_group": "telegraf_metrics_consumers",
                },
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    automater_group = automater.inputs[0].configuration["consumer_group"]
    assert automater_group != "telegraf_metrics_consumers"
    assert automater_group.startswith("telegraf_metrics_consumers-automater-")


async def test_create_rule_scopes_amqp_queue_distinct_from_collector(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # Same reasoning as the Kafka consumer_group case above -- an AMQP
    # queue is a competing-consumer target too.
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="AMQP Collector",
        inputs=[
            InputPlugin(
                plugin_type="amqp",
                name="hive_metrics-input",
                configuration={
                    "name_override": "hive_metrics",
                    "exchange": "telegraf",
                    "queue": "telegraf",
                },
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    automater_queue = automater.inputs[0].configuration["queue"]
    assert automater_queue != "telegraf"
    assert automater_queue.startswith("telegraf-automater-")
    # The exchange/binding stays identical -- only the queue differs, so
    # the Automater's queue still receives every message the Collector's
    # queue does (both bound to the same exchange).
    assert automater.inputs[0].configuration["exchange"] == "telegraf"


async def test_create_rule_forwards_http_collector_input_to_new_automater(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # A webhook push has no broker to fan out to two independent listeners
    # -- the Collector must forward a copy to the Automater's own listener
    # via a new outputs.http block. See iotops-workspace/ROADMAP.md's
    # "Automater fan-out strategy" note.
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="HTTP Collector",
        inputs=[
            InputPlugin(
                plugin_type="http",
                name="hive_metrics-input",
                configuration={
                    "name_override": "hive_metrics",
                    "service_address": "tcp://:9090",
                    "paths": ["/webhook"],
                },
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    updated_collector = await collector_repository.get(collector.id)
    forwards = [o for o in updated_collector.outputs if o.plugin_type == "http_forward"]
    assert len(forwards) == 1
    assert forwards[0].automater_id == automater.id
    assert forwards[0].configuration["url"] == f"http://{automater_container_name(automater)}:9090/webhook"


async def test_renaming_automater_resyncs_stale_http_forward_url_on_next_deploy(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # The container hostname baked into the Collector's http_forward
    # output is derived from the Automater's name at creation time. update()
    # alone doesn't redeploy (see AutomaterService.update), so a rename
    # only actually changes the running container's name -- and therefore
    # invalidates that baked-in hostname -- on the *next* deploy. Confirms
    # _resync_http_forwarding patches it up rather than leaving a
    # forwarding output pointing at a container that no longer exists.
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="HTTP Collector",
        inputs=[
            InputPlugin(
                plugin_type="http",
                name="hive_metrics-input",
                configuration={
                    "name_override": "hive_metrics",
                    "service_address": "tcp://:9090",
                    "paths": ["/webhook"],
                },
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )
    stale_hostname = automater_container_name(automater)

    renamed = await service.update(
        automater.id,
        AutomaterInput(
            project_id=automater.project_id,
            name="Renamed Automater",
            description=automater.description,
            enabled=automater.enabled,
            inputs=automater.inputs,
            outputs=automater.outputs,
            rules=automater.rules,
        ),
    )
    # update() alone doesn't touch the Collector's forwarding output --
    # the stale hostname is still there until a redeploy happens.
    still_stale = await collector_repository.get(collector.id)
    [stale_forward] = [o for o in still_stale.outputs if o.plugin_type == "http_forward"]
    assert stale_hostname in stale_forward.configuration["url"]

    await service.deploy(renamed.id)

    resynced_collector = await collector_repository.get(collector.id)
    [forward] = [o for o in resynced_collector.outputs if o.plugin_type == "http_forward"]
    new_hostname = automater_container_name(renamed)
    assert new_hostname != stale_hostname
    assert forward.configuration["url"] == f"http://{new_hostname}:9090/webhook"


async def test_create_rule_scopes_http_listener_config_for_forwarding(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # Two live-verified fixes bundled into the same scoping step (see
    # _automater_scoped_configuration's own comment for the full story):
    # 1. read_timeout/write_timeout bumped well past the fixed 10s
    #    flush_interval -- Go's net/http.Server falls back to ReadTimeout
    #    as its idle keep-alive timeout when IdleTimeout isn't set, and
    #    http_listener_v2 exposes no separate idle-timeout option, so the
    #    stock 10s default raced the Collector's forwarding outputs.http
    #    on every single flush.
    # 2. data_format forced to "influx" -- Telegraf's output JSON
    #    serializer and input JSON parser are different, non-interoperable
    #    shapes; a "json"-configured listener silently received
    #    well-formed-but-empty metrics from a forwarded request, so no
    #    rule could ever match, with no error anywhere.
    # 3. JSON-parser-only fields (tag_keys/json_string_fields) dropped --
    #    Telegraf's strict config validation crash-loops the container if
    #    a field only parsers.json understands is still set once
    #    data_format no longer selects it.
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="HTTP Collector",
        inputs=[
            InputPlugin(
                plugin_type="http",
                name="hive_metrics-input",
                configuration={
                    "name_override": "hive_metrics",
                    "service_address": "tcp://:8080",
                    "read_timeout": "10s",
                    "write_timeout": "10s",
                    "data_format": "json",
                    "tag_keys": ["station_id", "city"],
                    "json_string_fields": ["notes"],
                },
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    scoped_configuration = automater.inputs[0].configuration
    assert scoped_configuration["read_timeout"] == "60s"
    assert scoped_configuration["write_timeout"] == "60s"
    assert scoped_configuration["data_format"] == "influx"
    assert "tag_keys" not in scoped_configuration
    assert "json_string_fields" not in scoped_configuration


async def test_create_rule_does_not_duplicate_http_forwarding_for_same_url(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="HTTP Collector",
        inputs=[
            InputPlugin(
                plugin_type="http",
                name="hive_metrics-input",
                configuration={"name_override": "hive_metrics"},
            ),
            InputPlugin(
                plugin_type="http",
                name="device_status-input",
                configuration={"name_override": "device_status"},
            ),
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(table="hive_metrics"),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )
    await service.create_rule(
        project_id=project_id,
        rule=_rule(name="device-alert", table="device_status"),
        automater_id=automater.id,
        automater_name=None,
        automater_description="",
        collector_id=collector.id,
    )

    updated_collector = await collector_repository.get(collector.id)
    forwards = [o for o in updated_collector.outputs if o.plugin_type == "http_forward"]
    # Both tables share the same default service_address/path (":8080" +
    # "/telegraf") in this fixture, so they resolve to the same forward
    # URL -- exactly one output, not two, since a second identical
    # outputs.http block would be redundant.
    assert len(forwards) == 1


async def test_delete_removes_http_forwarding_from_collector(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    project_id = uuid4()
    collector = Collector(
        project_id=project_id,
        name="HTTP Collector",
        inputs=[
            InputPlugin(
                plugin_type="http",
                name="hive_metrics-input",
                configuration={"name_override": "hive_metrics"},
            )
        ],
        outputs=[OutputPlugin(plugin_type="timescaledb", configuration={})],
    )
    collector = await collector_repository.create(collector)

    automater = await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )
    forwarding_before = await collector_repository.get(collector.id)
    assert any(o.plugin_type == "http_forward" for o in forwarding_before.outputs)

    await service.delete(automater.id)

    forwarding_after = await collector_repository.get(collector.id)
    assert not any(o.plugin_type == "http_forward" for o in forwarding_after.outputs)
    # The Collector's own unrelated output is untouched.
    assert any(o.plugin_type == "timescaledb" for o in forwarding_after.outputs)


async def test_create_rule_does_not_forward_mqtt_input(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # mqtt already gets a full independent copy via the broker's native
    # fan-out -- no forwarding output should ever be created for it.
    project_id = uuid4()
    collector = await _seed_collector(collector_repository, project_id, "hive_metrics")

    await service.create_rule(
        project_id=project_id,
        rule=_rule(),
        automater_id=None,
        automater_name="New Automater",
        automater_description="",
        collector_id=collector.id,
    )

    updated_collector = await collector_repository.get(collector.id)
    assert not any(o.plugin_type == "http_forward" for o in updated_collector.outputs)


async def test_create_rule_leaves_mqtt_configuration_untouched(
    service: AutomaterService, collector_repository: CollectorRepository
) -> None:
    # mqtt has neither consumer_group nor queue -- _automater_scoped_configuration
    # must be a no-op for it, not accidentally add either field.
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

    assert "consumer_group" not in automater.inputs[0].configuration
    assert "queue" not in automater.inputs[0].configuration


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
