from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.ai.models import (
    AutomaterRuleSuggestion,
    AutomaterRuleSuggestionState,
    CopilotSuggestion,
    QueryRuleSuggestion,
    QueryRuleSuggestionState,
)
from app.automater.models import Condition, ConditionOperator, ResolveMode, RuleOperator, RuleSeverity
from app.automater.service import AutomaterService
from app.event.models import OccurrenceStatus
from app.event.service import EventService
from app.query_rule.models import QueryRuleSchedule
from app.query_rule.service import QueryRuleService
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

LIST_EXISTING_RULES_TOOL = {
    "name": "list_existing_rules",
    "description": (
        "Look up this project's existing real-time Rules (Automaters) and "
        "scheduled Query Rules -- use this before proposing a new one, so "
        "you don't duplicate coverage and so you can reuse the same "
        "identifier column names an existing rule already uses for the "
        "same entity."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

# Mirrors QueryRuleEditor.tsx's own INTERVAL_PRESETS -- a suggested
# interval must land on one of these or it won't pre-select anything in
# that form's dropdown.
_SCHEDULE_INTERVAL_PRESETS = ["1m", "5m", "10m", "15m", "30m", "1h", "3h", "6h", "12h", "24h"]

SUGGEST_AUTOMATION_TOOL = {
    "name": "suggest_automation",
    "description": (
        "Propose a new Rule once you have enough information (from "
        "list_existing_rules and query_telemetry) to make a grounded "
        "suggestion -- never propose a threshold you haven't checked "
        "against real telemetry statistics first. Choose kind="
        "'automater_rule' for a real-time, single-table condition (e.g. "
        "'temperature > 38'); choose kind='query_rule' for anything "
        "needing a cross-table join or a time-windowed aggregate (e.g. "
        "'average vibration over the last hour per machine'). This does "
        "not create anything -- it hands the user a prefilled, reviewable "
        "draft."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["automater_rule", "query_rule"]},
            "name": {"type": "string", "description": "Short rule name."},
            "category": {"type": "string"},
            "event_type": {"type": "string"},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "message": {
                "type": "string",
                "description": "Shown on the occurrence when this rule fires.",
            },
            "resolve_mode": {
                "type": "string",
                "enum": ["auto", "manual"],
                "description": "auto (default) clears the moment the condition stops matching; "
                "manual requires a human to resolve it.",
            },
            "identifiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Column(s) identifying one matching entity (e.g. device_id). Reuse "
                "an existing rule's identifier spelling for the same entity if one exists -- "
                "dashboard variables match on this name later.",
            },
            "table": {
                "type": "string",
                "description": "Required when kind='automater_rule': the table this rule watches.",
            },
            "conditions": {
                "type": "array",
                "description": "Required when kind='automater_rule'. Evaluated left-to-right, no "
                "precedence -- `join` combines a condition with the running result of every "
                "condition before it and is ignored on the first condition.",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "operator": {"type": "string", "enum": [">", ">=", "<", "<=", "==", "!="]},
                        "value": {"description": "Number, string, or boolean."},
                        "join": {"type": "string", "enum": ["AND", "OR"]},
                    },
                    "required": ["column", "operator", "value"],
                },
            },
            "sql": {
                "type": "string",
                "description": "Required when kind='query_rule': a single SELECT returning one "
                "row per matching entity (GROUP BY the identifier column(s), HAVING for any "
                "aggregate threshold) -- see query_telemetry's own rules for this database.",
            },
            "schedule_interval": {
                "type": "string",
                "enum": _SCHEDULE_INTERVAL_PRESETS,
                "description": "For kind='query_rule': how often to re-run the query. Mutually "
                "exclusive with schedule_cron.",
            },
            "schedule_cron": {
                "type": "string",
                "description": "For kind='query_rule': a 5-field cron expression, only if a fixed "
                "interval genuinely doesn't fit (e.g. 'daily at 3am'). Mutually exclusive with "
                "schedule_interval.",
            },
        },
        "required": ["kind", "name", "severity", "identifiers"],
    },
}

