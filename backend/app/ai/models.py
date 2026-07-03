from pydantic import BaseModel


class SqlGenerationRequest(BaseModel):
    prompt: str


class SqlGenerationResponse(BaseModel):
    sql: str
