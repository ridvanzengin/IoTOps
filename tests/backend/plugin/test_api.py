from fastapi.testclient import TestClient

from app.main import app


def test_list_plugins_returns_builtins() -> None:
    client = TestClient(app)

    response = client.get("/api/plugin")

    assert response.status_code == 200
    names = {plugin["name"] for plugin in response.json()}
    assert names == {"mqtt", "kafka", "http", "amqp", "timescaledb", "rule", "celery"}


def test_list_plugins_filters_by_category() -> None:
    client = TestClient(app)

    response = client.get("/api/plugin", params={"category": "input"})

    assert response.status_code == 200
    assert [plugin["name"] for plugin in response.json()] == ["mqtt", "kafka", "http", "amqp"]


def test_get_plugin_returns_configuration_schema() -> None:
    client = TestClient(app)

    response = client.get("/api/plugin/mqtt")

    assert response.status_code == 200
    assert "servers" in response.json()["configuration_schema"]["properties"]


def test_get_unknown_plugin_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/api/plugin/does-not-exist")

    assert response.status_code == 404
