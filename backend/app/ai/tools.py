from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.ai.models import (
    AutomaterRuleSuggestion,
    AutomaterRuleSuggestionState,
    CopilotSuggestion,
    DashboardPanelSuggestion,
    DashboardSuggestion,
    DashboardSuggestionState,
    PanelSuggestion,
    PanelSuggestionState,
    QueryRuleSuggestion,
    QueryRuleSuggestionState,
)
from app.automater.models import Condition, ConditionOperator, ResolveMode, RuleOperator, RuleSeverity
from app.automater.service import AutomaterService
from app.dashboard.models import (
    BarChart,
    Chart,
    GaugeChart,
    LineChart,
    PieChart,
    Query,
    ScatterChart,
    SeriesConfig,
    Variable,
)
from app.dashboard.service import DashboardService
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

LIST_EXISTING_PANELS_TOOL = {
    "name": "list_existing_panels",
    "description": (
        "Look up this project's existing dashboards and the panels already on each "
        "one -- use this before proposing a new panel, so you don't duplicate an "
        "existing chart, and so you learn each dashboard's real id (needed for "
        "suggest_panel's dashboard_id) and the variables it already defines (needed "
        "to know what's available to filter by, e.g. $hive_id). If the project has "
        "more than one dashboard and it isn't already obvious which one the user "
        "means, ask them (quick-replies with the dashboard names work well) before "
        "calling suggest_panel -- don't guess."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

SUGGEST_PANEL_TOOL = {
    "name": "suggest_panel",
    "description": (
        "Propose a new dashboard panel/chart once you have enough information (from "
        "list_existing_panels and query_telemetry) to make a grounded suggestion -- "
        "never propose a chart's fields without having checked via query_telemetry "
        "that the SQL actually returns those columns with sensible values first. "
        "This does not create anything -- it hands the user a prefilled, reviewable "
        "draft in the Panel Builder."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dashboard_id": {
                "type": "string",
                "description": "The id of the dashboard this panel is added to. Use the id "
                "already given to you for the dashboard currently open in this conversation "
                "if one was mentioned; otherwise use an id you saw in list_existing_panels' "
                "output, asking the user which dashboard first if more than one exists and "
                "it isn't obvious which they mean.",
            },
            "title": {
                "type": "string",
                "description": "Short panel title describing what it shows (e.g. 'Vibration Over "
                "Time', 'Vibration by Machine'). Never append a parenthetical qualifier like "
                "'(Selected Machine)' -- the dashboard's own variable selector already shows what's "
                "currently selected, so repeating it in every panel's title is redundant.",
            },
            "chart_type": {
                "type": "string",
                "enum": ["line", "bar", "scatter", "pie", "gauge"],
                "description": "scatter means individual unconnected points over time (or over a "
                "grouping column, like bar) -- e.g. noisy/sparse readings where a connected line "
                "would misleadingly imply interpolation between them. It does NOT mean plotting "
                "two arbitrary numeric metrics against each other (e.g. temperature vs irradiance) "
                "-- this platform's chart types don't support that kind of true X-Y correlation "
                "panel; x_axis for line/bar/scatter alike is always time or a grouping column, "
                "never a second measured value. If a request is really asking to correlate two "
                "metrics, pick whichever of them is more naturally the grouping dimension for "
                "x_axis (or use time) rather than inventing an unsupported chart shape.",
            },
            "sql": {
                "type": "string",
                "description": "A single SELECT statement for the panel's query. Follow "
                "query_telemetry's own SQL rules (single SELECT, no semicolon), but validate "
                "it with query_telemetry first using literal ISO timestamp bounds, then "
                "translate the final version to use these macros instead of literal values: "
                "$__timeFrom / $__timeTo for time-bounding (e.g. `WHERE time >= $__timeFrom "
                "AND time <= $__timeTo`), so the panel stays correct as the dashboard's own "
                "time range control changes; and, only when the request is specifically about "
                "'the selected/current X' rather than 'one series per X', $variable_name for "
                "any variable list_existing_panels showed you the target dashboard already "
                "defines (e.g. `WHERE hive_id = $hive_id`) -- do not invent variable names "
                "that weren't listed, and do not use a variable when the request actually "
                "wants one row/series per distinct value of that column (use a plain group-by "
                "column for that instead, see x_axis/series_by below).",
            },
            "time_range": {
                "type": "string",
                "description": "Default time window, e.g. '15m', '1h', '6h', '24h', '7d'. "
                "Defaults to '1h' if omitted.",
            },
            "x_axis": {
                "type": "string",
                "description": "Required when chart_type is line, bar, or scatter. Almost always "
                "'time' (the whole point of this being a monitoring dashboard) -- or, for a bar/"
                "scatter comparing entities, a grouping column like a machine/hive id. Never a "
                "second continuous measured value (see chart_type's own description).",
            },
            "y_axis": {
                "type": "string",
                "description": "Required when chart_type is line, bar, or scatter -- the "
                "primary series' value column.",
            },
            "series": {
                "type": "array",
                "description": "Optional additional series for line/bar/scatter, beyond "
                "y_axis. Mutually exclusive with series_by.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "label": {"type": "string"},
                        "axis": {"type": "string", "enum": ["left", "right"]},
                        "type": {
                            "type": "string",
                            "enum": ["line", "bar", "scatter"],
                            "description": "Overrides chart_type for just this series; omit to inherit.",
                        },
                    },
                    "required": ["field"],
                },
            },
            "series_by": {
                "type": "string",
                "description": "Optional: split into one series per distinct value of this "
                "column (e.g. one line per hive) -- use this, not a $variable, for 'per X' "
                "requests. Mutually exclusive with series.",
            },
            "label_field": {"type": "string", "description": "Required when chart_type is pie."},
            "value_field": {
                "type": "string",
                "description": "Required when chart_type is pie or gauge.",
            },
            "min": {"type": "number", "description": "For chart_type=gauge. Defaults to 0."},
            "max": {"type": "number", "description": "For chart_type=gauge. Defaults to 100."},
        },
        "required": ["dashboard_id", "title", "chart_type", "sql"],
    },
}

