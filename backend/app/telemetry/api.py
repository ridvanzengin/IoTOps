from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_telemetry_service
from app.telemetry.models import (
    TelemetryQueryResult,
    TelemetrySqlQuery,
    TelemetrySqlQueryResult,
    TelemetryTableSchema,
)
from app.telemetry.service import TelemetryService

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/tables", response_model=list[str])
async def list_telemetry_tables(
    service: TelemetryService = Depends(get_telemetry_service),
) -> list[str]:
    return await service.list_tables()


# Declared before GET /{table} so "schema" isn't swallowed by the {table} path param.
@router.get("/schema", response_model=list[TelemetryTableSchema])
async def get_telemetry_schema(
    service: TelemetryService = Depends(get_telemetry_service),
) -> list[TelemetryTableSchema]:
    return await service.get_schema()


@router.post("/query", response_model=TelemetrySqlQueryResult)
async def query_telemetry_sql(
    payload: TelemetrySqlQuery,
    service: TelemetryService = Depends(get_telemetry_service),
) -> TelemetrySqlQueryResult:
    return await service.run_query(payload)


@router.get("/{table}", response_model=TelemetryQueryResult)
async def query_telemetry(
    table: str,
    limit: int = Query(default=100, ge=1, le=1000),
    since: datetime | None = None,
    service: TelemetryService = Depends(get_telemetry_service),
) -> TelemetryQueryResult:
    return await service.query_recent(table, limit, since)
