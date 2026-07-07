from app.ai.models import AiVariableHint
from app.telemetry.models import TelemetryTableSchema


def build_sql_prompt(
    nl_query: str,
    schema: list[TelemetryTableSchema],
    variables: list[AiVariableHint] | None = None,
) -> str:
    schema_lines = [
        f"{table.table}({', '.join(f'{column.name} {column.data_type}' for column in table.columns)})"
        for table in schema
    ]
    schema_block = "\n".join(schema_lines)

    variables_block = ""
    if variables:
        variable_lines = "\n".join(f"${v.name} — {v.label}" for v in variables)
        variables_block = (
            "This dashboard defines the following variables, each holding the value "
            "currently selected by the viewer for that field:\n"
            f"{variable_lines}\n"
            "If the request implies filtering by one of these (e.g. 'for the selected "
            "hive', 'for this project'), reference it directly in the WHERE clause, e.g. "
            "`WHERE hive_id = $hive_id`. Do not wrap these tokens in quotes — substitution "
            "handles quoting automatically (same as $__timeFrom/$__timeTo below). Do not "
            "invent variable names that are not listed here.\n\n"
        )

    return (
        "You are a SQL expert for a PostgreSQL/TimescaleDB database, writing queries "
        "for time-series dashboard panels.\n"
        "Given the following table schema:\n"
        f"{schema_block}\n\n"
        f"{variables_block}"
        "Rules:\n"
        "1. Return ONLY a single SELECT statement. No markdown code fences, no explanations, "
        "no text other than the SQL.\n"
        "2. Do not aggregate (AVG/SUM/MAX/MIN/COUNT/GROUP BY) unless the request explicitly "
        "asks for a summary, average, total, or count. A request like 'show temperature for "
        "the last hour' wants the raw rows, not one aggregated value.\n"
        "3. Always include the table's timestamp column (e.g. `time`) in the SELECT list, "
        "alongside whichever value column(s) the request needs — charts plot against it.\n"
        "4. Always end with `ORDER BY <timestamp column> ASC` so the chart's time axis reads "
        "left-to-right. Never omit this for a time-series query.\n"
        "5. For any time-bounding the request implies (e.g. 'last 15 minutes', 'today', 'last "
        "hour'), do NOT hardcode `NOW() - INTERVAL '...'`. Instead filter on the timestamp "
        "column using the macros `$__timeFrom` and `$__timeTo`, e.g.:\n"
        "   WHERE time >= $__timeFrom AND time <= $__timeTo\n"
        "   These are substituted with the actual bounds from the dashboard's own time range "
        "control at query time, so the panel stays correct when that control changes — the "
        "exact duration named in the request does not need to match the literal SQL.\n\n"
        f"Request: {nl_query}"
    )
