from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import block_in_demo_mode, get_query_rule_service
from app.query_rule.models import QueryRule, QueryRuleInput, QueryRulePreviewRequest
from app.query_rule.service import QueryRuleService
from app.telemetry.models import TelemetrySqlQueryResult

router = APIRouter(prefix="/api/query-rule", tags=["query-rule"])


@router.post(
    "", response_model=QueryRule, status_code=201, dependencies=[Depends(block_in_demo_mode())]
)
async def create_query_rule(
    payload: QueryRuleInput,
    service: QueryRuleService = Depends(get_query_rule_service),
) -> QueryRule:
    return await service.create(payload)


# Registered ahead of GET/PUT/DELETE "/{query_rule_id}" -- no method
# collision today (those aren't POST-registered), but static routes
# before param routes is the safer default regardless.
@router.post("/preview", response_model=TelemetrySqlQueryResult)
async def preview_query_rule_sql(
    payload: QueryRulePreviewRequest,
    service: QueryRuleService = Depends(get_query_rule_service),
) -> TelemetrySqlQueryResult:
    return await service.preview(payload.sql)


@router.get("", response_model=list[QueryRule])
async def list_query_rules(
    project_id: UUID | None = None,
    service: QueryRuleService = Depends(get_query_rule_service),
) -> list[QueryRule]:
    return await service.list(project_id)


@router.get("/{query_rule_id}", response_model=QueryRule)
async def get_query_rule(
    query_rule_id: UUID,
    service: QueryRuleService = Depends(get_query_rule_service),
) -> QueryRule:
    return await service.get(query_rule_id)


@router.put(
    "/{query_rule_id}", response_model=QueryRule, dependencies=[Depends(block_in_demo_mode())]
)
async def update_query_rule(
    query_rule_id: UUID,
    payload: QueryRuleInput,
    service: QueryRuleService = Depends(get_query_rule_service),
) -> QueryRule:
    return await service.update(query_rule_id, payload)


@router.delete(
    "/{query_rule_id}", status_code=204, dependencies=[Depends(block_in_demo_mode())]
)
async def delete_query_rule(
    query_rule_id: UUID,
    service: QueryRuleService = Depends(get_query_rule_service),
) -> None:
    await service.delete(query_rule_id)
