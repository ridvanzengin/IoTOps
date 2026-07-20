from app.shared.sql_macros import substitute_macros


def test_substitutes_single_placeholder() -> None:
    result = substitute_macros("SELECT * FROM t WHERE hive = $hive", {"hive": "'A'"})

    assert result == "SELECT * FROM t WHERE hive = 'A'"


def test_longest_names_substituted_first_to_avoid_prefix_clobbering() -> None:
    sql = "SELECT * FROM t WHERE hive = $hive AND hive_id = $hive_id"

    result = substitute_macros(sql, {"hive": "'A'", "hive_id": "42"})

    assert result == "SELECT * FROM t WHERE hive = 'A' AND hive_id = 42"


def test_leaves_unreferenced_sql_untouched() -> None:
    sql = "SELECT * FROM t"

    result = substitute_macros(sql, {"hive": "'A'"})

    assert result == sql


def test_ignores_values_with_no_matching_token() -> None:
    sql = "SELECT * FROM t WHERE hive = $hive"

    result = substitute_macros(sql, {"hive": "'A'", "unused": "'B'"})

    assert result == "SELECT * FROM t WHERE hive = 'A'"


def test_strips_a_redundant_quote_pair_already_wrapping_the_token() -> None:
    # Regression: live-tested against Gemini -- a generated panel wrote
    # `WHERE machine_id = '$machine_id'`, quoting the token itself even
    # though the substituted value is already a quoted string literal.
    # Without stripping the redundant pair first, this double-quotes into
    # `''press-03''` -- an empty string literal, a bare `press-03`
    # (parsed as an identifier minus a number), and another empty string
    # literal, which Postgres rejects with "syntax error at or near
    # 'press'" -- not even a hint that quoting was the actual problem.
    sql = "SELECT * FROM machine_telemetry WHERE machine_id = '$machine_id'"

    result = substitute_macros(sql, {"machine_id": "'press-03'"})

    assert result == "SELECT * FROM machine_telemetry WHERE machine_id = 'press-03'"


def test_strips_redundant_quotes_around_time_range_macros_too() -> None:
    sql = "SELECT * FROM t WHERE time >= '$__timeFrom' AND time <= '$__timeTo'"

    result = substitute_macros(
        sql, {"__timeFrom": "'2026-01-01T00:00:00+00:00'", "__timeTo": "'2026-01-02T00:00:00+00:00'"}
    )

    assert result == (
        "SELECT * FROM t WHERE time >= '2026-01-01T00:00:00+00:00' "
        "AND time <= '2026-01-02T00:00:00+00:00'"
    )
