from datetime import datetime, timezone

from app.ai.models import AiVariableHint
from app.ai.prompts import build_copilot_system_prompt, build_query_rule_sql_prompt, build_sql_prompt
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


def test_query_rule_prompt_includes_schema_and_request() -> None:
    prompt = build_query_rule_sql_prompt("stations with sustained high wind", _schema())

    assert "device_metrics(time timestamp with time zone, temperature double precision)" in prompt
    assert "Request: stations with sustained high wind" in prompt


def test_query_rule_prompt_instructs_hardcoded_relative_windows_not_macros() -> None:
    # The opposite instruction of build_sql_prompt's -- there's no
    # dashboard time range to substitute from here, so the prompt
    # explicitly forbids the macros it tells Panel queries to use instead.
    prompt = build_query_rule_sql_prompt("average over the last hour", _schema())

    assert "Do NOT use" in prompt
    assert "$__timeFrom" in prompt
    assert "now() - interval" in prompt


def test_query_rule_prompt_instructs_one_row_per_matching_entity() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "GROUP BY" in prompt
    assert "HAVING" in prompt


def test_query_rule_prompt_encourages_cross_table_conditions() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "Cross-table conditions are expected" in prompt


def test_query_rule_prompt_does_not_require_ordering() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "No ORDER BY is needed" in prompt


def test_query_rule_prompt_forbids_clarifying_questions() -> None:
    prompt = build_query_rule_sql_prompt("average humidity is higher than 60 in last 15 minutes", _schema())

    assert "never ask a clarifying question" in prompt


def test_query_rule_prompt_includes_identifiers_hint_when_provided() -> None:
    prompt = build_query_rule_sql_prompt("average humidity per hive", _schema(), identifiers=["hive_id"])

    assert "hive_id" in prompt
    assert "author's own chosen" in prompt


def test_query_rule_prompt_omits_identifiers_section_when_none_provided() -> None:
    prompt = build_query_rule_sql_prompt("show temperature", _schema())

    assert "author's own chosen" not in prompt


def test_query_rule_prompt_repeats_identifiers_hint_near_the_request() -> None:
    # Live-tested: a single schema-adjacent mention wasn't reliably
    # followed for a fully generic request with no textual hint of the
    # entity -- repeating it right before "Request:" measurably fixed
    # that. See build_query_rule_sql_prompt's own comment.
    prompt = build_query_rule_sql_prompt("average humidity is higher than 60", _schema(), identifiers=["hive_id"])

    assert prompt.count("hive_id") >= 2
    request_index = prompt.rindex("Request:")
    assert "hive_id" in prompt[:request_index]


def test_copilot_system_prompt_includes_schema_and_current_time() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "device_metrics(time timestamp with time zone, temperature double precision)" in prompt
    assert now.isoformat() in prompt


def test_copilot_system_prompt_mentions_both_tools() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "query_occurrences" in prompt
    assert "query_telemetry" in prompt


def test_copilot_system_prompt_instructs_against_fabricating_answers() -> None:
    now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    prompt = build_copilot_system_prompt(_schema(), now=now)

    assert "say so plainly" in prompt
