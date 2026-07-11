import fakeredis
import mongomock
import pytest

from app.automater import tasks


@pytest.fixture(autouse=True)
def fake_clients(monkeypatch: pytest.MonkeyPatch) -> tuple[mongomock.Collection, fakeredis.FakeRedis]:
    collection = mongomock.MongoClient().get_database("iotops")["events"]
    redis_client = fakeredis.FakeRedis()
    monkeypatch.setattr(tasks, "_events_collection", collection)
    monkeypatch.setattr(tasks, "_redis_client", redis_client)
    return collection, redis_client


def _tags(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "flag": "match",
        "matched_rule": "swarm-alert",
        "matched_rule_id": "11111111-1111-1111-1111-111111111111",
        "automater_id": "22222222-2222-2222-2222-222222222222",
        "project_id": "33333333-3333-3333-3333-333333333333",
        "rule_category": "hive-health",
        "rule_severity": "high",
        "rule_event_type": "threshold_breach",
        "hive_id": "hive-1",
    }
    defaults.update(overrides)
    return defaults


def test_log_rule_match_persists_event_document(fake_clients: tuple) -> None:
    collection, _ = fake_clients
    fields = {"temperature": 40.0, "rule_message": "Hive hive-1 swarm risk"}

    tasks.log_rule_match.run(
        measurement="hive_metrics", tags=_tags(), fields=fields, timestamp="2026-07-10T12:00:00.123456789Z"
    )

    document = collection.find_one()
    assert document is not None
    assert document["project_id"] == "33333333-3333-3333-3333-333333333333"
    assert document["automater_id"] == "22222222-2222-2222-2222-222222222222"
    assert document["rule_id"] == "11111111-1111-1111-1111-111111111111"
    assert document["rule_name"] == "swarm-alert"
    assert document["table"] == "hive_metrics"
    assert document["flag"] == "match"
    assert document["message"] == "Hive hive-1 swarm risk"
    assert document["fields"]["temperature"] == 40.0


def test_log_rule_match_publishes_to_project_scoped_channel(fake_clients: tuple) -> None:
    collection, redis_client = fake_clients
    pubsub = redis_client.pubsub()
    pubsub.subscribe("events:33333333-3333-3333-3333-333333333333")
    pubsub.get_message()  # discard the subscribe confirmation

    tasks.log_rule_match.run(
        measurement="hive_metrics", tags=_tags(), fields={"temperature": 40.0}, timestamp="2026-07-10T12:00:00Z"
    )

    message = pubsub.get_message(timeout=1)
    assert message is not None
    assert message["type"] == "message"
    assert b'"rule_name":"swarm-alert"' in message["data"]


def test_log_rule_match_requires_attribution_tags(fake_clients: tuple) -> None:
    # Regression guard: a metric missing project_id/automater_id/
    # matched_rule_id (e.g. from an Automater deployed before this
    # attribution was added) must fail loudly, not silently write an
    # unattributed/uncorrelated Event.
    incomplete_tags = _tags()
    del incomplete_tags["project_id"]

    with pytest.raises(KeyError):
        tasks.log_rule_match.run(
            measurement="hive_metrics", tags=incomplete_tags, fields={}, timestamp="2026-07-10T12:00:00Z"
        )
