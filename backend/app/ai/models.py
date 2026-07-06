from pydantic import BaseModel, Field


class AiVariableHint(BaseModel):
    name: str
    label: str


class SqlGenerationRequest(BaseModel):
    prompt: str
    variables: list[AiVariableHint] = Field(default_factory=list)


class SqlGenerationResponse(BaseModel):
    sql: str
