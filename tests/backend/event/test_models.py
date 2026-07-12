from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.automater.models import Condition, Rule
from app.event.models import Event, EventFlag
from app.plugin.processors.rule import DeployedRule


def _event(**overrides: object) -> Event:
    defaults: dict[str, object] = {
        "project_id": uuid4(),
        "automater_id": uuid4(),
        "rule_id": uuid4(),
        "rule_name": "swarm-alert",
        "table": "hive_metrics",
        "flag": EventFlag.MATCH,
        "matched_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Event(**defaults)


def test_event_defaults() -> None:
    event = _event()

    assert event.category == ""
    assert event.tags == {}
    assert event.fields == {}
    assert event.identifier_keys == []
    assert event.created_at is not None


def test_event_accepts_identifier_keys() -> None:
    event = _event(identifier_keys=["hive_id", "apiary_id"], tags={"hive_id": "hive-1", "apiary_id": "apiary-2"})

    assert event.identifier_keys == ["hive_id", "apiary_id"]


def test_event_accepts_go_rfc3339_nano_timestamp_string() -> None:
    # Exactly what custom-telegraf's outputs/celery plugin puts in the
    # task body (m.Time().UTC().Format(time.RFC3339Nano)).
    event = _event(matched_at="2026-07-10T12:00:00.123456789Z")

    assert event.matched_at.year == 2026
    assert event.matched_at.tzinfo is not None


def test_event_round_trips_through_json() -> None:
    event = _event(tags={"hive_id": "hive-1"}, fields={"temperature": 40.0})

    restored = Event.model_validate_json(event.model_dump_json())

    assert restored == event


def test_deployed_rule_adds_automater_and_project_id() -> None:
    rule = Rule(
        name="swarm-alert",
        table="hive_metrics",
        conditions=[Condition(column="temperature", operator=">", value=36.0)],
    )
    automater_id = uuid4()
    project_id = uuid4()

    deployed = DeployedRule(**rule.model_dump(mode="json"), automater_id=automater_id, project_id=project_id)

    assert deployed.automater_id == automater_id
    assert deployed.project_id == project_id
    # Still a Rule underneath -- same fields, nothing dropped.
    assert deployed.name == rule.name
    assert deployed.conditions == rule.conditions


def test_deployed_rule_requires_automater_and_project_id() -> None:
    rule = Rule(
        name="swarm-alert",
        table="hive_metrics",
        conditions=[Condition(column="temperature", operator=">", value=36.0)],
    )

    with pytest.raises(ValueError):
        DeployedRule(**rule.model_dump(mode="json"), project_id=uuid4())  # missing automater_id
