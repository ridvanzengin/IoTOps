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


def build_query_rule_sql_prompt(
    nl_query: str,
    schema: list[TelemetryTableSchema],
    identifiers: list[str] | None = None,
) -> str:
    # Deliberately not build_sql_prompt with a flag -- the two frame the
    # query in genuinely opposite ways (one row per matching entity vs.
    # one row per raw reading; a fixed relative window hardcoded in the
    # SQL vs. a macro substituted from a dashboard's own time range that
    # doesn't exist here), not a couple of conditional lines. See
    # iotops-workspace/ROADMAP.md's "Query Rules" note.
    schema_lines = [
        f"{table.table}({', '.join(f'{column.name} {column.data_type}' for column in table.columns)})"
        for table in schema
    ]
    schema_block = "\n".join(schema_lines)

    # Repeated twice deliberately (once schema-adjacent, once right before
    # the request) -- live-tested against the real local model: a single
    # mention near the schema was reliably followed once the request text
    # itself already hinted at the entity (e.g. "... per hive"), but was
    # just as often ignored on a fully generic request with no such
    # wording, where the model defaulted to whichever table's column names
    # happened to read closest to the request. Recency plus repetition
    # measurably fixed the fully-generic case in testing; a single
    # mention did not.
    identifiers_line = ""
    if identifiers:
        identifiers_line = (
            "REQUIRED: query whichever table actually contains the column(s) "
            f"{', '.join(identifiers)} -- these are the author's own chosen "
            "identifier(s) for one matching entity, and take priority over any "
            "other table that merely has a similarly-named value column, even if "
            "the request's wording alone doesn't name that entity. GROUP BY "
            "exactly these columns.\n"
        )

    return (
        "You are a SQL expert for a PostgreSQL/TimescaleDB database, writing a query for "
        "a scheduled monitoring rule -- not a dashboard chart. This query re-runs "
        "unattended on its own fixed schedule (e.g. every 5 minutes), completely "
        "independent of any dashboard or user-selected time range.\n"
        "Given the following table schema:\n"
        f"{schema_block}\n\n"
        f"{identifiers_line}"
        "Rules:\n"
        "1. Return ONLY a single SELECT statement. No markdown code fences, no explanations, "
        "no text other than the SQL.\n"
        "2. The result set IS the current set of entities the rule considers matching -- "
        "return exactly one row per matching entity (e.g. per device/station/machine), "
        "never one row per raw reading. Use GROUP BY on whichever column identifies the "
        "entity, and HAVING for any aggregate threshold, e.g. `HAVING AVG(temperature) > "
        "60`.\n"
        "3. For any time window the request implies (e.g. 'over the last hour', 'in the "
        "last 6 hours'), hardcode it directly in the WHERE clause as `time > now() - "
        "interval '1 hour'`. Do NOT use `$__timeFrom`/`$__timeTo` or any other macro or "
        "placeholder -- there is no dashboard time range here, only this query's own fixed, "
        "relative window, evaluated fresh every time it runs.\n"
        "4. Cross-table conditions are expected and encouraged when the request needs them "
        "-- join tables, or combine separate subqueries with AND/OR -- do not artificially "
        "restrict the query to one table if the request genuinely needs more than one.\n"
        "5. No ORDER BY is needed -- this result set is evaluated for membership (which "
        "entities are present), not displayed as an ordered chart.\n"
        "6. If more than one table could plausibly answer the request, pick the single "
        "most relevant one yourself based on its column names and the identifiers above "
        "if given -- never ask a clarifying question or explain your reasoning in prose. "
        "Return SQL only, even if you have to guess.\n\n"
        f"{identifiers_line}"
        f"Request: {nl_query}"
    )
