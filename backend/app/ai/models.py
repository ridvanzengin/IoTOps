from pydantic import BaseModel, Field


class AiVariableHint(BaseModel):
    name: str
    label: str


class SqlGenerationRequest(BaseModel):
    prompt: str
    variables: list[AiVariableHint] = Field(default_factory=list)


class SqlGenerationResponse(BaseModel):
    sql: str


class QueryRuleSqlGenerationRequest(BaseModel):
    # No `variables` -- Dashboard Variables don't exist in a Query Rule's
    # context, see build_query_rule_sql_prompt's own comment.
    prompt: str
    # Whatever the author has already typed into the Identifiers field, if
    # anything -- passed through as a hint for both table selection and
    # GROUP BY (see build_query_rule_sql_prompt's own comment).
    identifiers: list[str] = Field(default_factory=list)
