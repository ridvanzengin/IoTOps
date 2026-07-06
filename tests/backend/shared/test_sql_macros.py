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
