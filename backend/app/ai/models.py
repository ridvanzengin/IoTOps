import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.automater.models import Condition, ResolveMode, RuleSeverity
from app.dashboard.models import (
    BarChart,
    Chart,
    GaugeChart,
    LineChart,
    PieChart,
    Query,
    ScatterChart,
    Variable,
    validate_variables,
)
from app.query_rule.models import QueryRuleSchedule


def _validate_chart_completeness(chart: Chart) -> None:
    # Shared by PanelSuggestionState and DashboardSuggestionState -- a
    # *suggestion* must have every field a real chart needs, unlike an
    # in-progress PanelEditor.tsx draft, which legitimately has blank
    # axis/field names before the user finishes it (see PanelSuggestionState's
    # own comment). Raising here means an incomplete draft reads as a
    # retryable tool error (see run_suggest_panel/run_suggest_dashboard),
    # not a suggestion card with blank chart fields.
    if isinstance(chart, (LineChart, BarChart, ScatterChart)):
        if not chart.x_axis or not chart.y_axis:
            raise ValueError("line/bar/scatter panel suggestion requires x_axis and y_axis")
    elif isinstance(chart, PieChart):
        if not chart.label_field or not chart.value_field:
            raise ValueError("pie panel suggestion requires label_field and value_field")
    elif isinstance(chart, GaugeChart):
        if not chart.value_field:
            raise ValueError("gauge panel suggestion requires value_field")


# Matches a $token the same way substitute_macros (app/shared/sql_macros.py)
# does when resolving one -- used here in the opposite direction, to find
# which variable names a panel's SQL *references* rather than to resolve
# them, so DashboardSuggestionState can catch a panel referencing a
# variable that was never declared in the same suggest_dashboard call.
# Live-tested: the model described "a Machine filter variable" in its own
# prose and wrote every panel's SQL against $machine_id, but the actual
# tool call's `variables` list was empty -- nothing caught the mismatch,
# so the dashboard was created with panels silently querying a macro that
# was never substituted (Postgres saw the literal text "$machine_id" in
# the WHERE clause), and every panel came back empty.
_VARIABLE_TOKEN_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_TIME_RANGE_MACROS = {"__timeFrom", "__timeTo"}


def _referenced_variable_names(sql: str) -> set[str]:
    return {name for name in _VARIABLE_TOKEN_RE.findall(sql) if name not in _TIME_RANGE_MACROS}


class AiVariableHint(BaseModel):
    name: str
    label: str


class SqlGenerationRequest(BaseModel):
    prompt: str
    variables: list[AiVariableHint] = Field(default_factory=list)


class SqlGenerationResponse(BaseModel):
    sql: str


class QueryRuleSqlGenerationRequest(BaseModel):
    # No `variables` -- Dashboard Variables don't exist in a Query Rule's
    # context, see build_query_rule_sql_prompt's own comment.
    prompt: str
    # Whatever the author has already typed into the Identifiers field, if
    # anything -- passed through as a hint for both table selection and
    # GROUP BY (see build_query_rule_sql_prompt's own comment).
    identifiers: list[str] = Field(default_factory=list)


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotQuestionRequest(BaseModel):
    project_id: UUID
    question: str
    # Client resends the transcript each turn -- the server is stateless
    # and re-caps to the last 8 messages regardless of what's sent here
    # (see AiService.answer_copilot_question).
    history: list[CopilotMessage] = Field(default_factory=list)
    # Set when the Co-pilot was opened from inside an already-open
    # dashboard (e.g. its "Suggest a panel" menu item) -- lets the system
    # prompt hint the model with that dashboard's id/name/variables so
    # suggest_panel doesn't need a round-trip through list_existing_panels
    # to discover it. None for every other entry point; suggest_panel
    # still works without it, the model just has to look it up itself.
    dashboard_id: UUID | None = None


class NeedsContext(BaseModel):
    column: str
    reason: str


class AutomaterRuleSuggestionState(BaseModel):
    # Mirrors CreateRuleRequest/RulePayload's shape closely enough to
    # submit, minus automater_id/automater_name/collector_id -- which
    # existing Automater or Collector to attach to is a deployment
    # decision the model has no basis for, so AutomaterEditor.tsx leaves
    # those to the user rather than prefilling them.
    project_id: UUID
    rule_name: str
    category: str = ""
    event_type: str = ""
    severity: RuleSeverity
    message: str = ""
    resolve_mode: ResolveMode = ResolveMode.AUTO
    identifiers: list[str] = Field(default_factory=list)
    table: str
    conditions: list[Condition]

    @model_validator(mode="after")
    def _validate_complete(self) -> "AutomaterRuleSuggestionState":
        # Mirrors Rule's own "must contain at least one condition"
        # invariant (app.automater.models.Rule) -- an empty table/
        # conditions means suggest_automation was called with an
        # incomplete draft, which should read as an error the model can
        # retry from (see run_suggest_automation), not a suggestion card
        # for nothing.
        if not self.table:
            raise ValueError("automater_rule suggestion requires a non-empty table")
        if not self.conditions:
            raise ValueError("automater_rule suggestion requires at least one condition")
        return self


