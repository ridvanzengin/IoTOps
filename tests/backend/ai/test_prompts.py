from app.ai.models import AiVariableHint
from app.ai.prompts import build_sql_prompt
from app.telemetry.models import TelemetryColumn, TelemetryTableSchema


def _schema() -> list[TelemetryTableSchema]:
    return [
        TelemetryTableSchema(
            table="device_metrics",
            columns=[
                TelemetryColumn(name="time", data_type="timestamp with time zone", is_nullable=False),
                TelemetryColumn(name="temperature", data_type="double precision", is_nullable=True),
            ],
        )
    ]


def test_prompt_includes_schema_and_request() -> None:
    prompt = build_sql_prompt("show temperature for the last hour", _schema())

    assert "device_metrics(time timestamp with time zone, temperature double precision)" in prompt
    assert "Request: show temperature for the last hour" in prompt


def test_prompt_instructs_time_range_macros_over_hardcoded_intervals() -> None:
    prompt = build_sql_prompt("show temperature for the last 15 minutes", _schema())

    assert "$__timeFrom" in prompt
    assert "$__timeTo" in prompt
    assert "NOW() - INTERVAL" in prompt


def test_prompt_instructs_no_aggregation_unless_requested() -> None:
    prompt = build_sql_prompt("show temperature", _schema())

    assert "Do not aggregate" in prompt


def test_prompt_instructs_ordering_and_timestamp_column() -> None:
    prompt = build_sql_prompt("show temperature", _schema())

    assert "ORDER BY" in prompt
    assert "timestamp column" in prompt


def test_prompt_includes_variable_hints_when_provided() -> None:
    prompt = build_sql_prompt(
        "show temperature for the selected hive",
        _schema(),
        variables=[AiVariableHint(name="hive_id", label="Hive")],
    )

    assert "$hive_id" in prompt
    assert "Hive" in prompt


def test_prompt_omits_variable_section_when_none_provided() -> None:
    prompt = build_sql_prompt("show temperature", _schema())

    assert "dashboard defines the following variables" not in prompt
