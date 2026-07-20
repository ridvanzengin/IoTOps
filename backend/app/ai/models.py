from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.automater.models import Condition, ResolveMode, RuleSeverity
from app.dashboard.models import BarChart, Chart, GaugeChart, LineChart, PieChart, Query, ScatterChart
from app.query_rule.models import QueryRuleSchedule


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
        # Chart's own field types don't enforce non-empty axis/field names
        # (a real, in-progress PanelEditor.tsx draft legitimately has
        # those blank before the user finishes it) -- a *suggestion*
        # specifically needs its own completeness check, mirroring
        # AutomaterRuleSuggestionState/QueryRuleSuggestionState's own
        # validators, so an incomplete draft reads as a retryable tool
        # error (see run_suggest_panel) rather than a suggestion card with
        # blank chart fields.
        if not self.query.sql:
            raise ValueError("panel suggestion requires a non-empty sql query")
        if isinstance(self.chart, (LineChart, BarChart, ScatterChart)):
            if not self.chart.x_axis or not self.chart.y_axis:
                raise ValueError("line/bar/scatter panel suggestion requires x_axis and y_axis")
        elif isinstance(self.chart, PieChart):
            if not self.chart.label_field or not self.chart.value_field:
                raise ValueError("pie panel suggestion requires label_field and value_field")
        elif isinstance(self.chart, GaugeChart):
            if not self.chart.value_field:
                raise ValueError("gauge panel suggestion requires value_field")
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


# Discriminated on `kind` -- the frontend derives which route to prefill
# (/automaters/new, /query-rules/new, or /dashboards/{dashboard_id}/
# panels/new) from it rather than the backend sending a route string, so
# that routing decision isn't duplicated in two layers. See
# app/ai/tools.py's SUGGEST_AUTOMATION_TOOL/SUGGEST_PANEL_TOOL and
# AiService._execute_copilot_tool.
CopilotSuggestion = Annotated[
    AutomaterRuleSuggestion | QueryRuleSuggestion | PanelSuggestion, Field(discriminator="kind")
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
