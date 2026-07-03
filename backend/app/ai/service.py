import re

import httpx

from app.ai.prompts import build_sql_prompt
from app.shared.exceptions import AiGenerationError
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

    async def generate_sql(self, nl_query: str) -> str:
        schema = await self._telemetry_service.get_schema()
        prompt = build_sql_prompt(nl_query, schema)

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
        validate_select_only_sql(sql)
        return sql
