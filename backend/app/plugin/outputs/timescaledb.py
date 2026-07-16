from pydantic import Field

from app.config import settings
from app.plugin.common import CommonOpts, advanced_field


def _default_create_templates() -> list[str]:
    return [
        "CREATE TABLE {{.table}} ({{.columns}});"
        " SELECT create_hypertable('{{.table}}', 'time');"
        " SELECT add_retention_policy('{{.table}}', INTERVAL '"
        + str(settings.retention_days)
        + " days', if_not_exists => true);"
    ]


class TimescaleDBOutputConfig(CommonOpts):
    connection: str = Field(default_factory=lambda: settings.timescale_uri)

    pgr_schema: str = advanced_field(default="public", alias="schema")
    tags_as_foreign_keys: bool = advanced_field(default=False)
    tag_table_suffix: str = advanced_field(default="_tag")
    foreign_tag_constraint: bool = advanced_field(default=False)
    tags_as_jsonb: bool = advanced_field(default=False)
    fields_as_jsonb: bool = advanced_field(default=False)
    timestamp_column_name: str = advanced_field(default="time")
    timestamp_column_type: str = advanced_field(default="timestamp with time zone")

    # Telegraf refuses to auto-create/alter tables if these are explicitly
    # empty (empty means "disabled", not "use my built-in default"), so we
    # mirror Telegraf's own default templates here rather than [], and turn
    # every auto-created table into a TimescaleDB hypertable in the same
    # statement. Also applies a retention policy (settings.retention_days,
    # 14 days by default) unconditionally -- not tied to demo mode, just a
    # sane out-of-the-box default so telemetry doesn't grow unbounded. A
    # user who wants unlimited retention can override this field (it's
    # advanced/exposed in the Collector/Automater UI) or raise
    # RETENTION_DAYS.
    create_templates: list[str] = Field(
        default_factory=_default_create_templates,
        json_schema_extra={"advanced": True},
    )
    # Telegraf's postgresql output template context exposes the missing
    # columns as `.columns` (a list), not a singular `.column` -- rendering
    # it bare would print Go's default slice format, not SQL, so multiple
    # missing columns need the `join` filter to repeat the
    # "ADD COLUMN IF NOT EXISTS" keyword between them. Verified against the
    # actual telegraf:1.32-alpine plugin docs after this silently dropped
    # every schema-evolution ALTER (new columns from later-arriving fields
    # were "omitted", never added) with the previous `{{.column}}` template.
    add_column_templates: list[str] = Field(
        default=[
            "ALTER TABLE {{.table}} ADD COLUMN IF NOT EXISTS"
            ' {{.columns|join ", ADD COLUMN IF NOT EXISTS "}}'
        ],
        json_schema_extra={"advanced": True},
    )
    tag_table_create_templates: list[str] = Field(
        default=["CREATE TABLE {{.table}} ({{.columns}})"],
        json_schema_extra={"advanced": True},
    )
    tag_table_add_column_templates: list[str] = Field(
        default=[
            "ALTER TABLE {{.table}} ADD COLUMN IF NOT EXISTS"
            ' {{.columns|join ", ADD COLUMN IF NOT EXISTS "}}'
        ],
        json_schema_extra={"advanced": True},
    )

    uint64_type: str = advanced_field(default="numeric")
    retry_max_backoff: str = advanced_field(default="15s")
    tag_cache_size: int = advanced_field(default=100000)
    log_level: str = advanced_field(default="warn")
