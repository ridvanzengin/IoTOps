import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg
from croniter import croniter

from app.automater.models import ResolveMode
from app.event.models import Event, EventFlag, OccurrenceStatus
from app.event.repository import EventRepository
from app.query_rule.models import QueryRule, QueryRuleInput
from app.query_rule.repository import QueryRuleRepository
from app.shared.exceptions import InvalidOperationError, QueryExecutionError
from app.shared.validators import validate_select_only_sql
from app.telemetry.models import TelemetrySqlQueryResult
from app.telemetry.repository import TelemetryRepository

logger = logging.getLogger(__name__)

_EXECUTION_TIMEOUT_SECONDS = 10.0
_DURATION_UNITS = {"s": "seconds", "m": "minutes", "h": "hours"}


def _parse_duration(value: str) -> timedelta:
    unit = value[-1] if value else ""
    amount = value[:-1]
    if unit not in _DURATION_UNITS or not amount.isdigit():
        raise InvalidOperationError(
            f"Unsupported interval {value!r} -- expected a number followed by s/m/h, e.g. '5m'"
        )
    return timedelta(**{_DURATION_UNITS[unit]: int(amount)})


def _is_due(query_rule: QueryRule, now: datetime) -> bool:
    if not query_rule.enabled:
        return False
    if query_rule.last_evaluated_at is None:
        return True
    if query_rule.schedule.interval is not None:
        return now >= query_rule.last_evaluated_at + _parse_duration(query_rule.schedule.interval)
    # cron: real next-run semantics (day-of-week/month boundaries) via
    # croniter rather than hand-rolled, see QueryRuleSchedule's own comment.
    next_run = croniter(query_rule.schedule.cron, query_rule.last_evaluated_at).get_next(datetime)
    return now >= next_run


