from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectInput(BaseModel):
    name: str
    description: str = ""

    # Which of this project's Dashboards the activity bar navigates to on
    # icon click, and the toolbar dashboard-switcher pre-selects. Not
    # validated against the dashboard collection -- no cross-collection
    # reference check exists anywhere else in this module either (compare
    # Dashboard.project_id, also never checked against Project), and a
    # dangling id here is harmless: the frontend just falls back to the
    # first dashboard it finds if this one doesn't resolve.
    default_dashboard_id: UUID | None = None


class Project(ProjectInput):
    schema_version: int = 1
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
