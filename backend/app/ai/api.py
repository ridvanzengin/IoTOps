from fastapi import APIRouter, Depends

from app.ai.models import (
    CopilotAnswerResponse,
    CopilotQuestionRequest,
    QueryRuleSqlGenerationRequest,
    SqlGenerationRequest,
    SqlGenerationResponse,
)
from app.ai.service import AiService
from app.dependencies import block_in_demo_mode, get_ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

_ai_disabled_in_demo = Depends(block_in_demo_mode("AI features are disabled in this demo environment."))


@router.post("/sql", response_model=SqlGenerationResponse, dependencies=[_ai_disabled_in_demo])
async def generate_sql(
    payload: SqlGenerationRequest,
    service: AiService = Depends(get_ai_service),
) -> SqlGenerationResponse:
    sql = await service.generate_sql(payload.prompt, payload.variables)
    return SqlGenerationResponse(sql=sql)


@router.post(
    "/query-rule-sql", response_model=SqlGenerationResponse, dependencies=[_ai_disabled_in_demo]
)
async def generate_query_rule_sql(
    payload: QueryRuleSqlGenerationRequest,
    service: AiService = Depends(get_ai_service),
) -> SqlGenerationResponse:
    sql = await service.generate_query_rule_sql(payload.prompt, payload.identifiers)
    return SqlGenerationResponse(sql=sql)


@router.post("/copilot", response_model=CopilotAnswerResponse, dependencies=[_ai_disabled_in_demo])
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
