from typing import Literal
from uuid import UUID

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


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotQuestionRequest(BaseModel):
    project_id: UUID
    question: str
    # Client resends the transcript each turn -- the server is stateless
    # and re-caps to the last 8 messages regardless of what's sent here
    # (see AiService.answer_copilot_question).
    history: list[CopilotMessage] = Field(default_factory=list)


class NeedsContext(BaseModel):
    column: str
    reason: str


class CopilotAnswerResponse(BaseModel):
    answer: str
    # Set when the model called flag_missing_context during this turn --
    # lets the frontend render an inline "add context" nudge under the
    # answer instead of a generic always-on icon. See app/ai/tools.py's
    # run_flag_missing_context and AiService.answer_copilot_question.
    needs_context: NeedsContext | None = None
