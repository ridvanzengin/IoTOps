from uuid import UUID

from app.automater.docker import AutomaterDockerManager
from app.automater.models import Automater, AutomaterInput, Rule
from app.automater.repository import AutomaterRepository
from app.collector.generator import generate_toml
from app.plugin.registry import PluginRegistry
from app.shared.models import ProcessorPlugin

_RULE_PLUGIN_TYPE = "rule"


class AutomaterService:
    def __init__(
        self,
        repository: AutomaterRepository,
        registry: PluginRegistry,
        docker_manager: AutomaterDockerManager,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._docker_manager = docker_manager

    async def create(self, payload: AutomaterInput) -> Automater:
        automater = Automater(**payload.model_dump())
        self._validate_plugin_configurations(automater)
        return await self._repository.create(automater)

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