# One panel's worth of fields, shared by SUGGEST_DASHBOARD_TOOL's `panels`
# array items below -- identical to SUGGEST_PANEL_TOOL's own per-panel
# properties minus dashboard_id (a dashboard suggestion's panels don't
# have one yet, the dashboard itself doesn't exist until the user
# confirms).
_DASHBOARD_PANEL_ITEM_SCHEMA = {
    "type": "object",
    "properties": {k: v for k, v in SUGGEST_PANEL_TOOL["input_schema"]["properties"].items() if k != "dashboard_id"},
    "required": ["title", "chart_type", "sql"],
}

SUGGEST_DASHBOARD_TOOL = {
    "name": "suggest_dashboard",
    "description": (
        "Propose a whole new starter dashboard -- a name, optionally a chain of "
        "variables, and every panel worth having -- once you've surveyed the "
        "project's data via list_existing_panels and query_telemetry. Unlike "
        "suggest_panel, propose the full set of panels you found worth monitoring in "
        "one call, not just the single strongest one -- the user reviews the whole "
        "set at once and creates it in one action, never one panel at a time. This "
        "does not create anything -- it hands the user a reviewable draft; nothing is "
        "written until they confirm."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short dashboard name."},
            "description": {"type": "string"},
            "variables": {
                "type": "array",
                "description": "Optional, ordered. Omit entirely for a flat overview dashboard "
                "with no per-entity filtering -- only propose variables when the data has an "
                "obvious per-entity grouping (e.g. a hive_id/machine_id column) and it's genuinely "
                "useful to filter by it. REQUIRED if declared: at least one item in `panels` "
                "must actually filter or group by a declared variable's name -- a variable with "
                "no panel using it is rejected, since it'd be pure decoration on the dashboard. "
                "For a chain, only the leaf actually needs a direct $name reference in some "
                "panel's sql -- a chain parent (referenced via a later item's predicate_variable) "
                "counts as used too, since it's still narrowing the leaf's own options. A later "
                "item's predicate_variable must reference an "
                "earlier item's name in THIS SAME array (e.g. Apiary at index 0, Hive at index 1 "
                "with predicate_variable='apiary'), mirroring how they'd be chained one at a time "
                "in the Variable Builder, just proposed together.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Token used in SQL as $name."},
                        "label": {"type": "string"},
                        "table": {"type": "string"},
                        "value_column": {"type": "string"},
                        "predicate_column": {
                            "type": "string",
                            "description": "Optional -- a same-table column to narrow this "
                            "variable's own options by an earlier variable's selected value.",
                        },
                        "predicate_variable": {
                            "type": "string",
                            "description": "Optional -- pairs with predicate_column; must name an "
                            "earlier item in this array.",
                        },
                    },
                    "required": ["name", "label", "table", "value_column"],
                },
            },
            "panels": {
                "type": "array",
                "description": "Every panel worth having on this dashboard -- aim for at least "
                "4 (typically 4-6), not an exhaustive dump. Rejected if fewer than 3. Each item "
                "follows the exact same rules as suggest_panel's own fields (SQL macros, title convention, "
                "variable-vs-grouping-column choice) -- see suggest_panel's description.",
                "items": _DASHBOARD_PANEL_ITEM_SCHEMA,
            },
        },
        "required": ["name", "panels"],
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
# question; it's trusted to do the same for these five suggestion-related
# tools (list_existing_rules/suggest_automation and their panel/dashboard
# equivalents below) -- never re-gate any of them behind an intent flag.
COPILOT_TOOLS = [
    QUERY_OCCURRENCES_TOOL,
    QUERY_TELEMETRY_TOOL,
    FLAG_MISSING_CONTEXT_TOOL,
    LIST_EXISTING_RULES_TOOL,
    SUGGEST_AUTOMATION_TOOL,
    LIST_EXISTING_PANELS_TOOL,
    SUGGEST_PANEL_TOOL,
    SUGGEST_DASHBOARD_TOOL,
]

