from typing import Any

from pydantic import BaseModel, Field

_ADVANCED = {"json_schema_extra": {"advanced": True}}


class CommonOpts(BaseModel):
    """Options Telegraf accepts on every input/processor/output plugin."""

    name_override: str | None = Field(default=None, **_ADVANCED)
    name_prefix: str | None = Field(default=None, **_ADVANCED)
    name_suffix: str | None = Field(default=None, **_ADVANCED)
    alias: str | None = Field(default=None, **_ADVANCED)

    namepass: list[str] = Field(default=[], **_ADVANCED)
    namedrop: list[str] = Field(default=[], **_ADVANCED)
    fieldpass: list[str] = Field(default=[], **_ADVANCED)
    fielddrop: list[str] = Field(default=[], **_ADVANCED)

    tagpass: dict[str, list[str]] = Field(default={}, **_ADVANCED)
    tagdrop: dict[str, list[str]] = Field(default={}, **_ADVANCED)
    taginclude: list[str] = Field(default=[], **_ADVANCED)
    tagexclude: list[str] = Field(default=[], **_ADVANCED)

    interval: str | None = Field(default=None, **_ADVANCED)
    measurement_prefix: str | None = Field(default=None, **_ADVANCED)


def advanced_field(default: Any = None, **kwargs: Any) -> Any:
    extra = kwargs.pop("json_schema_extra", {})
    return Field(default=default, json_schema_extra={**extra, "advanced": True}, **kwargs)
