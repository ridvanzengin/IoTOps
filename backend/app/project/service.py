from uuid import UUID

from app.automater.service import AutomaterService
from app.collector.service import CollectorService
from app.dashboard.service import DashboardService
from app.project.models import Project, ProjectInput
from app.project.repository import ProjectRepository
from app.query_rule.service import QueryRuleService


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        collector_service: CollectorService,
        automater_service: AutomaterService,
        dashboard_service: DashboardService,
        query_rule_service: QueryRuleService,
    ) -> None:
        self._repository = repository
        self._collector_service = collector_service
        self._automater_service = automater_service
        self._dashboard_service = dashboard_service
        self._query_rule_service = query_rule_service

    async def create(self, payload: ProjectInput) -> Project:
        project = Project(**payload.model_dump())
        return await self._repository.create(project)

    async def get(self, project_id: UUID) -> Project:
        return await self._repository.get(project_id)

    async def list(self) -> list[Project]:
        return await self._repository.list()

    async def update(self, project_id: UUID, payload: ProjectInput) -> Project:
        existing = await self._repository.get(project_id)
        updated = existing.model_copy(
            update={
                "name": payload.name,
                "description": payload.description,
                "ai_context": payload.ai_context,
                "default_dashboard_id": payload.default_dashboard_id,
            }
        )
        return await self._repository.update(updated)

    async def delete(self, project_id: UUID) -> None:
        # Every related entity's own delete() already does its own
        # cleanup correctly (CollectorService/AutomaterService stop and
        # remove their deployed Docker containers before deleting the
        # Mongo doc) -- this just has to find and call each one, not
        # reimplement any of that. Automaters first: an Automater's own
        # delete() touches Collectors via _remove_http_forwarding, so it
        # should run while its Collector still exists (nothing actually
        # breaks either order, this is just the more sensible sequencing).
        automaters = await self._automater_service.list()
        for automater in automaters:
            if automater.project_id == project_id:
                await self._automater_service.delete(automater.id)

        for query_rule in await self._query_rule_service.list(project_id):
            await self._query_rule_service.delete(query_rule.id)

        collectors = await self._collector_service.list()
        for collector in collectors:
            if collector.project_id == project_id:
                await self._collector_service.delete(collector.id)

        dashboards = await self._dashboard_service.list()
        for dashboard in dashboards:
            if dashboard.project_id == project_id:
                await self._dashboard_service.delete(dashboard.id)

        await self._repository.delete(project_id)
