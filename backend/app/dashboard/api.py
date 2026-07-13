from uuid import UUID

from fastapi import APIRouter, Depends

from app.dashboard.models import (
    Dashboard,
    DashboardInput,
    DashboardLayoutInput,
    DashboardQueryPreview,
    PanelInput,
    PanelQueryOverrides,
    PanelQueryResult,
    VariableOptionsRequest,
    VariableOptionsResult,
)
from app.dashboard.service import DashboardService
from app.dependencies import get_dashboard_service
from app.telemetry.models import TelemetrySqlQueryResult

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.post("", response_model=Dashboard, status_code=201)
async def create_dashboard(
    payload: DashboardInput,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.create(payload)


@router.get("", response_model=list[Dashboard])
async def list_dashboards(
    service: DashboardService = Depends(get_dashboard_service),
) -> list[Dashboard]:
    return await service.list()


@router.get("/{dashboard_id}", response_model=Dashboard)
async def get_dashboard(
    dashboard_id: UUID,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.get(dashboard_id)


@router.put("/{dashboard_id}", response_model=Dashboard)
async def update_dashboard(
    dashboard_id: UUID,
    payload: DashboardInput,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.update(dashboard_id, payload)


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(
    dashboard_id: UUID,
    service: DashboardService = Depends(get_dashboard_service),
) -> None:
    await service.delete(dashboard_id)


@router.post("/{dashboard_id}/panel", response_model=Dashboard, status_code=201)
async def add_panel(
    dashboard_id: UUID,
    payload: PanelInput,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.add_panel(dashboard_id, payload)


@router.put("/{dashboard_id}/panel/{panel_id}", response_model=Dashboard)
async def update_panel(
    dashboard_id: UUID,
    panel_id: UUID,
    payload: PanelInput,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.update_panel(dashboard_id, panel_id, payload)


@router.delete("/{dashboard_id}/panel/{panel_id}", response_model=Dashboard)
async def remove_panel(
    dashboard_id: UUID,
    panel_id: UUID,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.remove_panel(dashboard_id, panel_id)


@router.put("/{dashboard_id}/layout", response_model=Dashboard)
async def save_layout(
    dashboard_id: UUID,
    payload: DashboardLayoutInput,
    service: DashboardService = Depends(get_dashboard_service),
) -> Dashboard:
    return await service.save_layout(dashboard_id, payload)


@router.post("/{dashboard_id}/panel/{panel_id}/query", response_model=PanelQueryResult)
async def run_panel_query(
    dashboard_id: UUID,
    panel_id: UUID,
    payload: PanelQueryOverrides,
    service: DashboardService = Depends(get_dashboard_service),
) -> PanelQueryResult:
    return await service.run_panel_query_by_id(dashboard_id, panel_id, payload)


@router.post("/{dashboard_id}/preview-query", response_model=TelemetrySqlQueryResult)
async def preview_dashboard_query(
    dashboard_id: UUID,
    payload: DashboardQueryPreview,
    service: DashboardService = Depends(get_dashboard_service),
) -> TelemetrySqlQueryResult:
    return await service.preview_query(dashboard_id, payload)


@router.post("/{dashboard_id}/variables/options", response_model=VariableOptionsResult)
async def resolve_variable_options(
    dashboard_id: UUID,
    payload: VariableOptionsRequest,
    service: DashboardService = Depends(get_dashboard_service),
) -> VariableOptionsResult:
    return await service.resolve_variable_options(dashboard_id, payload)
