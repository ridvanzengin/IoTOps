from app.project.models import Project


def test_project_defaults() -> None:
    project = Project(name="Beekeeping")

    assert project.description == ""
    assert project.schema_version == 1


def test_project_round_trips_through_json() -> None:
    project = Project(name="Beekeeping", description="Hive monitoring")

    restored = Project.model_validate_json(project.model_dump_json())

    assert restored == project
