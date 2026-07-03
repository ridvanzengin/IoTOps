from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_telemetry_service
from app.telemetry.models import TelemetryQueryResult
from app.telemetry.service import TelemetryService

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/tables", response_model=list[str])
async def list_telemetry_tables(
    service: TelemetryService = Depends(get_telemetry_service),
) -> list[str]:
    return await service.list_tables()


@router.get("/{table}", response_model=TelemetryQueryResult)
async def query_telemetry(
    table: str,
    limit: int = Query(default=100, ge=1, le=1000),
    since: datetime | None = None,
    service: TelemetryService = Depends(get_telemetry_service),
) -> TelemetryQueryResult:
    return await service.query_recent(table, limit, since)
