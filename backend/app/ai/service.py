import re

import httpx

from app.ai.models import AiVariableHint
from app.ai.prompts import build_query_rule_sql_prompt, build_sql_prompt
from app.shared.exceptions import AiGenerationError, InvalidQueryError
from app.shared.validators import validate_select_only_sql
from app.telemetry.service import TelemetryService

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
    ) -> None:
        self._telemetry_service = telemetry_service
        self._http_client = http_client
        self._base_url = base_url
        self._model = model

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
