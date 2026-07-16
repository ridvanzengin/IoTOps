from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.event.models import OccurrenceStatus
from app.event.service import EventService
from app.shared.exceptions import InvalidQueryError, QueryExecutionError
from app.telemetry.service import TelemetryService

QUERY_OCCURRENCES_TOOL = {
    "name": "query_occurrences",
    "description": (
        "Look up Rule match/clear occurrences (alerts) for this project. Use this "
        "to answer questions about firings, counts, timing, or resolution status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_name": {
                "type": "string",
                "description": "Filter to occurrences whose rule name contains this text. Omit for all rules.",
            },
            "since_hours": {
                "type": "integer",
                "description": "How many hours back from now to search. Defaults to 24 if omitted.",
            },
            "status": {
                "type": "string",
                "enum": ["ACTIVE", "RESOLVED"],
                "description": "Filter by resolution status. Omit for both.",
            },
            "limit": {
                "type": "integer",
                "description": "Max occurrences to return (default 30, capped at 100).",
            },
        },
    },
}

QUERY_TELEMETRY_TOOL = {
    "name": "query_telemetry",
    "description": (
        "Run a single read-only SQL SELECT against this project's telemetry "
        "tables (see the schema you were given) to answer questions about "
        "actual sensor readings/values."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": (
                    "A single SELECT statement. No semicolons. Use explicit ISO "
                    "timestamp bounds for time filtering."
                ),
            },
        },
        "required": ["sql"],
    },
}

FLAG_MISSING_CONTEXT_TOOL = {
    "name": "flag_missing_context",
    "description": (
        "Call this instead of guessing when a telemetry column's meaning is "
        "genuinely ambiguous and no project context explains it (e.g. `val1`, "
        "`sensor_a`, a coded status enum). Do not call this for columns whose "
        "meaning is reasonably clear from the name."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "The ambiguous column name (and table, if useful, e.g. 'machine_telemetry.val1')."},
            "reason": {"type": "string", "description": "Briefly, why its meaning is unclear."},
        },
        "required": ["column", "reason"],
    },
}

COPILOT_TOOLS = [QUERY_OCCURRENCES_TOOL, QUERY_TELEMETRY_TOOL, FLAG_MISSING_CONTEXT_TOOL]

_MAX_OCCURRENCES_LIMIT = 100
_TELEMETRY_ROW_LIMIT = 50
_TELEMETRY_TIMEOUT_SECONDS = 10.0


async def run_query_occurrences(
    event_service: EventService, project_id: UUID, input_: dict[str, Any]
) -> str:
    since_hours = input_.get("since_hours", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    limit = min(input_.get("limit", 30), _MAX_OCCURRENCES_LIMIT)

    status: OccurrenceStatus | None = None
    raw_status = input_.get("status")
    if raw_status:
        try:
            status = OccurrenceStatus(raw_status.lower())
        except ValueError:
            return f"Invalid status '{raw_status}' -- must be ACTIVE or RESOLVED."

    occurrences, total = await event_service.list_occurrences(
        project_id=project_id,
        limit=limit,
        status=status,
        since=since,
        search=input_.get("rule_name"),
    )

    if not occurrences:
        return f"No occurrences found in the last {since_hours} hour(s) matching these filters."

    lines = [f"{total} matching occurrence(s) in the last {since_hours} hour(s):"]
    for occ in occurrences:
        resolved = f", resolved {occ.resolved_at.isoformat()}" if occ.resolved_at else ""
        identifiers = ", ".join(f"{k}={v}" for k, v in occ.identifiers.items())
        lines.append(
            f"- {occ.matched_at.isoformat()}  rule={occ.rule_name}  "
            f"severity={occ.severity.value}  status={occ.status.value}{resolved}  "
            f"identifiers={{{identifiers}}}  message=\"{occ.message}\""
        )
    return "\n".join(lines)


def run_flag_missing_context(input_: dict[str, Any]) -> str:
    # No lookup needed -- this tool is purely a structural signal (see
    # AiService.answer_copilot_question, which captures the args and
    # surfaces them as CopilotAnswerResponse.needs_context) rather than a
    # data source. The model still needs a tool_result to continue the
    # loop and produce its final prose answer, hence the short ack.
    return "Noted -- mention in your answer that this column's meaning is unclear."


async def run_query_telemetry(telemetry_service: TelemetryService, input_: dict[str, Any]) -> str:
    sql = input_.get("sql", "")
    try:
        result = await telemetry_service.run_bounded_query(
            sql, limit=_TELEMETRY_ROW_LIMIT, timeout_seconds=_TELEMETRY_TIMEOUT_SECONDS
        )
    except InvalidQueryError:
        return "Query rejected: only a single, read-only SELECT statement is allowed."
    except QueryExecutionError as exc:
        return f"Query failed: {exc.message}"

    if not result.rows:
        return "Query ran successfully but returned no rows."

    lines = [", ".join(result.columns)]
    for row in result.rows:
        lines.append(", ".join(str(row.get(col, "")) for col in result.columns))
    return "\n".join(lines)
