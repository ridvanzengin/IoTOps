from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.dependencies import get_project_service
from app.main import app
from app.project.repository import ProjectRepository
from app.project.service import ProjectService

VALID_PAYLOAD = {"name": "Beekeeping", "description": "Hive monitoring"}


@pytest.fixture
def client() -> TestClient:
    database = AsyncMongoMockClient()["iotops"]
    service = ProjectService(repository=ProjectRepository(database))
    app.dependency_overrides[get_project_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_project_returns_201(client: TestClient) -> None:
    response = client.post("/api/project", json=VALID_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["name"] == "Beekeeping"


def test_get_missing_project_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/project/{uuid4()}")

    assert response.status_code == 404


def test_list_projects_returns_created_project(client: TestClient) -> None:
    created = client.post("/api/project", json=VALID_PAYLOAD).json()

    response = client.get("/api/project")

    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [created["id"]]


def test_update_project_renames_it(client: TestClient) -> None:
    created = client.post("/api/project", json=VALID_PAYLOAD).json()

    response = client.put(
        f"/api/project/{created['id']}",
        json={**VALID_PAYLOAD, "name": "Renamed Project"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Project"


def test_delete_project_removes_it(client: TestClient) -> None:
    created = client.post("/api/project", json=VALID_PAYLOAD).json()

    response = client.delete(f"/api/project/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/project/{created['id']}").status_code == 404
