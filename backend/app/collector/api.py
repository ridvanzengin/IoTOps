from uuid import UUID

from fastapi import APIRouter, Depends

from app.collector.models import Collector, CollectorInput
from app.collector.service import CollectorService
from app.dependencies import block_in_demo_mode, get_collector_service

router = APIRouter(prefix="/api/collector", tags=["collector"])


@router.post(
    "", response_model=Collector, status_code=201, dependencies=[Depends(block_in_demo_mode())]
)
async def create_collector(
    payload: CollectorInput,
    service: CollectorService = Depends(get_collector_service),
) -> Collector:
    return await service.create(payload)


@router.get("", response_model=list[Collector])
async def list_collectors(
    service: CollectorService = Depends(get_collector_service),
) -> list[Collector]:
    return await service.list()


@router.get("/{collector_id}", response_model=Collector)
async def get_collector(
    collector_id: UUID,
    service: CollectorService = Depends(get_collector_service),
) -> Collector:
    return await service.get(collector_id)


@router.put(
    "/{collector_id}", response_model=Collector, dependencies=[Depends(block_in_demo_mode())]
)
async def update_collector(
    collector_id: UUID,
    payload: CollectorInput,
    service: CollectorService = Depends(get_collector_service),
) -> Collector:
    return await service.update(collector_id, payload)


@router.delete(
    "/{collector_id}", status_code=204, dependencies=[Depends(block_in_demo_mode())]
)
async def delete_collector(
    collector_id: UUID,
    service: CollectorService = Depends(get_collector_service),
) -> None:
    await service.delete(collector_id)


@router.post(
    "/{collector_id}/deployment",
    response_model=Collector,
    dependencies=[Depends(block_in_demo_mode())],
)
async def deploy_collector(
    collector_id: UUID,
    service: CollectorService = Depends(get_collector_service),
) -> Collector:
    return await service.deploy(collector_id)


@router.delete(
    "/{collector_id}/deployment",
    response_model=Collector,
    dependencies=[Depends(block_in_demo_mode())],
)
async def stop_collector_deployment(
    collector_id: UUID,
    service: CollectorService = Depends(get_collector_service),
) -> Collector:
    return await service.stop(collector_id)


@router.get("/{collector_id}/deployment", response_model=Collector)
async def get_collector_deployment_status(
    collector_id: UUID,
    service: CollectorService = Depends(get_collector_service),
) -> Collector:
    return await service.refresh_status(collector_id)
