import pytest

from app.shared.exceptions import InvalidQueryError
from app.shared.validators import validate_select_only_sql


def test_accepts_plain_select() -> None:
    validate_select_only_sql("SELECT * FROM device_metrics")


def test_accepts_select_with_trailing_semicolon() -> None:
    validate_select_only_sql("SELECT * FROM device_metrics;")


def test_accepts_cte_query() -> None:
    # Regression: a real AI-suggested Query Rule used a CTE (window
    # function comparing a reading to the previous one) and was rejected
    # outright since the old validator only accepted a literal `SELECT`
    # prefix -- CTEs are a legitimate, common way to express this kind of
    # read-only comparison.
    sql = (
        "WITH recent AS (SELECT hive_id, weight_kg, "
        "LAG(weight_kg) OVER (PARTITION BY hive_id ORDER BY time) AS prev "
        "FROM hive_weight) "
        "SELECT hive_id FROM recent WHERE weight_kg - prev < -200"
    )

    validate_select_only_sql(sql)


def test_accepts_columns_that_merely_contain_forbidden_words() -> None:
    # `_` is a word character, so `created_at`/`delete_flag` never match
    # \bCREATE\b / \bDELETE\b -- these must not be rejected.
    validate_select_only_sql("SELECT created_at, delete_flag FROM device_metrics")


def test_rejects_non_select_statement() -> None:
    with pytest.raises(InvalidQueryError):
        validate_select_only_sql("DELETE FROM device_metrics")


def test_rejects_multiple_statements() -> None:
    with pytest.raises(InvalidQueryError):
        validate_select_only_sql("SELECT 1; DROP TABLE device_metrics;")


@pytest.mark.parametrize(
    "keyword",
    ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "EXECUTE"],
)
def test_rejects_data_modifying_cte(keyword: str) -> None:
    # The one attack a bare `^SELECT` prefix check used to block "for
    # free" by rejecting WITH outright: Postgres only allows INSERT/
    # UPDATE/DELETE as a named CTE, never as a plain FROM-subquery, so
    # allowing WITH without this check would reopen that door.
    sql = f"WITH x AS ({keyword} FROM device_metrics RETURNING *) SELECT * FROM x"

    with pytest.raises(InvalidQueryError):
        validate_select_only_sql(sql)


def test_rejects_unbounded_recursive_cte() -> None:
    # WITH RECURSIVE is syntactically read-only, but run through the
    # Panel Builder's ad hoc SQL path (which has no query timeout, unlike
    # the AI Co-pilot's own bounded query tool), an unbounded recursive
    # CTE is a real resource-exhaustion risk against the shared
    # TimescaleDB connection pool.
    sql = "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t) SELECT n FROM t"

    with pytest.raises(InvalidQueryError):
        validate_select_only_sql(sql)


@pytest.mark.parametrize(
    "keyword",
    ["delete", "insert", "call", "lock", "create"],
)
def test_accepts_forbidden_words_inside_string_literals(keyword: str) -> None:
    # Regression: the keyword blocklist used to scan the whole SQL text
    # including quoted data values, so a completely ordinary query like
    # `WHERE action = 'delete'` was rejected even though it contains no
    # DELETE statement at all -- only real SQL syntax should trip this.
    sql = f"SELECT * FROM audit_log WHERE action = '{keyword}'"

    validate_select_only_sql(sql)


def test_accepts_string_literal_with_escaped_quote() -> None:
    # `''` is the standard SQL escape for a literal quote character inside
    # a string -- the literal-stripping regex must consume the whole
    # value, not stop at the first `'` it sees.
    sql = "SELECT * FROM notes WHERE message = 'it''s a delete test'"

    validate_select_only_sql(sql)


def test_still_rejects_delete_used_as_real_sql_outside_a_literal() -> None:
    # Stripping string literals must not accidentally blind the check to
    # a real DML statement that happens to sit right next to a string.
    with pytest.raises(InvalidQueryError):
        validate_select_only_sql("DELETE FROM device_metrics WHERE id = 'x'")
