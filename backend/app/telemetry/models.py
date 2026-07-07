from typing import Any

from pydantic import BaseModel


class TelemetryQueryResult(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]


class TelemetryColumn(BaseModel):
    name: str
    data_type: str
    is_nullable: bool


class TelemetryTableSchema(BaseModel):
    table: str
    columns: list[TelemetryColumn]


class TelemetrySqlQuery(BaseModel):
    sql: str
    limit: int = 1000


class TelemetrySqlQueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
