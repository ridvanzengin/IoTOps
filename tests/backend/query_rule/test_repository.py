from uuid import uuid4

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.query_rule.models import QueryRule, QueryRuleSchedule
from app.query_rule.repository import QueryRuleRepository
from app.shared.exceptions import EntityNotFoundError


@pytest.fixture
def repository() -> QueryRuleRepository:
    database = AsyncMongoMockClient()["iotops"]
    return QueryRuleRepository(database)


def _query_rule(**overrides: object) -> QueryRule:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "name": "high-wind-scheduled",
        "sql": "SELECT station_id FROM weather_metrics",
        "identifiers": ["station_id"],
        "schedule": QueryRuleSchedule(interval="5m"),
    }
    defaults.update(overrides)
    return QueryRule(**defaults)


async def test_create_and_get(repository: QueryRuleRepository) -> None:
    query_rule = _query_rule()

    await repository.create(query_rule)
    fetched = await repository.get(query_rule.id)

    assert fetched == query_rule


async def test_get_missing_raises(repository: QueryRuleRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.get(uuid4())


async def test_list_returns_all_created(repository: QueryRuleRepository) -> None:
    first = _query_rule(name="Rule A")
    second = _query_rule(name="Rule B")
    await repository.create(first)
    await repository.create(second)

    query_rules = await repository.list()

    assert {q.id for q in query_rules} == {first.id, second.id}


async def test_list_filters_by_project_id(repository: QueryRuleRepository) -> None:
    project_a = uuid4()
    project_b = uuid4()
    rule_a = _query_rule(project_id=project_a)
    rule_b = _query_rule(project_id=project_b)
    await repository.create(rule_a)
    await repository.create(rule_b)

    query_rules = await repository.list(project_id=project_a)

    assert [q.id for q in query_rules] == [rule_a.id]


async def test_update_persists_changes(repository: QueryRuleRepository) -> None:
    query_rule = _query_rule()
    await repository.create(query_rule)

    query_rule.name = "Renamed Query Rule"
    await repository.update(query_rule)
    fetched = await repository.get(query_rule.id)

    assert fetched.name == "Renamed Query Rule"
    assert fetched.updated_at >= query_rule.created_at


async def test_update_missing_raises(repository: QueryRuleRepository) -> None:
    query_rule = _query_rule()

    with pytest.raises(EntityNotFoundError):
        await repository.update(query_rule)


async def test_delete_removes_query_rule(repository: QueryRuleRepository) -> None:
    query_rule = _query_rule()
    await repository.create(query_rule)

    await repository.delete(query_rule.id)

    with pytest.raises(EntityNotFoundError):
        await repository.get(query_rule.id)


async def test_delete_missing_raises(repository: QueryRuleRepository) -> None:
    with pytest.raises(EntityNotFoundError):
        await repository.delete(uuid4())
