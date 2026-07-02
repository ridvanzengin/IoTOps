from fastapi import APIRouter, Depends

from app.dependencies import get_plugin_registry
from app.plugin.models import Plugin
from app.plugin.registry import PluginRegistry
from app.shared.enums import PluginCategory

router = APIRouter(prefix="/api/plugin", tags=["plugin"])


@router.get("", response_model=list[Plugin])
async def list_plugins(
    category: PluginCategory | None = None,
    registry: PluginRegistry = Depends(get_plugin_registry),
) -> list[Plugin]:
    return registry.list(category=category)


@router.get("/{plugin_type}", response_model=Plugin)
async def get_plugin(
    plugin_type: str,
    registry: PluginRegistry = Depends(get_plugin_registry),
) -> Plugin:
    return registry.get(plugin_type)