# Always the full set, in every conversation -- this used to split into a
# 3-tool default and a 5-tool "suggest-automation intent" variant, gated
# behind which button opened the panel. That meant a plain "I want to
# create a rule" typed into the ordinary Co-pilot had no suggest_automation
# tool available at all, and the model correctly (from its own
# perspective) said it couldn't create one after a long clarifying
# conversation. The model's own judgment already keeps query_occurrences/
# query_telemetry/flag_missing_context from firing on the wrong kind of
# question; it's trusted to do the same for these two.
COPILOT_TOOLS = [
    QUERY_OCCURRENCES_TOOL,
    QUERY_TELEMETRY_TOOL,
    FLAG_MISSING_CONTEXT_TOOL,
    LIST_EXISTING_RULES_TOOL,
    SUGGEST_AUTOMATION_TOOL,
]

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


async def run_list_existing_rules(
    automater_service: AutomaterService, query_rule_service: QueryRuleService, project_id: UUID
) -> str:
    # AutomaterService.list() has no project filter (mirrors how
    # run_query_occurrences's own event_service call is the one that's
    # project-scoped, not every service in this module) -- filter here.
    automaters = [a for a in await automater_service.list() if a.project_id == project_id]
    query_rules = await query_rule_service.list(project_id)

    if not automaters and not query_rules:
        return "This project has no existing Rules or Query Rules yet."

    lines = []
    for automater in automaters:
        for rule in automater.rules:
            conditions = " ".join(
                (f"{c.join.value} " if i else "") + f"{c.column} {c.operator.value} {c.value}"
                for i, c in enumerate(rule.conditions)
            )
            identifiers = ", ".join(rule.identifiers) or "none"
            lines.append(
                f"- [real-time] \"{rule.name}\": table={rule.table} conditions=({conditions}) "
                f"identifiers={identifiers} severity={rule.severity.value}"
            )
    for query_rule in query_rules:
        schedule = (
            f"every {query_rule.schedule.interval}"
            if query_rule.schedule.interval
            else f"cron {query_rule.schedule.cron}"
        )
        identifiers = ", ".join(query_rule.identifiers) or "none"
        sql_gist = query_rule.sql if len(query_rule.sql) <= 200 else query_rule.sql[:200] + "..."
        lines.append(
            f"- [scheduled, {schedule}] \"{query_rule.name}\": sql=({sql_gist}) "
            f"identifiers={identifiers} severity={query_rule.severity.value}"
        )
    return "\n".join(lines)


def run_suggest_automation(
    project_id: UUID, input_: dict[str, Any]
) -> tuple[str, CopilotSuggestion | None]:
    kind = input_.get("kind", "")
    try:
        suggestion = _build_suggestion(project_id, kind, input_)
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        return f"Couldn't build that suggestion: {exc}. Adjust the fields and try again.", None

    kind_label = "real-time" if kind == "automater_rule" else "scheduled"
    return (
        f"Drafted a {kind_label} rule -- mention in your answer that a draft is ready for "
        "review below, and ask if they'd like any adjustments.",
        suggestion,
    )


def _build_suggestion(project_id: UUID, kind: str, input_: dict[str, Any]) -> CopilotSuggestion:
    common = {
        "category": input_.get("category", ""),
        "event_type": input_.get("event_type", ""),
        "severity": RuleSeverity(input_.get("severity", "low")),
        "message": input_.get("message", ""),
        "resolve_mode": ResolveMode(input_.get("resolve_mode", "auto")),
        "identifiers": input_.get("identifiers", []),
    }
    name = input_.get("name", "")

    if kind == "automater_rule":
        conditions = [
            Condition(
                column=c["column"],
                operator=ConditionOperator(c["operator"]),
                value=c["value"],
                join=RuleOperator(c.get("join", "AND")),
            )
            for c in input_.get("conditions", [])
        ]
        state = AutomaterRuleSuggestionState(
            project_id=project_id,
            rule_name=name,
            table=input_.get("table", ""),
            conditions=conditions,
            **common,
        )
        return AutomaterRuleSuggestion(label=f"New real-time rule: {name}", state=state)

    if kind == "query_rule":
        interval = input_.get("schedule_interval")
        cron = input_.get("schedule_cron")
        # Coerced to exactly one, matching QueryRuleSchedule's own
        # validator -- interval wins if the model (incorrectly) set both.
        schedule = QueryRuleSchedule(interval=interval or None, cron=None if interval else cron)
        state = QueryRuleSuggestionState(
            project_id=project_id,
            name=name,
            sql=input_.get("sql", ""),
            schedule=schedule,
            **common,
        )
        return QueryRuleSuggestion(label=f"New scheduled rule: {name}", state=state)

    raise ValueError(f"Unknown suggestion kind '{kind}' -- must be automater_rule or query_rule")
