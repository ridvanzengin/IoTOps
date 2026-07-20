import json
import re
from datetime import datetime, timezone
from uuid import UUID

import anthropic
import httpx

from app.ai.models import AiVariableHint, CopilotMessage, CopilotSuggestion, NeedsContext
from app.ai.prompts import build_copilot_system_prompt, build_query_rule_sql_prompt, build_sql_prompt
from app.ai.tools import (
    COPILOT_TOOLS,
    run_flag_missing_context,
    run_list_existing_panels,
    run_list_existing_rules,
    run_query_occurrences,
    run_query_telemetry,
    run_suggest_automation,
    run_suggest_panel,
)
from app.automater.service import AutomaterService
from app.collector.models import Collector
from app.collector.service import CollectorService
from app.dashboard.service import DashboardService
from app.event.service import EventService
from app.plugin.registry import PluginRegistry
from app.project.service import ProjectService
from app.query_rule.service import QueryRuleService
from app.shared.exceptions import AiGenerationError, EntityNotFoundError, InvalidQueryError
from app.shared.validators import validate_select_only_sql
from app.telemetry.models import TelemetryTableSchema
from app.telemetry.service import TelemetryService

# A suggestion turn can chain several tool calls before a final answer
# (list_existing_rules, one or more query_telemetry checks across
# different columns/tables, suggest_automation, then the text response).
# Live-tested against a real cross-table request ("weight loss + elevated
# sound together") that genuinely needed more round-trips than a
# single-signal one -- 6 wasn't enough and exhausted with a hard error.
# 10 gives real headroom; each iteration is one cheap Haiku call, so the
# cost of a few extra unused iterations on simpler turns is negligible.
MAX_COPILOT_ITERATIONS = 10

# Marks a compact, machine-readable recap of a turn's suggestion, appended
# to the *stored* answer text (not shown in the chat bubble -- see
# CopilotChat.tsx's stripping) so a later refinement turn ("use max
# instead") is grounded on the exact prior proposal once this round-trips
# back as history, not the model's own paraphrased recollection of it. See
# development-plan.md's "One real technical gotcha" note.
_SUGGESTION_CONTEXT_START = "\n\n[[suggestion-context]]"
_SUGGESTION_CONTEXT_END = "[[/suggestion-context]]"

# Lets the model offer a small set of clickable choices (see
# build_copilot_system_prompt's own instructions for the exact format)
# instead of prose-only options the user would have to retype. Parsed out
# of the final answer and returned as CopilotAnswerResponse.quick_replies
# -- unlike the suggestion recap above, these don't need to round-trip as
# history: once clicked, the choice becomes a normal user message, and the
# prose already explains each option well enough for later reference.
_QUICK_REPLIES_RE = re.compile(
    r"\n*\[\[quick-replies\]\]\s*\n(.*?)\n\[\[/quick-replies\]\]\s*", re.DOTALL
)

_CODE_FENCE_RE = re.compile(r"```(?:sql)?", re.IGNORECASE)


def _extract_quick_replies(text: str) -> tuple[str, list[str] | None]:
    matches = list(_QUICK_REPLIES_RE.finditer(text))
    if not matches:
        return text, None
    # Use the *last* block's labels -- the system prompt places the real
    # quick-replies block "at the very end of the answer" (see
    # build_copilot_system_prompt), so if the model also echoes a stale
    # one from earlier history, the final occurrence is the one actually
    # meant for this turn. Strip *every* occurrence from the text either
    # way -- the sibling suggestion-context marker was observed live being
    # echoed a second time by the model (mimicking what it saw in its own
    # prior-turn history), and stripping only the first match there left a
    # raw duplicate visible in the chat bubble. Defending the same way
    # here even though it hasn't been directly observed for this marker.
    labels = [line.strip(" -*\t") for line in matches[-1].group(1).splitlines()]
    labels = [label for label in labels if label]
    stripped = _QUICK_REPLIES_RE.sub("", text).strip()
    return stripped, labels or None


