from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

from app.shared.enums import PluginCategory

_PLUGIN_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def plugin_id(name: str) -> UUID:
    return uuid5(_PLUGIN_NAMESPACE, name)


class Plugin(BaseModel):
    id: UUID
    name: str
    category: PluginCategory
    telegraf_name: str
    version: str = "1.0.0"
    description: str = ""
    configuration_schema: dict[str, Any]
    supported_platforms: list[str] = Field(default_factory=list)
