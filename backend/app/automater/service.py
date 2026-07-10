from uuid import UUID

from app.automater.docker import AutomaterDockerManager
from app.automater.models import Automater, AutomaterInput, Rule
from app.automater.repository import AutomaterRepository
from app.collector.generator import generate_toml
from app.collector.models import Collector
from app.collector.repository import CollectorRepository
from app.plugin.registry import PluginRegistry
from app.shared.exceptions import EntityNotFoundError, InvalidOperationError
from app.shared.models import InputPlugin, OutputPlugin, ProcessorPlugin

_RULE_PLUGIN_TYPE = "rule"
_CELERY_TASK_NAME = "automater.tasks.log_rule_match"


class AutomaterService:
    def __init__(
        self,
        repository: AutomaterRepository,
        registry: PluginRegistry,
        docker_manager: AutomaterDockerManager,
        collector_repository: CollectorRepository,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._docker_manager = docker_manager
        self._collector_repository = collector_repository

    async def create(self, payload: AutomaterInput) -> Automater:
        automater = Automater(**payload.model_dump())
        self._validate_plugin_configurations(automater)
        return await self._repository.create(automater)

    async def create_rule(
        self,
        project_id: UUID,
        rule: Rule,
        automater_id: UUID | None,
        automater_name: str | None,
        automater_description: str,
        collector_id: UUID | None,
    ) -> Automater:
        if automater_id is not None:
            automater = await self._repository.get(automater_id)
            if automater.project_id != project_id:
                raise InvalidOperationError(
                    f"Automater {automater_id} does not belong to project {project_id}"
                )
            # An Automater can watch more than one table -- mirrors how a
            # Collector can already have more than one mqtt input. If this
            # Automater has no input for the new rule's table yet, add one
            # (derived from the given Collector) rather than deploying a
            # rule that can never match anything (the Go plugin only
            # evaluates a rule against metrics whose name equals its
            # table). Already-covered tables need no collector_id at all --
            # existing behavior, unchanged.
            if not self._has_input_for_table(automater, rule.table):
                if collector_id is None:
                    raise InvalidOperationError(
                        f"Automater {automater_id} has no input for table {rule.table!r} yet; "
                        "collector_id is required to add one"
                    )
                collector = await self._collector_repository.get(collector_id)
                mqtt_input = self._find_mqtt_input(collector, rule.table)
                automater.inputs.append(
                    InputPlugin(
                        plugin_type=mqtt_input.plugin_type,
                        name=mqtt_input.name,
                        enabled=True,
                        configuration=mqtt_input.configuration,
                    )
                )
            automater.rules.append(rule)
        else:
            if not automater_name:
                raise InvalidOperationError(
                    "automater_name is required when creating a new Automater"
                )
            if collector_id is None:
                raise InvalidOperationError(
                    "collector_id is required when creating a new Automater"
                )
            collector = await self._collector_repository.get(collector_id)
            mqtt_input = self._find_mqtt_input(collector, rule.table)

            automater = Automater(
                project_id=project_id,
                name=automater_name,
                description=automater_description,
                inputs=[
                    InputPlugin(
                        plugin_type=mqtt_input.plugin_type,
                        name=mqtt_input.name,
                        enabled=True,
                        configuration=mqtt_input.configuration,
                    )
                ],
                rules=[rule],
                outputs=[
                    OutputPlugin(
                        plugin_type="celery",
                        enabled=True,
                        configuration={"task_name": _CELERY_TASK_NAME},
                    )
                ],
            )
            self._validate_plugin_configurations(automater)
            automater = await self._repository.create(automater)

        return await self._redeploy_or_stop(automater)

    def _has_input_for_table(self, automater: Automater, table: str) -> bool:
        return any(
            i.plugin_type == "mqtt" and i.configuration.get("name_override") == table
            for i in automater.inputs
        )

    def _find_mqtt_input(self, collector: Collector, table: str) -> InputPlugin:
        mqtt_input = next(
            (
                i
                for i in collector.inputs
                if i.plugin_type == "mqtt" and i.configuration.get("name_override") == table
            ),
            None,
        )
        if mqtt_input is None:
            raise InvalidOperationError(f"Collector {collector.id} has no mqtt input for table {table!r}")
        return mqtt_input

    async def set_rule_enabled(self, automater_id: UUID, rule_id: UUID, enabled: bool) -> Automater:
        # Deliberately narrower than a full-rule replace: the only rule edit
        # exposed today is activate/deactivate, and a general-purpose "PUT
        # any field" endpoint would let `table` change without any of the
        # create_rule input-matching/validation logic running -- silently
        # deploying a rule that can never fire (see ROADMAP.md 2026-07-10,
        # "Multi-table Automaters"). Full rule-field editing, if it ships
        # later, needs that same validation built in from the start rather
        # than resurrecting this endpoint as-is.
        automater = await self._repository.get(automater_id)
        index = self._rule_index(automater, rule_id)
        automater.rules[index] = automater.rules[index].model_copy(update={"enabled": enabled})
        return await self._redeploy_or_stop(automater)

    async def delete_rule(self, automater_id: UUID, rule_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        index = self._rule_index(automater, rule_id)
        if len(automater.rules) == 1:
            raise InvalidOperationError(
                "Cannot delete an Automater's last rule -- delete the Automater itself instead"
            )
        del automater.rules[index]
        return await self._redeploy_or_stop(automater)

    def _rule_index(self, automater: Automater, rule_id: UUID) -> int:
        for i, rule in enumerate(automater.rules):
            if rule.id == rule_id:
                return i
        raise EntityNotFoundError("Rule", rule_id)

    async def _redeploy_or_stop(self, automater: Automater) -> Automater:
        automater = await self._repository.update(automater)
        if any(rule.enabled for rule in automater.rules):
            processors = [self._synthesize_rule_processor(automater.rules)]
            toml_config = generate_toml(
                automater.inputs, processors, automater.outputs, self._registry
            )
            deployed = self._docker_manager.deploy(automater, toml_config)
            return await self._repository.update(deployed)
        if automater.docker is not None:
            stopped = self._docker_manager.stop(automater)
            return await self._repository.update(stopped)
        return automater

    async def get(self, automater_id: UUID) -> Automater:
        return await self._repository.get(automater_id)

    def _synthesize_rule_processor(self, rules: list[Rule]) -> ProcessorPlugin:
        # The rule plugin instance is never persisted on Automater itself
        # (there's no `processors` field, only `rules`) -- it's built fresh
        # at deploy time from the rules the user actually authored. See
        # iotops-workspace/ROADMAP.md Phase B step 1.
        #
        # Defined before `list` below: a `list[Rule]` annotation on a method
        # that comes *after* a method literally named `list` in this same
        # class body would resolve `list` against the class namespace (where
        # it's already been rebound to that method), not the builtin.
        configuration = self._registry.validate_configuration(
            _RULE_PLUGIN_TYPE,
            {"rules": [rule.model_dump(mode="json") for rule in rules]},
        )
        return ProcessorPlugin(plugin_type=_RULE_PLUGIN_TYPE, configuration=configuration)

    async def list(self) -> list[Automater]:
        return await self._repository.list()

    async def update(self, automater_id: UUID, payload: AutomaterInput) -> Automater:
        existing = await self._repository.get(automater_id)
        updated = existing.model_copy(
            update={
                "project_id": payload.project_id,
                "name": payload.name,
                "description": payload.description,
                "enabled": payload.enabled,
                "inputs": payload.inputs,
                "rules": payload.rules,
                "outputs": payload.outputs,
            }
        )
        self._validate_plugin_configurations(updated)
        return await self._repository.update(updated)

    async def delete(self, automater_id: UUID) -> None:
        automater = await self._repository.get(automater_id)
        self._docker_manager.remove(automater)
        await self._repository.delete(automater_id)

    async def deploy(self, automater_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        processors = [self._synthesize_rule_processor(automater.rules)]
        toml_config = generate_toml(
            automater.inputs, processors, automater.outputs, self._registry
        )
        deployed = self._docker_manager.deploy(automater, toml_config)
        return await self._repository.update(deployed)

    async def stop(self, automater_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        stopped = self._docker_manager.stop(automater)
        return await self._repository.update(stopped)

    async def refresh_status(self, automater_id: UUID) -> Automater:
        automater = await self._repository.get(automater_id)
        refreshed = self._docker_manager.refresh_status(automater)
        return await self._repository.update(refreshed)

    def _validate_plugin_configurations(self, automater: Automater) -> None:
        for instance in (*automater.inputs, *automater.outputs):
            instance.configuration = self._registry.validate_configuration(
                instance.plugin_type, instance.configuration
            )