class QueryRuleService:
    def __init__(
        self,
        repository: QueryRuleRepository,
        telemetry_repository: TelemetryRepository,
        event_repository: EventRepository,
    ) -> None:
        self._repository = repository
        self._telemetry_repository = telemetry_repository
        self._event_repository = event_repository

    async def create(self, payload: QueryRuleInput) -> QueryRule:
        # Validated at authoring time, not just at the first scheduled
        # evaluation -- same guard TelemetryService/AiService already
        # apply before ever running a query (app/shared/validators.py),
        # reused verbatim.
        validate_select_only_sql(payload.sql)
        query_rule = QueryRule(**payload.model_dump())
        return await self._repository.create(query_rule)

    async def get(self, query_rule_id: UUID) -> QueryRule:
        return await self._repository.get(query_rule_id)

    async def update(self, query_rule_id: UUID, payload: QueryRuleInput) -> QueryRule:
        validate_select_only_sql(payload.sql)
        existing = await self._repository.get(query_rule_id)
        updated = existing.model_copy(
            update={
                "project_id": payload.project_id,
                "name": payload.name,
                "description": payload.description,
                "sql": payload.sql,
                "nl_prompt": payload.nl_prompt,
                "identifiers": payload.identifiers,
                "category": payload.category,
                "severity": payload.severity,
                "event_type": payload.event_type,
                "message": payload.message,
                "resolve_mode": payload.resolve_mode,
                "schedule": payload.schedule,
                "enabled": payload.enabled,
            }
        )
        return await self._repository.update(updated)

    async def delete(self, query_rule_id: UUID) -> None:
        await self._repository.delete(query_rule_id)

    async def execute(
        self, sql: str, timeout_seconds: float = _EXECUTION_TIMEOUT_SECONDS
    ) -> list[dict[str, Any]]:
        validate_select_only_sql(sql)
        try:
            return await self._telemetry_repository.execute_match_query(sql, timeout_seconds)
        except (asyncpg.PostgresError, TimeoutError) as exc:
            raise QueryExecutionError(str(exc)) from exc

    async def preview(self, sql: str) -> TelemetrySqlQueryResult:
        # Same execution path evaluate() uses (same timeout, no OFFSET
        # wrapping) -- what an author previews before saving is exactly
        # what will run on schedule, not an approximation of it.
        rows = await self.execute(sql)
        columns = list(rows[0].keys()) if rows else []
        return TelemetrySqlQueryResult(columns=columns, rows=rows)

    async def evaluate(self, query_rule: QueryRule) -> None:
        """Runs the query, diffs its current result set (keyed by
        `identifiers`) against currently-open occurrences for this rule,
        and writes match/clear Events for whatever changed. Mirrors
        rule.go's own suppress-the-repeat / skip-clear-for-manual
        semantics without touching Redis -- re-arm here comes from the
        next evaluation cycle simply not finding the identifier tuple in
        its open set anymore, not a TTL. See iotops-workspace/ROADMAP.md's
        "Query Rules" note.
        """
        rows = await self.execute(query_rule.sql)
        current_by_key: dict[tuple[str, ...], dict[str, Any]] = {}
        for row in rows:
            key = tuple(str(row.get(column, "")) for column in query_rule.identifiers)
            current_by_key[key] = row

        # Unbounded by time/limit deliberately -- this is the evaluation
        # engine's own bookkeeping (which identifiers are currently open
        # for this rule), not a UI page. A still-open occurrence from
        # arbitrarily long ago is exactly what re-arm/clear detection
        # needs to see; the sidebar's 1h-default windowing is a display
        # concern for EventsPanel, not this loop.
        open_occurrences, _total = await self._event_repository.list_occurrences(
            rule_ids=[query_rule.id], status=OccurrenceStatus.ACTIVE, limit=100_000
        )
        open_by_key = {
            tuple(occurrence.identifiers.get(column, "") for column in query_rule.identifiers): occurrence
            for occurrence in open_occurrences
        }

        now = datetime.now(timezone.utc)

        for key, row in current_by_key.items():
            if key not in open_by_key:
                identifiers = dict(zip(query_rule.identifiers, key))
                await self._write_event(query_rule, EventFlag.MATCH, identifiers, row, now)

        if query_rule.resolve_mode != ResolveMode.MANUAL:
            for key, occurrence in open_by_key.items():
                if key not in current_by_key:
                    await self._write_event(query_rule, EventFlag.CLEAR, occurrence.identifiers, {}, now)

    async def _write_event(
        self,
        query_rule: QueryRule,
        flag: EventFlag,
        identifiers: dict[str, str],
        row: dict[str, Any],
        now: datetime,
    ) -> None:
        non_identifier_fields = {
            column: value for column, value in row.items() if column not in query_rule.identifiers
        }
        event = Event(
            project_id=query_rule.project_id,
            source_type="query_rule",
            query_rule_id=query_rule.id,
            rule_id=query_rule.id,
            rule_name=query_rule.name,
            category=query_rule.category,
            severity=query_rule.severity,
            event_type=query_rule.event_type,
            message=query_rule.message,
            flag=flag,
            resolve_mode=query_rule.resolve_mode,
            identifier_keys=query_rule.identifiers,
            tags={key: str(value) for key, value in identifiers.items()},
            fields=non_identifier_fields,
            matched_at=now,
        )
        await self._event_repository.create(event)

    async def evaluate_due(self) -> None:
        """The Celery Beat ticker's entry point (app/query_rule/tasks.py)
        -- checks every QueryRule's own schedule rather than Beat tracking
        N independent schedules itself. `last_evaluated_at` is stamped
        even when evaluation raises, so a broken query backs off to its
        own normal cadence instead of being retried every tick.
        """
        now = datetime.now(timezone.utc)
        for query_rule in await self._repository.list():
            if not _is_due(query_rule, now):
                continue
            try:
                await self.evaluate(query_rule)
            except Exception:
                logger.exception("Query Rule %s evaluation failed", query_rule.id)
            finally:
                await self._repository.update(query_rule.model_copy(update={"last_evaluated_at": now}))

    # Defined last: a `list[...]` annotation on a method that comes *after*
    # a method literally named `list` in this same class body would resolve
    # `list` against the class namespace (already rebound to that method),
    # not the builtin -- see AutomaterService._synthesize_rule_processor's
    # own comment on the same gotcha.
    async def list(self, project_id: UUID | None = None) -> list[QueryRule]:
        return await self._repository.list(project_id)