class QueryRuleSuggestionState(BaseModel):
    project_id: UUID
    name: str
    category: str = ""
    event_type: str = ""
    severity: RuleSeverity
    message: str = ""
    resolve_mode: ResolveMode = ResolveMode.AUTO
    identifiers: list[str] = Field(default_factory=list)
    sql: str
    schedule: QueryRuleSchedule

    @model_validator(mode="after")
    def _validate_complete(self) -> "QueryRuleSuggestionState":
        if not self.sql:
            raise ValueError("query_rule suggestion requires a non-empty sql")
        return self


class PanelSuggestionState(BaseModel):
    # Mirrors PanelInput minus `position` (PanelBuilder.tsx's own
    # findFreePosition already auto-places new panels -- no reason to make
    # the model guess a grid slot) and `event_rule_ids` (not something the
    # model should propose). Adds `dashboard_id`, which PanelInput doesn't
    # need (panels are always addressed via their parent Dashboard's own
    # id in the URL) but a suggestion does, since -- unlike a Rule
    # suggestion, where which Automater/Collector to attach to is left to
    # the user -- a panel has nowhere to go without a target dashboard.
    dashboard_id: UUID
    title: str
    chart: Chart
    query: Query
    time_range: str = "1h"

    @model_validator(mode="after")
    def _validate_complete(self) -> "PanelSuggestionState":
        if not self.query.sql:
            raise ValueError("panel suggestion requires a non-empty sql query")
        _validate_chart_completeness(self.chart)
        return self


class DashboardPanelSuggestion(BaseModel):
    # Same shape as PanelSuggestionState minus dashboard_id -- nested
    # inside DashboardSuggestionState, so the dashboard it belongs to is
    # implicit (it doesn't exist yet at proposal time, unlike a standalone
    # panel suggestion which always targets a real, already-existing
    # dashboard).
    title: str
    chart: Chart
    query: Query
    time_range: str = "1h"


