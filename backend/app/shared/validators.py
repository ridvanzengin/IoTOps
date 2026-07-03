import re

from app.shared.exceptions import InvalidQueryError

_SELECT_RE = re.compile(r"^\s*SELECT\s", re.IGNORECASE)


def validate_select_only_sql(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if not _SELECT_RE.match(stripped):
        raise InvalidQueryError(sql)
    if ";" in stripped:
        raise InvalidQueryError(sql)
