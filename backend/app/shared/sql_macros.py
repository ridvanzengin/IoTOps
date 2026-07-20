import re


def substitute_macros(sql: str, values: dict[str, str]) -> str:
    for name in sorted(values, key=len, reverse=True):
        # Every substituted value here is already a fully-quoted SQL
        # string literal (see DashboardService._format_variable_value and
        # its own $__timeFrom/$__timeTo formatting) -- if the SQL itself
        # also wraps the token in quotes (`WHERE machine_id = '$machine_id'`,
        # a mistake both hand-typed SQL and AI-generated SQL have been
        # observed making despite prompt guidance saying not to), the
        # result double-quotes into invalid SQL: `''press-03''`, a bare
        # `press-03` sitting between two empty-string literals, which
        # Postgres rejects as a syntax error at the bare identifier, not
        # at the quotes themselves. Strip a redundant surrounding quote
        # pair around the token first so either style substitutes correctly.
        sql = re.sub(rf"'\${re.escape(name)}'", f"${name}", sql)
        sql = sql.replace(f"${name}", values[name])
    return sql
