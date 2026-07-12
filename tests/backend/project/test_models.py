from uuid import uuid4

from app.project.models import Project


def test_project_defaults() -> None:
    project = Project(name="Beekeeping")

    assert project.description == ""
    assert project.schema_version == 1
    assert project.default_dashboard_id is None


def test_project_accepts_default_dashboard_id() -> None:
    dashboard_id = uuid4()

    project = Project(name="Beekeeping", default_dashboard_id=dashboard_id)

    assert project.default_dashboard_id == dashboard_id


def test_project_round_trips_through_json() -> None:
    project = Project(name="Beekeeping", description="Hive monitoring")

    restored = Project.model_validate_json(project.model_dump_json())

    assert restored == project
