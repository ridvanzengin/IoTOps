from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import Field

from app.shared.enums import CollectorStatus
from app.shared.models import DockerConfig, Pipeline, ProcessorPlugin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CollectorPluginsBase(Pipeline):
    processors: list[ProcessorPlugin] = Field(default_factory=list)


class CollectorInput(CollectorPluginsBase):
    pass


class Collector(CollectorPluginsBase):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    status: CollectorStatus = CollectorStatus.CREATED
    docker: DockerConfig | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
