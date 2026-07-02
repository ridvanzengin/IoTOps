from pydantic import Field

from app.plugin.common import CommonOpts, advanced_field


class TimescaleDBOutputConfig(CommonOpts):
    connection: str = "postgresql://iotops:iotops@timescaledb:5432/iotops"

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
    # statement. No retention policy by default -- that's a data-lifetime
    # decision each user should opt into deliberately, not an implicit
    # default that silently deletes their telemetry.
    create_templates: list[str] = Field(
        default=[
            "CREATE TABLE {{.table}} ({{.columns}});"
            " SELECT create_hypertable('{{.table}}', 'time');"
        ],
        json_schema_extra={"advanced": True},
    )
    add_column_templates: list[str] = Field(
        default=["ALTER TABLE {{.table}} ADD COLUMN IF NOT EXISTS {{.column}}"],
        json_schema_extra={"advanced": True},
    )
    tag_table_create_templates: list[str] = Field(
        default=["CREATE TABLE {{.table}} ({{.columns}})"],
        json_schema_extra={"advanced": True},
    )
    tag_table_add_column_templates: list[str] = Field(
        default=["ALTER TABLE {{.table}} ADD COLUMN IF NOT EXISTS {{.column}}"],
        json_schema_extra={"advanced": True},
    )

    uint64_type: str = advanced_field(default="numeric")
    retry_max_backoff: str = advanced_field(default="15s")
    tag_cache_size: int = advanced_field(default=100000)
    log_level: str = advanced_field(default="warn")
