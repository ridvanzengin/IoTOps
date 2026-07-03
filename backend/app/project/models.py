from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectInput(BaseModel):
    name: str
    description: str = ""


class Project(ProjectInput):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