class DashboardSuggestionState(BaseModel):
    project_id: UUID
    name: str
    description: str = ""
    variables: list[Variable] = Field(default_factory=list)
    panels: list[DashboardPanelSuggestion]

    @model_validator(mode="after")
    def _validate_complete(self) -> "DashboardSuggestionState":
        if len(self.panels) < 3:
            # A single- or two-panel "dashboard" defeats the entire point
            # of this tool over suggest_panel -- live-tested repeatedly:
            # the model settling for 1-2 panels when the data supported
            # more, and separately (see MAX_COPILOT_ITERATIONS handling)
            # an iteration-budget exhaustion surfacing a partial draft as
            # if it were final. suggest_panel exists for the "just one or
            # two things worth monitoring" case; a suggest_dashboard call
            # should never settle for fewer than 3.
            raise ValueError(
                "dashboard suggestion requires at least 3 panels -- if there's only one or "
                "two things worth monitoring, use suggest_panel instead"
            )
        declared_names = {v.name for v in self.variables}
        used_names: set[str] = set()
        for index, panel in enumerate(self.panels):
            # Identify the offending panel by position + title, not just
            # the bare invariant text -- a bare ValueError raised from
            # inside a model_validator over a list gets wrapped by
            # Pydantic with a dump of the *entire* DashboardSuggestionState
            # (every panel, every variable, as repr'd Python objects) as
            # "input_value", not just the one bad panel. For a 5-panel
            # dashboard that's a wall of noise the model has to parse to
            # find the one relevant fact -- live-tested to actually cause
            # the model to give up on retrying suggest_dashboard and
            # describe the dashboard in prose instead (no card at all).
            # Naming the panel up front keeps the actionable part of the
            # message short regardless of how much noise Pydantic appends.
            try:
                if not panel.query.sql:
                    raise ValueError("requires a non-empty sql query")
                _validate_chart_completeness(panel.chart)
                # A panel can only filter by a variable this same call
                # actually declares -- see _referenced_variable_names'
                # own comment for the live-tested failure this catches
                # (SQL referencing $machine_id with an empty variables
                # list, so the token was never substituted and every
                # panel came back with no data).
                referenced = _referenced_variable_names(panel.query.sql)
                undeclared = referenced - declared_names
                if undeclared:
                    names = ", ".join(f"${name}" for name in sorted(undeclared))
                    raise ValueError(
                        f"references undeclared variable(s) {names} -- either add them to "
                        "variables or remove the reference from the sql"
                    )
                used_names |= referenced
            except ValueError as exc:
                raise ValueError(f"panel {index} ('{panel.title}') {exc}") from exc
        # A chain parent (e.g. Apiary, predicate_variable for Hive) counts
        # as used even without its own direct $apiary reference in any
        # panel's sql, as long as the variable it narrows is used -- it's
        # still doing real work narrowing the child's own options on the
        # dashboard, not decoration. Walk the chain from each used variable
        # up through predicate_variable to propagate "used" to its
        # ancestors.
        by_name = {v.name: v for v in self.variables}
        for name in list(used_names):
            current = by_name.get(name)
            while current is not None and current.predicate_variable:
                used_names.add(current.predicate_variable)
                current = by_name.get(current.predicate_variable)
        unused_names = declared_names - used_names
        if unused_names:
            # The mirror-image bug of the undeclared-variable check above,
            # live-tested just as directly: the model declared a Panel
            # Array variable "for later" but every proposed panel was a
            # flat fleet-wide overview that never actually filtered or
            # grouped by it -- a purely decorative variable the user has
            # no way to tell is meant to do anything. A declared variable
            # earns its place by being exercised by at least one panel in
            # THIS SAME call (a filtered panel, or a per-entity comparison
            # panel grouping by the same column) -- it's not a "just in
            # case, for later" placeholder.
            names = ", ".join(f"${name}" for name in sorted(unused_names))
            raise ValueError(
                f"declares variable(s) {names} that no panel actually uses -- either add a "
                "panel that filters or groups by at least one of them, or remove them from "
                "variables"
            )
        # Reuses the same chain-order invariant DashboardInput itself
        # enforces (a predicate_variable must reference an earlier name in
        # this same list) -- catching a broken chain here reads as a
        # retryable tool error the model can fix, not a 422 from
        # POST /api/dashboard after the user already clicked "Create".
        validate_variables(self.variables)
        return self


class AutomaterRuleSuggestion(BaseModel):
    kind: Literal["automater_rule"] = "automater_rule"
    label: str
    state: AutomaterRuleSuggestionState


class QueryRuleSuggestion(BaseModel):
    kind: Literal["query_rule"] = "query_rule"
    label: str
    state: QueryRuleSuggestionState


class PanelSuggestion(BaseModel):
    kind: Literal["panel"] = "panel"
    label: str
    state: PanelSuggestionState


class DashboardSuggestion(BaseModel):
    kind: Literal["dashboard"] = "dashboard"
    label: str
    state: DashboardSuggestionState


# Discriminated on `kind` -- the frontend derives which route/action to
# take (/automaters/new, /query-rules/new, /dashboards/{dashboard_id}/
# panels/new, or -- for "dashboard" -- a direct create-then-navigate
# rather than a route at all, see CopilotChat.tsx's suggestion-card
# handling) from it rather than the backend sending a route string, so
# that decision isn't duplicated in two layers. See app/ai/tools.py's
# SUGGEST_AUTOMATION_TOOL/SUGGEST_PANEL_TOOL/SUGGEST_DASHBOARD_TOOL and
# AiService._execute_copilot_tool.
CopilotSuggestion = Annotated[
    AutomaterRuleSuggestion | QueryRuleSuggestion | PanelSuggestion | DashboardSuggestion,
    Field(discriminator="kind"),
]


class CopilotAnswerResponse(BaseModel):
    answer: str
    # Set when the model called flag_missing_context during this turn --
    # lets the frontend render an inline "add context" nudge under the
    # answer instead of a generic always-on icon. See app/ai/tools.py's
    # run_flag_missing_context and AiService.answer_copilot_question.
    needs_context: NeedsContext | None = None
    # Set when the model called suggest_automation during this turn --
    # the frontend renders this as a link card into the relevant builder,
    # prefilled but never auto-created.
    suggestion: CopilotSuggestion | None = None
    # Set when the model ended its answer with a quick-replies block (see
    # build_copilot_system_prompt) -- short, clickable option labels the
    # frontend renders as chips; clicking one sends it as the next
    # question, same as typing it. Parsed out of `answer` server-side, see
    # AiService._extract_quick_replies.
    quick_replies: list[str] | None = None
