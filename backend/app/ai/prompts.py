from app.telemetry.models import TelemetryTableSchema


def build_sql_prompt(nl_query: str, schema: list[TelemetryTableSchema]) -> str:
    schema_lines = [
        f"{table.table}({', '.join(f'{column.name} {column.data_type}' for column in table.columns)})"
        for table in schema
    ]
    schema_block = "\n".join(schema_lines)

    return (
        "You are a SQL expert for a PostgreSQL/TimescaleDB database.\n"
        "Given the following table schema:\n"
        f"{schema_block}\n\n"
        "Return ONLY a single SELECT statement that answers the request below.\n"
        "Do not include markdown code fences, explanations, or any text other than the SQL.\n\n"
        f"Request: {nl_query}"
    )
