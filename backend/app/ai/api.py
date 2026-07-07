from fastapi import APIRouter, Depends

from app.ai.models import SqlGenerationRequest, SqlGenerationResponse
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