def _validation_error_summary(exc: ValidationError) -> str:
    # str(exc) on a raw ValidationError dumps the *entire* input value that
    # failed to validate (every field, as repr'd Python objects) alongside
    # each error's own message -- fine for a small, flat suggestion model,
    # but for DashboardSuggestionState (a list of several panels plus a
    # list of variables) that dump ballooned into a wall of noise the
    # model had to parse to find the one relevant fact. Live-tested to
    # actually cause the model to give up retrying and describe the
    # dashboard in prose instead of calling the tool again. Extracting
    # just each error's own message keeps the retryable signal short
    # regardless of how large the surrounding suggestion is.
    return "; ".join(err["msg"] for err in exc.errors(include_url=False))


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
    except ValidationError as exc:
        return f"Couldn't build that suggestion: {_validation_error_summary(exc)}. Adjust the fields and try again.", None
    except (ValueError, KeyError, TypeError) as exc:
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


def _describe_chart(chart: Chart) -> str:
    if isinstance(chart, (LineChart, BarChart, ScatterChart)):
        series_note = f", +{len(chart.series)} series" if chart.series else ""
        return f"x={chart.x_axis}, y={chart.y_axis}{series_note}"
    if isinstance(chart, PieChart):
        return f"label={chart.label_field}, value={chart.value_field}"
    return f"value={chart.value_field}"  # GaugeChart


async def run_list_existing_panels(dashboard_service: DashboardService, project_id: UUID) -> str:
    # DashboardService.list() has no project filter (same gap as
    # AutomaterService.list(), see run_list_existing_rules above) --
    # filter here.
    dashboards = [d for d in await dashboard_service.list() if d.project_id == project_id]
    if not dashboards:
        return (
            "This project has no dashboards yet -- a dashboard must exist before a "
            "panel can be added to it. Mention that in your answer if relevant."
        )

    lines = []
    for dashboard in dashboards:
        variables = (
            ", ".join(f"${v.name} ({v.label})" for v in dashboard.variables)
            if dashboard.variables
            else "none"
        )
        lines.append(f"Dashboard \"{dashboard.name}\" (id={dashboard.id}), variables: {variables}")
        if not dashboard.panels:
            lines.append("  - no panels yet")
        for panel in dashboard.panels:
            sql_gist = panel.query.sql if len(panel.query.sql) <= 200 else panel.query.sql[:200] + "..."
            lines.append(
                f"  - \"{panel.title}\" ({panel.chart.type}: {_describe_chart(panel.chart)}) "
                f"sql=({sql_gist})"
            )
    return "\n".join(lines)


