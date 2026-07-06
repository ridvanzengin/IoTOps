def substitute_macros(sql: str, values: dict[str, str]) -> str:
    for name in sorted(values, key=len, reverse=True):
        sql = sql.replace(f"${name}", values[name])
    return sql
