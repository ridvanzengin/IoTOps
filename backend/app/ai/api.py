from fastapi import APIRouter, Depends

from app.ai.models import (
    CopilotAnswerResponse,
    CopilotQuestionRequest,
    QueryRuleSqlGenerationRequest,
    SqlGenerationRequest,
    SqlGenerationResponse,
)
from app.ai.service import AiService
from app.dependencies import get_ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

# No block_in_demo_mode gate here, unlike every mutating route elsewhere --
# these run for real in the public demo now that the AI backend defaults to
# Gemini's free tier (see Settings.ai_provider), not a paid Anthropic key
# that public traffic could burn through. AiService itself (constructed
# with demo=settings.demo -- see get_ai_service) degrades to a friendly
# "AI features are limited in this demo" message if the free tier gets
# rate-limited or is otherwise unreachable, rather than failing outright.


@router.post("/sql", response_model=SqlGenerationResponse)
async def generate_sql(
    payload: SqlGenerationRequest,
    service: AiService = Depends(get_ai_service),
) -> SqlGenerationResponse:
    sql = await service.generate_sql(payload.prompt, payload.variables)
    return SqlGenerationResponse(sql=sql)


@router.post("/query-rule-sql", response_model=SqlGenerationResponse)
async def generate_query_rule_sql(
    payload: QueryRuleSqlGenerationRequest,
    service: AiService = Depends(get_ai_service),
) -> SqlGenerationResponse:
    sql = await service.generate_query_rule_sql(payload.prompt, payload.identifiers)
    return SqlGenerationResponse(sql=sql)


@router.post("/copilot", response_model=CopilotAnswerResponse)
async def answer_copilot_question(
    payload: CopilotQuestionRequest,
    service: AiService = Depends(get_ai_service),
) -> CopilotAnswerResponse:
    answer, needs_context, suggestion, quick_replies = await service.answer_copilot_question(
        payload.project_id, payload.question, payload.history, payload.dashboard_id
    )
    return CopilotAnswerResponse(
        answer=answer, needs_context=needs_context, suggestion=suggestion, quick_replies=quick_replies
    )
