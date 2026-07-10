from pathlib import Path

import docker
import httpx

from app.ai.service import AiService
from app.automater.docker import AutomaterDockerManager
from app.automater.repository import AutomaterRepository
from app.automater.service import AutomaterService
from app.collector.docker import CollectorDockerManager
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
from app.config import settings
from app.dashboard.repository import DashboardRepository
from app.dashboard.service import DashboardService
from app.database import get_database, get_timescale_pool
from app.plugin.registry import PluginRegistry, build_default_registry
from app.project.repository import ProjectRepository
from app.project.service import ProjectService
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService

_registry: PluginRegistry | None = None
_docker_manager: CollectorDockerManager | None = None
_automater_docker_manager: AutomaterDockerManager | None = None
_http_client: httpx.AsyncClient | None = None


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


def get_automater_docker_manager() -> AutomaterDockerManager:
    global _automater_docker_manager
    if _automater_docker_manager is None:
        _automater_docker_manager = AutomaterDockerManager(
            client=docker.from_env(),
            runtime_dir=Path(settings.runtime_dir),
            host_runtime_dir=Path(settings.host_runtime_dir or settings.runtime_dir),
            network=settings.docker_network,
            telegraf_image=settings.automater_telegraf_image,
        )
    return _automater_docker_manager


def get_automater_service() -> AutomaterService:
    return AutomaterService(
        repository=AutomaterRepository(get_database()),
        registry=get_plugin_registry(),
        docker_manager=get_automater_docker_manager(),
        collector_repository=CollectorRepository(get_database()),
    )


async def get_telemetry_service() -> TelemetryService:
    pool = await get_timescale_pool()
    return TelemetryService(repository=TelemetryRepository(pool))


def get_project_service() -> ProjectService:
    return ProjectService(repository=ProjectRepository(get_database()))


async def get_dashboard_service() -> DashboardService:
    return DashboardService(
        repository=DashboardRepository(get_database()),
        telemetry_service=await get_telemetry_service(),
    )


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=60.0)
    return _http_client


async def get_ai_service() -> AiService:
    return AiService(
        telemetry_service=await get_telemetry_service(),
        http_client=get_http_client(),
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )
