from uuid import UUID

from app.collector.docker import CollectorDockerManager
from app.collector.generator import generate_toml
from app.collector.models import Collector, CollectorInput
from app.collector.repository import CollectorRepository
from app.plugin.registry import PluginRegistry


class CollectorService:
    def __init__(
        self,
        repository: CollectorRepository,
        registry: PluginRegistry,
        docker_manager: CollectorDockerManager,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._docker_manager = docker_manager

    async def create(self, payload: CollectorInput) -> Collector:
        collector = Collector(**payload.model_dump())
        self._validate_plugin_configurations(collector)
        return await self._repository.create(collector)

    async def get(self, collector_id: UUID) -> Collector:
        return await self._repository.get(collector_id)

    async def list(self) -> list[Collector]:
        return await self._repository.list()

    async def update(self, collector_id: UUID, payload: CollectorInput) -> Collector:
        existing = await self._repository.get(collector_id)
        updated = existing.model_copy(
            update={
                "project_id": payload.project_id,
                "name": payload.name,
                "description": payload.description,
                "enabled": payload.enabled,
                "inputs": payload.inputs,
                "processors": payload.processors,
                "outputs": payload.outputs,
            }
        )
        self._validate_plugin_configurations(updated)
        return await self._repository.update(updated)

    async def delete(self, collector_id: UUID) -> None:
        collector = await self._repository.get(collector_id)
        self._docker_manager.remove(collector)
        await self._repository.delete(collector_id)

    async def deploy(self, collector_id: UUID) -> Collector:
        collector = await self._repository.get(collector_id)
        toml_config = generate_toml(
            collector.inputs, collector.processors, collector.outputs, self._registry
        )
        deployed = self._docker_manager.deploy(collector, toml_config)
        return await self._repository.update(deployed)

    async def redeploy_if_running(self, collector: Collector) -> Collector:
        """Persist a config change made on an already-loaded Collector, and
        redeploy it only if it's currently running -- otherwise there's
        nothing to refresh, the next real deploy picks up the change
        naturally. Used by AutomaterService when it adds/removes the
        forwarding output an http-sourced Automater depends on, so the
        Collector doesn't need its own "redeploy because a dependent
        changed" concept beyond this one narrow case. See
        iotops-workspace/ROADMAP.md's "Automater fan-out strategy" note.
        """
        if collector.docker is None:
            return await self._repository.update(collector)
        toml_config = generate_toml(
            collector.inputs, collector.processors, collector.outputs, self._registry
        )
        deployed = self._docker_manager.deploy(collector, toml_config)
        return await self._repository.update(deployed)

    async def stop(self, collector_id: UUID) -> Collector:
        collector = await self._repository.get(collector_id)
        stopped = self._docker_manager.stop(collector)
        return await self._repository.update(stopped)

    async def refresh_status(self, collector_id: UUID) -> Collector:
        collector = await self._repository.get(collector_id)
        refreshed = self._docker_manager.refresh_status(collector)
        return await self._repository.update(refreshed)

    def _validate_plugin_configurations(self, collector: Collector) -> None:
        for instance in (*collector.inputs, *collector.processors, *collector.outputs):
            instance.configuration = self._registry.validate_configuration(
                instance.plugin_type, instance.configuration
            )
