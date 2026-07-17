import re

from app.shared.exceptions import InvalidQueryError

# WITH is allowed alongside SELECT so a read-only CTE (e.g. a window
# function comparing a reading to the previous one, as AI-suggested Query
# Rules genuinely need) isn't rejected outright.
_SELECT_RE = re.compile(r"^\s*(WITH|SELECT)\s", re.IGNORECASE)

# Postgres only allows INSERT/UPDATE/DELETE as a *named CTE* (`WITH x AS
# (DELETE FROM t RETURNING *) SELECT * FROM x`), never as a plain
# FROM-subquery -- so rejecting anything not starting with SELECT used to
# make a data-modifying CTE structurally impossible for free. Allowing
# WITH above reopens that door, so it has to be closed explicitly here
# instead. \b word boundaries avoid false positives on identifiers that
# merely contain one of these as a substring (e.g. `created_at`,
# `delete_flag` -- `_` is a word character, so there's no boundary
# between "delete" and "_flag"). RECURSIVE is included too: WITH RECURSIVE
# is syntactically a read-only CTE, but an unbounded recursive CTE run
# through the interactive Panel Builder SQL path (which has no query
# timeout, unlike the AI Co-pilot's own query_telemetry) is a real
# resource-exhaustion risk against the shared TimescaleDB connection pool.
_FORBIDDEN_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|MERGE|CALL|COPY|VACUUM|"
    r"REINDEX|EXECUTE|LOCK|REFRESH|RECURSIVE)\b",
    re.IGNORECASE,
)

# Matches a single-quoted SQL string literal, including a doubled `''`
# escaped quote inside it (the standard SQL escape for a literal quote
# character). Used to blank out literal *data* before running the
# forbidden-keyword scan, so a legitimate value like `WHERE action =
# 'delete'` isn't rejected just because the word "delete" appears as data,
# not as an actual SQL keyword.
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def validate_select_only_sql(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if not _SELECT_RE.match(stripped):
        raise InvalidQueryError(sql)
    if ";" in stripped:
        raise InvalidQueryError(sql)
    without_literals = _STRING_LITERAL_RE.sub("''", stripped)
    if _FORBIDDEN_KEYWORDS_RE.search(without_literals):
        raise InvalidQueryError(sql)
