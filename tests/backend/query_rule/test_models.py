from uuid import uuid4

import pytest

from app.query_rule.models import QueryRule, QueryRuleSchedule


def _schedule(**overrides: object) -> QueryRuleSchedule:
    defaults: dict[str, object] = {"interval": "5m"}
    defaults.update(overrides)
    return QueryRuleSchedule(**defaults)


def _query_rule(**overrides: object) -> QueryRule:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "name": "high-wind-scheduled",
        "sql": "SELECT station_id FROM weather_metrics",
        "identifiers": ["station_id"],
        "schedule": _schedule(),
    }
    defaults.update(overrides)
    return QueryRule(**defaults)


def test_query_rule_defaults() -> None:
    query_rule = _query_rule()

    assert query_rule.enabled is True
    assert query_rule.last_evaluated_at is None
    assert query_rule.nl_prompt is None
    assert query_rule.resolve_mode.value == "auto"


def test_query_rule_allows_zero_identifiers() -> None:
    # Matches Rule.identifiers' own optionality (also defaults to []) --
    # a query with none is a single system-wide check, sharing one
    # occurrence group across every row it returns, mirroring rule.go's
    # zero-identifiers branch.
    query_rule = _query_rule(identifiers=[])

    assert query_rule.identifiers == []


def test_schedule_requires_exactly_one_of_interval_or_cron() -> None:
    with pytest.raises(ValueError):
        QueryRuleSchedule(interval="5m", cron="0 3 * * *")

    with pytest.raises(ValueError):
        QueryRuleSchedule()


def test_schedule_accepts_cron_only() -> None:
    schedule = QueryRuleSchedule(cron="0 3 * * *")

    assert schedule.interval is None
    assert schedule.cron == "0 3 * * *"


def test_query_rule_round_trips_through_json() -> None:
    query_rule = _query_rule(nl_prompt="stations with high wind")

    restored = QueryRule.model_validate_json(query_rule.model_dump_json())

    assert restored == query_rule
