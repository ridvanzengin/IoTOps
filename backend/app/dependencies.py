from pathlib import Path

import docker

from app.collector.docker import CollectorDockerManager
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
from app.config import settings
from app.database import get_database
from app.plugin.registry import PluginRegistry, build_default_registry

_registry: PluginRegistry | None = None
_docker_manager: CollectorDockerManager | None = None


def get_plugin_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_registry()
    return _registry


def get_docker_manager() -> CollectorDockerManager:
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = CollectorDockerManager(
            client=docker.from_env(),
            runtime_dir=Path(settings.runtime_dir),
            host_runtime_dir=Path(settings.host_runtime_dir or settings.runtime_dir),
            network=settings.docker_network,
            telegraf_image=settings.telegraf_image,
        )
    return _docker_manager


def get_collector_service() -> CollectorService:
    return CollectorService(
        repository=CollectorRepository(get_database()),
        registry=get_plugin_registry(),
        docker_manager=get_docker_manager(),
    )
