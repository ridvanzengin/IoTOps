from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.event.repository import EventRepository
from app.query_rule.models import QueryRuleInput, QueryRuleSchedule
from app.query_rule.repository import QueryRuleRepository
from app.query_rule.service import QueryRuleService
from app.shared.exceptions import EntityNotFoundError, InvalidQueryError
from app.telemetry.repository import TelemetryRepository


@pytest.fixture
def service() -> QueryRuleService:
    database = AsyncMongoMockClient()["iotops"]
    return QueryRuleService(
        repository=QueryRuleRepository(database),
        # Not exercised by these CRUD-only tests -- evaluation behavior
        # (execute/evaluate/evaluate_due) is covered separately in
        # test_evaluation.py with real fakes.
        telemetry_repository=TelemetryRepository(pool=None),  # type: ignore[arg-type]
        event_repository=EventRepository(database),
    )


def _input(**overrides: object) -> QueryRuleInput:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "name": "high-wind-scheduled",
        "sql": "SELECT station_id FROM weather_metrics",
        "identifiers": ["station_id"],
        "schedule": QueryRuleSchedule(interval="5m"),
    }
    defaults.update(overrides)
    return QueryRuleInput(**defaults)


async def test_create_persists_and_returns_query_rule(service: QueryRuleService) -> None:
    created = await service.create(_input())

    fetched = await service.get(created.id)
    assert fetched.name == "high-wind-scheduled"
    assert fetched.sql == "SELECT station_id FROM weather_metrics"


async def test_create_rejects_non_select_sql(service: QueryRuleService) -> None:
    with pytest.raises(InvalidQueryError):
        await service.create(_input(sql="DROP TABLE weather_metrics"))


async def test_create_rejects_stacked_statements(service: QueryRuleService) -> None:
    with pytest.raises(InvalidQueryError):
        await service.create(_input(sql="SELECT 1; DROP TABLE weather_metrics"))


async def test_list_filters_by_project(service: QueryRuleService) -> None:
    project_a = uuid4()
    project_b = uuid4()
    await service.create(_input(project_id=project_a))
    await service.create(_input(project_id=project_b))

    query_rules = await service.list(project_id=project_a)

    assert len(query_rules) == 1
    assert query_rules[0].project_id == project_a


async def test_update_replaces_editable_fields(service: QueryRuleService) -> None:
    created = await service.create(_input())

    updated = await service.update(
        created.id, _input(name="renamed", sql="SELECT station_id FROM weather_metrics WHERE 1=1")
    )

    assert updated.name == "renamed"
    assert updated.sql == "SELECT station_id FROM weather_metrics WHERE 1=1"


async def test_update_missing_query_rule_raises(service: QueryRuleService) -> None:
    with pytest.raises(EntityNotFoundError):
        await service.update(uuid4(), _input())


async def test_update_rejects_non_select_sql(service: QueryRuleService) -> None:
    created = await service.create(_input())

    with pytest.raises(InvalidQueryError):
        await service.update(created.id, _input(sql="DELETE FROM weather_metrics"))


async def test_delete_removes_query_rule(service: QueryRuleService) -> None:
    created = await service.create(_input())

    await service.delete(created.id)

    with pytest.raises(EntityNotFoundError):
        await service.get(created.id)
