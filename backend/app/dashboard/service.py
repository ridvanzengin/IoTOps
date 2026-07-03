from uuid import UUID

from app.dashboard.models import (
    Dashboard,
    DashboardInput,
    DashboardLayoutInput,
    Panel,
    PanelInput,
    validate_panel_positions,
)
from app.dashboard.repository import DashboardRepository
from app.shared.exceptions import EntityNotFoundError
from app.telemetry.models import TelemetrySqlQuery, TelemetrySqlQueryResult
from app.telemetry.service import TelemetryService


class DashboardService:
    def __init__(
        self, repository: DashboardRepository, telemetry_service: TelemetryService
    ) -> None:
        self._repository = repository
        self._telemetry_service = telemetry_service

    async def create(self, payload: DashboardInput) -> Dashboard:
        dashboard = Dashboard(**payload.model_dump())
        return await self._repository.create(dashboard)

    async def get(self, dashboard_id: UUID) -> Dashboard:
        return await self._repository.get(dashboard_id)

    async def list(self) -> list[Dashboard]:
        return await self._repository.list()

    async def update(self, dashboard_id: UUID, payload: DashboardInput) -> Dashboard:
        existing = await self._repository.get(dashboard_id)
        updated = existing.model_copy(
            update={
                "project_id": payload.project_id,
                "name": payload.name,
                "description": payload.description,
                "variables": payload.variables,
                "panels": payload.panels,
                "layout": payload.layout,
            }
        )
        validate_panel_positions(updated.panels)
        return await self._repository.update(updated)

    async def delete(self, dashboard_id: UUID) -> None:
        await self._repository.delete(dashboard_id)

    async def add_panel(self, dashboard_id: UUID, payload: PanelInput) -> Dashboard:
        dashboard = await self._repository.get(dashboard_id)
        panel = Panel(**payload.model_dump())
        updated_panels = [*dashboard.panels, panel]
        validate_panel_positions(updated_panels)
        updated = dashboard.model_copy(update={"panels": updated_panels})
        return await self._repository.update(updated)

    async def update_panel(
        self, dashboard_id: UUID, panel_id: UUID, payload: PanelInput
    ) -> Dashboard:
        dashboard = await self._repository.get(dashboard_id)
        if not any(panel.id == panel_id for panel in dashboard.panels):
            raise EntityNotFoundError("Panel", panel_id)

        updated_panels = [
            Panel(id=panel_id, **payload.model_dump()) if panel.id == panel_id else panel
            for panel in dashboard.panels
        ]
        validate_panel_positions(updated_panels)
        updated = dashboard.model_copy(update={"panels": updated_panels})
        return await self._repository.update(updated)

    async def remove_panel(self, dashboard_id: UUID, panel_id: UUID) -> Dashboard:
        dashboard = await self._repository.get(dashboard_id)
        updated_panels = [panel for panel in dashboard.panels if panel.id != panel_id]
        if len(updated_panels) == len(dashboard.panels):
            raise EntityNotFoundError("Panel", panel_id)

        updated = dashboard.model_copy(update={"panels": updated_panels})
        return await self._repository.update(updated)

    async def save_layout(
        self, dashboard_id: UUID, payload: DashboardLayoutInput
    ) -> Dashboard:
        dashboard = await self._repository.get(dashboard_id)
        positions = {update.id: update.position for update in payload.panels}
        updated_panels = [
            panel.model_copy(update={"position": positions[panel.id]})
            if panel.id in positions
            else panel
            for panel in dashboard.panels
        ]
        validate_panel_positions(updated_panels)
        updated = dashboard.model_copy(
            update={"panels": updated_panels, "layout": payload.layout}
        )
        return await self._repository.update(updated)

    async def run_panel_query(self, panel: Panel) -> TelemetrySqlQueryResult:
        sql = panel.query.sql
        for name, value in panel.query.variables.items():
            sql = sql.replace(f"${name}", value)
        return await self._telemetry_service.run_query(
            TelemetrySqlQuery(sql=sql, limit=panel.query.limit)
        )
