from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.api import router as ai_router
from app.automater.api import router as automater_router
from app.collector.api import router as collector_router
from app.config import settings
from app.dashboard.api import router as dashboard_router
from app.event.api import router as event_router
from app.plugin.api import router as plugin_router
from app.project.api import router as project_router
from app.query_rule.api import router as query_rule_router
from app.shared.exceptions import (
    AiGenerationError,
    DuplicateNameError,
    EntityNotFoundError,
    InvalidOperationError,
    InvalidQueryError,
    PluginConfigurationError,
    QueryExecutionError,
)
from app.telemetry.api import router as telemetry_router

app = FastAPI(title="IoTOps")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_router)
app.include_router(automater_router)
app.include_router(collector_router)
app.include_router(dashboard_router)
app.include_router(event_router)
app.include_router(plugin_router)
app.include_router(project_router)
app.include_router(query_rule_router)
app.include_router(telemetry_router)


@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(PluginConfigurationError)
async def plugin_configuration_error_handler(
    request: Request, exc: PluginConfigurationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(InvalidQueryError)
async def invalid_query_error_handler(request: Request, exc: InvalidQueryError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(QueryExecutionError)
async def query_execution_error_handler(request: Request, exc: QueryExecutionError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(DuplicateNameError)
async def duplicate_name_error_handler(request: Request, exc: DuplicateNameError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(InvalidOperationError)
async def invalid_operation_error_handler(
    request: Request, exc: InvalidOperationError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AiGenerationError)
async def ai_generation_error_handler(request: Request, exc: AiGenerationError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
