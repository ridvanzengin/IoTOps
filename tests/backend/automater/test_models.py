from uuid import uuid4

import pytest

from app.automater.models import Automater, Condition, Rule, RuleOperator, RuleSeverity
from app.shared.models import InputPlugin, OutputPlugin


def _condition(**overrides: object) -> Condition:
    defaults: dict[str, object] = {"column": "temperature", "operator": ">", "value": 30.0}
    defaults.update(overrides)
    return Condition(**defaults)


def _rule(**overrides: object) -> Rule:
    defaults: dict[str, object] = {
        "name": "swarm-alert",
        "table": "hive_metrics",
        "conditions": [_condition()],
    }
    defaults.update(overrides)
    return Rule(**defaults)


def _input() -> InputPlugin:
    return InputPlugin(
        plugin_type="mqtt",
        name="hive-mqtt",
        configuration={"name_override": "hive_metrics"},
    )


def _output() -> OutputPlugin:
    return OutputPlugin(plugin_type="celery", configuration={"task_name": "automater.tasks.log_rule_match"})


def test_condition_defaults_to_and_join() -> None:
    condition = _condition()

    assert condition.join == RuleOperator.AND


def test_rule_defaults() -> None:
    rule = _rule()

    assert rule.enabled is True
    assert rule.priority == 0
    assert rule.severity == RuleSeverity.LOW
    assert rule.ttl == "5m"
    assert rule.identifiers == []
    assert rule.description == ""


def test_rule_requires_at_least_one_condition() -> None:
    with pytest.raises(ValueError, match="at least one condition"):
        Rule(name="no-conditions", table="hive_metrics", conditions=[])


def test_rule_round_trips_through_json() -> None:
    rule = _rule(conditions=[_condition(), _condition(column="humidity", operator="<", value=40.0, join="OR")])

    restored = Rule.model_validate_json(rule.model_dump_json())

    assert restored == rule
    assert restored.conditions[1].join == RuleOperator.OR


def test_automater_requires_at_least_one_rule() -> None:
    with pytest.raises(ValueError, match="at least one rule"):
        Automater(
            project_id=uuid4(),
            name="Empty Automater",
            inputs=[_input()],
            outputs=[_output()],
            rules=[],
        )


def test_automater_requires_at_least_one_input() -> None:
    with pytest.raises(ValueError, match="at least one input"):
        Automater(
            project_id=uuid4(),
            name="No Input",
            inputs=[],
            outputs=[_output()],
            rules=[_rule()],
        )


def test_automater_allows_multiple_rules_with_the_same_name() -> None:
    # Rule names are deliberately not required unique -- the Redis
    # firing-state key is scoped by Rule.id, not name, so two same-named
    # rules on different columns never collide (see rule.go's firingKey).
    automater = Automater(
        project_id=uuid4(),
        name="Multi-Rule Automater",
        inputs=[_input()],
        outputs=[_output()],
        rules=[
            _rule(name="dup", conditions=[_condition(column="temperature")]),
            _rule(name="dup", conditions=[_condition(column="humidity")]),
        ],
    )

    assert automater.rules[0].id != automater.rules[1].id
    assert automater.rules[0].name == automater.rules[1].name == "dup"


def test_automater_round_trips_through_json() -> None:
    automater = Automater(
        project_id=uuid4(),
        name="Hive Automater",
        inputs=[_input()],
        outputs=[_output()],
        rules=[_rule()],
    )

    restored = Automater.model_validate_json(automater.model_dump_json())

    assert restored == automater
