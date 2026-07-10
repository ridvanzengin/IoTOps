from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


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


class Pipeline(BaseModel):
    """Shared shape for Collector and Automater: a project-scoped, named,
    enable-able flow with at least one input and at least one output.
    Subclasses add their own middle stage (Collector: processors,
    Automater: rules, synthesized into one processor at deploy time).
    """

    project_id: UUID
    name: str
    description: str = ""
    enabled: bool = True
    inputs: list[InputPlugin]
    outputs: list[OutputPlugin]

    @model_validator(mode="after")
    def _validate_io(self) -> "Pipeline":
        if not self.inputs:
            raise ValueError(f"{type(self).__name__} must contain at least one input")
        if not self.outputs:
            raise ValueError(f"{type(self).__name__} must contain at least one output")
        return self
