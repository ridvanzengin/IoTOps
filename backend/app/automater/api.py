from uuid import UUID

from fastapi import APIRouter, Depends

from app.automater.models import Automater, AutomaterInput
from app.automater.service import AutomaterService
from app.dependencies import get_automater_service

router = APIRouter(prefix="/api/automater", tags=["automater"])


@router.post("", response_model=Automater, status_code=201)
async def create_automater(
    payload: AutomaterInput,
    service: AutomaterService = Depends(get_automater_service),
) -> Automater:
    return await service.create(payload)


@router.get("", response_model=list[Automater])
async def list_automaters(
    service: AutomaterService = Depends(get_automater_service),
) -> list[Automater]:
    return await service.list()


@router.get("/{automater_id}", response_model=Automater)
async def get_automater(
    automater_id: UUID,
    service: AutomaterService = Depends(get_automater_service),
) -> Automater:
    return await service.get(automater_id)


@router.put("/{automater_id}", response_model=Automater)
async def update_automater(
    automater_id: UUID,
    payload: AutomaterInput,
    service: AutomaterService = Depends(get_automater_service),
) -> Automater:
    return await service.update(automater_id, payload)


@router.delete("/{automater_id}", status_code=204)
async def delete_automater(
    automater_id: UUID,
    service: AutomaterService = Depends(get_automater_service),
) -> None:
    await service.delete(automater_id)


@router.post("/{automater_id}/deployment", response_model=Automater)
async def deploy_automater(
    automater_id: UUID,
    service: AutomaterService = Depends(get_automater_service),
) -> Automater:
    return await service.deploy(automater_id)


@router.delete("/{automater_id}/deployment", response_model=Automater)
async def stop_automater_deployment(
    automater_id: UUID,
    service: AutomaterService = Depends(get_automater_service),
) -> Automater:
    return await service.stop(automater_id)


@router.get("/{automater_id}/deployment", response_model=Automater)
async def get_automater_deployment_status(
    automater_id: UUID,
    service: AutomaterService = Depends(get_automater_service),
) -> Automater:
    return await service.refresh_status(automater_id)
