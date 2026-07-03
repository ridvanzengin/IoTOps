from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.collector.api import router as collector_router
from app.config import settings
from app.plugin.api import router as plugin_router
from app.shared.exceptions import EntityNotFoundError, PluginConfigurationError
from app.telemetry.api import router as telemetry_router

app = FastAPI(title="IoTOps")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collector_router)
app.include_router(plugin_router)
app.include_router(telemetry_router)


@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(PluginConfigurationError)
async def plugin_configuration_error_handler(
    request: Request, exc: PluginConfigurationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
