from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.shared.enums import CollectorStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InputPlugin(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    plugin_type: str
    name: str
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)


class ProcessorPlugin(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    plugin_type: str
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)


class OutputPlugin(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    plugin_type: str
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)


class DockerConfig(BaseModel):
    image: str
    container_name: str
    network: str = "iotops"
    restart_policy: str = "unless-stopped"
    volumes: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)


class CollectorPluginsBase(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    inputs: list[InputPlugin]
    processors: list[ProcessorPlugin] = Field(default_factory=list)
    outputs: list[OutputPlugin]

    @model_validator(mode="after")
    def _validate_plugins(self) -> "CollectorPluginsBase":
        if not self.inputs:
            raise ValueError("Collector must contain at least one input")
        if not self.outputs:
            raise ValueError("Collector must contain at least one output")
        return self


class CollectorInput(CollectorPluginsBase):
    pass


class Collector(CollectorPluginsBase):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    status: CollectorStatus = CollectorStatus.CREATED
    docker: DockerConfig | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