def _strip_markdown_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def _collector_table_names(collectors: list[Collector], registry: PluginRegistry) -> set[str]:
    # Mirrors AutomaterEditor.tsx's own inputTableNames -- TimescaleDB has
    # no per-project table isolation (a "project" is a Mongo-side grouping
    # of Collectors/Automaters, not something the database itself knows
    # about), so which tables "belong" to a project has to be derived from
    # that project's own Collectors' inputs, same as the frontend already
    # does for the DB Schema panel.
    names: set[str] = set()
    for collector in collectors:
        for input_plugin in collector.inputs:
            override = input_plugin.configuration.get("name_override")
            if isinstance(override, str) and override:
                names.add(override)
            else:
                names.add(registry.get(input_plugin.plugin_type).telegraf_name)
    return names


class AiService:
    def __init__(
        self,
        telemetry_service: TelemetryService,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
        event_service: EventService,
        project_service: ProjectService,
        anthropic_client: anthropic.AsyncAnthropic,
        anthropic_model: str,
        automater_service: AutomaterService,
        query_rule_service: QueryRuleService,
        collector_service: CollectorService,
        plugin_registry: PluginRegistry,
        dashboard_service: DashboardService,
    ) -> None:
        self._telemetry_service = telemetry_service
        self._http_client = http_client
        self._base_url = base_url
        self._model = model
        # Below: the Anthropic-backed Co-pilot chat -- a separate model
        # backend from the Ollama-backed SQL generation above, which stays
        # untouched. See answer_copilot_question.
        self._event_service = event_service
        self._project_service = project_service
        self._anthropic_client = anthropic_client
        self._anthropic_model = anthropic_model
        # Only used by the list_existing_rules tool -- see
        # _execute_copilot_tool.
        self._automater_service = automater_service
        self._query_rule_service = query_rule_service
        # Only used to scope the Co-pilot's own schema block to the current
        # project's tables -- see _project_schema.
        self._collector_service = collector_service
        self._plugin_registry = plugin_registry
        # Only used by list_existing_panels and to resolve the optional
        # dashboard_hint below -- see answer_copilot_question.
        self._dashboard_service = dashboard_service

    async def generate_sql(
        self, nl_query: str, variables: list[AiVariableHint] | None = None
    ) -> str:
        schema = await self._telemetry_service.get_schema()
        prompt = build_sql_prompt(nl_query, schema, variables)
        return await self._generate_sql_from_prompt(prompt)

    async def generate_query_rule_sql(
        self, nl_query: str, identifiers: list[str] | None = None
    ) -> str:
        schema = await self._telemetry_service.get_schema()
        prompt = build_query_rule_sql_prompt(nl_query, schema, identifiers)
        return await self._generate_sql_from_prompt(prompt)

    async def _generate_sql_from_prompt(self, prompt: str) -> str:
        try:
            response = await self._http_client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AiGenerationError(str(exc)) from exc

        raw = response.json().get("response", "")
        sql = _strip_markdown_fences(raw)
        try:
            validate_select_only_sql(sql)
        except InvalidQueryError as exc:
            # Distinct from a user hand-writing bad SQL themselves (that's
            # InvalidQueryError, a 400) -- this is the AI failing to return
            # valid SQL at all (an ambiguous/underspecified request most
            # often), a different failure the caller should be told how to
            # fix: be more specific, not "your SQL is wrong".
            raise AiGenerationError(
                "The AI didn't return valid SQL for this request -- try being more specific "
                "(e.g. naming the table, or a column/identifier that pins down what you're "
                "asking about)."
            ) from exc
        return sql

    async def answer_copilot_question(
        self,
        project_id: UUID,
        question: str,
        history: list[CopilotMessage],
        dashboard_id: UUID | None = None,
    ) -> tuple[str, NeedsContext | None, CopilotSuggestion | None, list[str] | None]:
        schema = await self._project_schema(project_id)
        project = await self._project_service.get(project_id)
        now = datetime.now(timezone.utc)
        dashboard_hint = None
        if dashboard_id is not None:
            try:
                dashboard = await self._dashboard_service.get(dashboard_id)
                dashboard_hint = (
                    dashboard.id,
                    dashboard.name,
                    [AiVariableHint(name=v.name, label=v.label) for v in dashboard.variables],
                )
            except EntityNotFoundError:
                pass  # Stale/bad id -- fall through, model just won't get a hint.
        system = build_copilot_system_prompt(
            schema, now=now, ai_context=project.ai_context, dashboard_hint=dashboard_hint
        )
        messages: list[dict] = [
            {"role": h.role, "content": h.content} for h in history[-8:]
        ] + [{"role": "user", "content": question}]
        needs_context: NeedsContext | None = None
        suggestion: CopilotSuggestion | None = None

        for _ in range(MAX_COPILOT_ITERATIONS):
            try:
                response = await self._anthropic_client.messages.create(
                    model=self._anthropic_model,
                    max_tokens=500,
                    system=system,
                    tools=COPILOT_TOOLS,
                    messages=messages,
                )
            except anthropic.APIError as exc:
                raise AiGenerationError(
                    "The AI didn't return an answer -- try rephrasing the question."
                ) from exc

            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if not tool_uses:
                answer = next(
                    (block.text for block in response.content if block.type == "text"), ""
                ).strip()
                if not answer:
                    raise AiGenerationError(
                        "The AI didn't return an answer -- try rephrasing the question."
                    )
                answer, quick_replies = _extract_quick_replies(answer)
                if not answer:
                    if suggestion is None:
                        raise AiGenerationError(
                            "The AI didn't return an answer -- try rephrasing the question."
                        )
                    # The model's entire final answer was just a
                    # quick-replies block with no prose -- rare (the
                    # system prompt asks for prose plus the block), but
                    # shouldn't discard an already-drafted suggestion
                    # from an earlier tool call this same turn.
                    answer = "Here's a draft for you to review."
                if suggestion is not None:
                    recap = json.dumps(suggestion.model_dump(mode="json"))
                    answer = f"{answer}{_SUGGESTION_CONTEXT_START}{recap}{_SUGGESTION_CONTEXT_END}"
                return answer, needs_context, suggestion, quick_replies

            tool_results = []
            for tool_use in tool_uses:
                if tool_use.name == "flag_missing_context":
                    # Keeps the most recent flag if called more than once in
                    # one turn -- a structural signal, not a data source (see
                    # run_flag_missing_context), surfaced on the response
                    # alongside the prose answer.
                    needs_context = NeedsContext(
                        column=tool_use.input.get("column", ""),
                        reason=tool_use.input.get("reason", ""),
                    )
                    result_text = run_flag_missing_context(tool_use.input)
                elif tool_use.name == "suggest_automation":
                    # Same structural-signal shape as flag_missing_context
                    # above -- keeps the most recent draft if called more
                    # than once in one turn (a refinement re-proposing).
                    result_text, new_suggestion = run_suggest_automation(project_id, tool_use.input)
                    if new_suggestion is not None:
                        suggestion = new_suggestion
                elif tool_use.name == "suggest_panel":
                    result_text, new_suggestion = run_suggest_panel(tool_use.input)
                    if new_suggestion is not None:
                        suggestion = new_suggestion
                else:
                    result_text = await self._execute_copilot_tool(
                        tool_use.name, tool_use.input, project_id
                    )
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tool_use.id, "content": result_text}
                )
            messages.append({"role": "user", "content": tool_results})

        raise AiGenerationError(
            "The AI couldn't finish answering within the allotted steps -- try a more "
            "specific question."
        )

    async def _project_schema(self, project_id: UUID) -> list[TelemetryTableSchema]:
        # Regression: the Co-pilot used to get the *global* TimescaleDB
        # schema regardless of which project was selected (every table
        # from every project's Collectors), so it would ask about vehicle
        # or solar-panel theft for a beekeeping project just because those
        # tables happened to exist somewhere else. Scoped to exactly the
        # tables this project's own Collectors write to, same as
        # AutomaterEditor.tsx's own DB Schema panel already does
        # client-side.
        schema = await self._telemetry_service.get_schema()
        collectors = [c for c in await self._collector_service.list() if c.project_id == project_id]
        table_names = _collector_table_names(collectors, self._plugin_registry)
        return [table for table in schema if table.table in table_names]

    async def _execute_copilot_tool(self, name: str, input_: dict, project_id: UUID) -> str:
        if name == "query_occurrences":
            return await run_query_occurrences(self._event_service, project_id, input_)
        if name == "query_telemetry":
            return await run_query_telemetry(self._telemetry_service, input_)
        if name == "list_existing_rules":
            return await run_list_existing_rules(
                self._automater_service, self._query_rule_service, project_id
            )
        if name == "list_existing_panels":
            return await run_list_existing_panels(self._dashboard_service, project_id)
        return f"Unknown tool: {name}"
