import re
from datetime import datetime, timezone
from uuid import UUID

import anthropic
import httpx

from app.ai.models import AiVariableHint, CopilotMessage
from app.ai.prompts import build_copilot_system_prompt, build_query_rule_sql_prompt, build_sql_prompt
from app.ai.tools import COPILOT_TOOLS, run_query_occurrences, run_query_telemetry
from app.event.service import EventService
from app.shared.exceptions import AiGenerationError, InvalidQueryError
from app.shared.validators import validate_select_only_sql
from app.telemetry.service import TelemetryService

MAX_COPILOT_ITERATIONS = 4

_CODE_FENCE_RE = re.compile(r"```(?:sql)?", re.IGNORECASE)


def _strip_markdown_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


class AiService:
    def __init__(
        self,
        telemetry_service: TelemetryService,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
        event_service: EventService,
        anthropic_client: anthropic.AsyncAnthropic,
        anthropic_model: str,
    ) -> None:
        self._telemetry_service = telemetry_service
        self._http_client = http_client
        self._base_url = base_url
        self._model = model
        # Below: the Anthropic-backed Co-pilot chat -- a separate model
        # backend from the Ollama-backed SQL generation above, which stays
        # untouched. See answer_copilot_question.
        self._event_service = event_service
        self._anthropic_client = anthropic_client
        self._anthropic_model = anthropic_model

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
        self, project_id: UUID, question: str, history: list[CopilotMessage]
    ) -> str:
        schema = await self._telemetry_service.get_schema()
        now = datetime.now(timezone.utc)
        system = build_copilot_system_prompt(schema, now=now)
        messages: list[dict] = [
            {"role": h.role, "content": h.content} for h in history[-8:]
        ] + [{"role": "user", "content": question}]

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
                return answer

            tool_results = []
            for tool_use in tool_uses:
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

    async def _execute_copilot_tool(self, name: str, input_: dict, project_id: UUID) -> str:
        if name == "query_occurrences":
            return await run_query_occurrences(self._event_service, project_id, input_)
        if name == "query_telemetry":
            return await run_query_telemetry(self._telemetry_service, input_)
        return f"Unknown tool: {name}"
