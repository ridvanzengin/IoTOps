from __future__ import annotations

from uuid import UUID

from app.dashboard.models import (
    Dashboard,
    DashboardInput,
    DashboardLayoutInput,
    DashboardQueryPreview,
    Panel,
    PanelInput,
    PanelQueryOverrides,
    PanelQueryResult,
    Variable,
    VariableOptionsRequest,
    VariableOptionsResult,
    build_variable_source_sql,
    validate_panel_positions,
    validate_variables,
)
from app.dashboard.repository import DashboardRepository
from app.shared.exceptions import EntityNotFoundError
from app.shared.sql_macros import substitute_macros
from app.shared.time_range import resolve_time_range
from app.telemetry.models import TelemetrySqlQuery, TelemetrySqlQueryResult
from app.telemetry.service import TelemetryService


def _format_variable_value(raw: str) -> str:
    return "'" + raw.replace("'", "''") + "'"


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
        validate_variables(updated.variables)
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

    async def _substitute_and_run(
        self,
        sql: str,
        limit: int,
        *,
        static_variables: dict[str, str],
        dashboard_variables: list[Variable],
        variable_values: dict[str, str],
        time_range: str,
    ) -> TelemetrySqlQueryResult:
        substitutions = dict(static_variables)
        for variable in dashboard_variables:
            raw = variable_values.get(variable.name)
            if raw is None:
                continue
            substitutions[variable.name] = _format_variable_value(raw)

        time_from, time_to = resolve_time_range(time_range)
        substitutions["__timeFrom"] = f"'{time_from.isoformat()}'"
        substitutions["__timeTo"] = f"'{time_to.isoformat()}'"

        resolved_sql = substitute_macros(sql, substitutions)
        return await self._telemetry_service.run_query(
            TelemetrySqlQuery(sql=resolved_sql, limit=limit)
        )

    async def run_panel_query(
        self,
        panel: Panel,
        *,
        dashboard_variables: list[Variable] | None = None,
        time_range: str | None = None,
        variable_values: dict[str, str] | None = None,
    ) -> PanelQueryResult:
        resolved_time_range = time_range or panel.time_range
        result = await self._substitute_and_run(
            panel.query.sql,
            panel.query.limit,
            static_variables=panel.query.variables,
            dashboard_variables=dashboard_variables or [],
            variable_values=variable_values or {},
            time_range=resolved_time_range,
        )
        # Cheap to resolve again rather than threading a return value
        # through _substitute_and_run (shared by preview_query/
        # resolve_variable_options too, neither of which need the
        # bounds) -- resolve_time_range is just `now() - timedelta`, and
        # the few milliseconds between this call and the one inside
        # _substitute_and_run don't matter for a chart overlay window.
        time_from, time_to = resolve_time_range(resolved_time_range)
        return PanelQueryResult(
            columns=result.columns, rows=result.rows, time_from=time_from, time_to=time_to
        )

    async def run_panel_query_by_id(
        self, dashboard_id: UUID, panel_id: UUID, overrides: PanelQueryOverrides
    ) -> PanelQueryResult:
        dashboard = await self._repository.get(dashboard_id)
        panel = next((p for p in dashboard.panels if p.id == panel_id), None)
        if panel is None:
            raise EntityNotFoundError("Panel", panel_id)

        return await self.run_panel_query(
            panel,
            dashboard_variables=dashboard.variables,
            time_range=overrides.time_range,
            variable_values=overrides.variable_values,
        )

    async def preview_query(
        self, dashboard_id: UUID, request: DashboardQueryPreview
    ) -> TelemetrySqlQueryResult:
        dashboard = await self._repository.get(dashboard_id)
        return await self._substitute_and_run(
            request.sql,
            request.limit,
            static_variables={},
            dashboard_variables=dashboard.variables,
            variable_values=request.variable_values,
            time_range=request.time_range,
        )

    async def resolve_variable_options(
        self, dashboard_id: UUID, request: VariableOptionsRequest
    ) -> VariableOptionsResult:
        dashboard = await self._repository.get(dashboard_id)
        sql = build_variable_source_sql(
            request.table,
            request.value_column,
            request.predicate_column,
            request.predicate_variable,
        )
        result = await self._substitute_and_run(
            sql,
            1000,
            static_variables={},
            dashboard_variables=dashboard.variables,
            variable_values=request.variable_values,
            time_range="1h",
        )
        if not result.rows or not result.columns:
            return VariableOptionsResult(options=[])
        first_column = result.columns[0]
        return VariableOptionsResult(
            options=[str(row[first_column]) for row in result.rows]
        )
