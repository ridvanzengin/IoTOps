from pathlib import Path

from mongomock_motor import AsyncMongoMockClient

from app.automater.docker import AutomaterDockerManager
from app.automater.repository import AutomaterRepository
from app.automater.service import AutomaterService
from app.collector.docker import CollectorDockerManager
from app.collector.repository import CollectorRepository
from app.collector.service import CollectorService
from app.dashboard.repository import DashboardRepository
from app.dashboard.service import DashboardService
from app.event.repository import EventRepository
from app.plugin.registry import build_default_registry
from app.project.repository import ProjectRepository
from app.project.service import ProjectService
from app.query_rule.repository import QueryRuleRepository
from app.query_rule.service import QueryRuleService
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.collector.test_docker import FakeDockerClient
from tests.backend.query_rule.fakes import FakeTelemetryRepository
from tests.backend.telemetry.fakes import FakePool


def build_project_service(tmp_path: Path) -> ProjectService:
    """Fully-wired ProjectService -- real Collector/Automater/Dashboard/
    QueryRule services underneath (fake Docker client, fake Timescale
    pool), not just a Mongo-only stub -- needed since ProjectService.delete
    genuinely cascades to each of them, not only its own repository."""
    database = AsyncMongoMockClient()["iotops"]

    collector_service = CollectorService(
        repository=CollectorRepository(database),
        registry=build_default_registry(),
        docker_manager=CollectorDockerManager(
            client=FakeDockerClient(),  # type: ignore[arg-type]
            runtime_dir=tmp_path / "collector-runtime",
            host_runtime_dir=Path("/host/collector-runtime"),
        ),
    )
    automater_service = AutomaterService(
        repository=AutomaterRepository(database),
        registry=build_default_registry(),
        docker_manager=AutomaterDockerManager(
            client=FakeDockerClient(),  # type: ignore[arg-type]
            runtime_dir=tmp_path / "automater-runtime",
            host_runtime_dir=Path("/host/automater-runtime"),
        ),
        collector_service=collector_service,
    )
    telemetry_service = TelemetryService(repository=TelemetryRepository(FakePool(tables=[])))
    dashboard_service = DashboardService(
        repository=DashboardRepository(database), telemetry_service=telemetry_service
    )
    query_rule_service = QueryRuleService(
        repository=QueryRuleRepository(database),
        telemetry_repository=FakeTelemetryRepository(),  # type: ignore[arg-type]
        event_repository=EventRepository(database),
    )

    return ProjectService(
        repository=ProjectRepository(database),
        collector_service=collector_service,
        automater_service=automater_service,
        dashboard_service=dashboard_service,
        query_rule_service=query_rule_service,
    )
