from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import block_in_demo_mode, get_project_service
from app.project.models import Project, ProjectInput
from app.project.service import ProjectService

router = APIRouter(prefix="/api/project", tags=["project"])


@router.post(
    "",
    response_model=Project,
    status_code=201,
    dependencies=[Depends(block_in_demo_mode(allow_seed_token=True))],
)
async def create_project(
    payload: ProjectInput,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return await service.create(payload)


@router.get("", response_model=list[Project])
async def list_projects(
    service: ProjectService = Depends(get_project_service),
) -> list[Project]:
    return await service.list()


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return await service.get(project_id)


@router.put(
    "/{project_id}",
    response_model=Project,
    dependencies=[Depends(block_in_demo_mode(allow_seed_token=True))],
)
async def update_project(
    project_id: UUID,
    payload: ProjectInput,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return await service.update(project_id, payload)


@router.delete(
    "/{project_id}", status_code=204, dependencies=[Depends(block_in_demo_mode())]
)
async def delete_project(
    project_id: UUID,
    service: ProjectService = Depends(get_project_service),
) -> None:
    await service.delete(project_id)
