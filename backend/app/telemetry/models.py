from typing import Any

from pydantic import BaseModel


class TelemetryQueryResult(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
