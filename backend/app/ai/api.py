from fastapi import APIRouter, Depends

from app.ai.models import QueryRuleSqlGenerationRequest, SqlGenerationRequest, SqlGenerationResponse
from app.ai.service import AiService
from app.dependencies import get_ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


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
