from datetime import datetime
from uuid import UUID

from app.event.models import Event, EventRuleCount, Occurrence, ProjectUnresolvedCount
from app.event.repository import EventRepository


class EventService:
    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository

    # Defined before `list` below -- see EventRepository's own comment on
    # why (a `list[...]` annotation on a method after one literally named
    # `list` resolves against the class namespace, not the builtin).
    async def counts_by_rule(self, project_id: UUID | None = None) -> list[EventRuleCount]:
        return await self._repository.counts_by_rule(project_id)

    async def list_occurrences(self, project_id: UUID | None = None, limit: int = 50) -> list[Occurrence]:
        return await self._repository.list_occurrences(project_id, limit)

    async def unresolved_counts_by_project(self) -> list[ProjectUnresolvedCount]:
        return await self._repository.unresolved_counts_by_project()

    async def list(
        self,
        project_id: UUID | None = None,
        limit: int = 50,
        since: datetime | None = None,
        until: datetime | None = None,
        rule_ids: list[UUID] | None = None,
    ) -> list[Event]:
        return await self._repository.list(project_id, limit, since, until, rule_ids)