def run_suggest_panel(input_: dict[str, Any]) -> tuple[str, CopilotSuggestion | None]:
    try:
        suggestion = _build_panel_suggestion(input_)
    except ValidationError as exc:
        return f"Couldn't build that panel suggestion: {_validation_error_summary(exc)}. Adjust the fields and try again.", None
    except (ValueError, KeyError, TypeError) as exc:
        return f"Couldn't build that panel suggestion: {exc}. Adjust the fields and try again.", None
    return (
        "Drafted a panel -- mention in your answer that a draft is ready for review "
        "below, and ask if they'd like any adjustments.",
        suggestion,
    )


def _build_chart(chart_type: str, title: str, input_: dict[str, Any]) -> Chart:
    if chart_type in ("line", "bar", "scatter"):
        series = [
            SeriesConfig(
                field=s["field"], label=s.get("label"), axis=s.get("axis", "left"), type=s.get("type")
            )
            for s in input_.get("series", [])
        ]
        common = {
            "title": title,
            "x_axis": input_.get("x_axis", ""),
            "y_axis": input_.get("y_axis", ""),
            "series": series,
            "series_by": input_.get("series_by"),
        }
        if chart_type == "line":
            return LineChart(**common)
        if chart_type == "bar":
            return BarChart(**common)
        return ScatterChart(**common)
    if chart_type == "pie":
        return PieChart(
            title=title,
            label_field=input_.get("label_field", ""),
            value_field=input_.get("value_field", ""),
        )
    if chart_type == "gauge":
        return GaugeChart(
            title=title,
            value_field=input_.get("value_field", ""),
            min=input_.get("min", 0),
            max=input_.get("max", 100),
        )
    raise ValueError(f"Unknown chart_type '{chart_type}' -- must be line, bar, scatter, pie, or gauge")


def _build_panel_suggestion(input_: dict[str, Any]) -> CopilotSuggestion:
    title = input_.get("title", "")
    state = PanelSuggestionState(
        dashboard_id=UUID(input_["dashboard_id"]),
        title=title,
        chart=_build_chart(input_.get("chart_type", ""), title, input_),
        query=Query(sql=input_.get("sql", "")),
        time_range=input_.get("time_range") or "1h",
    )
    return PanelSuggestion(label=f"New panel: {title}", state=state)


def run_suggest_dashboard(project_id: UUID, input_: dict[str, Any]) -> tuple[str, CopilotSuggestion | None]:
    try:
        suggestion = _build_dashboard_suggestion(project_id, input_)
    except ValidationError as exc:
        return (
            f"Couldn't build that dashboard suggestion: {_validation_error_summary(exc)}. "
            "Adjust the fields and try again.",
            None,
        )
    # AttributeError: a `panels` item that isn't an object (e.g. a plain
    # string panel name instead of {title, chart_type, sql, ...}) fails on
    # the first `.get()` call while building it -- without this, that
    # crashed the whole request instead of giving the model a retryable
    # error message, since AttributeError isn't a ValueError/TypeError.
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return f"Couldn't build that dashboard suggestion: {exc}. Adjust the fields and try again.", None

    # Always plural -- DashboardSuggestionState's own validator already
    # requires at least 3 panels, so the singular case can't occur here.
    return (
        f"Drafted a dashboard with {len(suggestion.state.panels)} panels -- mention in "
        "your answer that a draft is ready for review below, and ask if they'd like "
        "any adjustments.",
        suggestion,
    )


def _build_dashboard_suggestion(project_id: UUID, input_: dict[str, Any]) -> CopilotSuggestion:
    variables = [
        Variable(
            name=v["name"],
            label=v["label"],
            table=v["table"],
            value_column=v["value_column"],
            predicate_column=v.get("predicate_column"),
            predicate_variable=v.get("predicate_variable"),
        )
        for v in input_.get("variables", [])
    ]
    panels = [
        DashboardPanelSuggestion(
            title=p.get("title", ""),
            chart=_build_chart(p.get("chart_type", ""), p.get("title", ""), p),
            query=Query(sql=p.get("sql", "")),
            time_range=p.get("time_range") or "1h",
        )
        for p in input_.get("panels", [])
    ]
    name = input_.get("name", "")
    state = DashboardSuggestionState(
        project_id=project_id,
        name=name,
        description=input_.get("description", ""),
        variables=variables,
        panels=panels,
    )
    return DashboardSuggestion(label=f"New dashboard: {name}", state=state)
