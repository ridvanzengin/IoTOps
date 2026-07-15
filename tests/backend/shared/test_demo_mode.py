from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_project_service
from app.main import app
from tests.backend.project.fakes import build_project_service

# Every route that must be gated by block_in_demo_mode -- kept as an
# explicit (method, path) set, not derived, so a route added later without
# the guard fails this test instead of silently shipping unprotected.
GATED_ROUTES = {
    ("POST", "/api/project"),
    ("PUT", "/api/project/{project_id}"),
    ("DELETE", "/api/project/{project_id}"),
    ("POST", "/api/collector"),
    ("PUT", "/api/collector/{collector_id}"),
    ("DELETE", "/api/collector/{collector_id}"),
    ("POST", "/api/collector/{collector_id}/deployment"),
    ("DELETE", "/api/collector/{collector_id}/deployment"),
    ("POST", "/api/automater"),
    ("POST", "/api/automater/rules"),
    ("PUT", "/api/automater/{automater_id}/rules/{rule_id}/enabled"),
    ("DELETE", "/api/automater/{automater_id}/rules/{rule_id}"),
    ("PUT", "/api/automater/{automater_id}"),
    ("DELETE", "/api/automater/{automater_id}"),
    ("POST", "/api/automater/{automater_id}/deployment"),
    ("DELETE", "/api/automater/{automater_id}/deployment"),
    ("POST", "/api/query-rule"),
    ("PUT", "/api/query-rule/{query_rule_id}"),
    ("DELETE", "/api/query-rule/{query_rule_id}"),
    ("POST", "/api/dashboard"),
    ("PUT", "/api/dashboard/{dashboard_id}"),
    ("DELETE", "/api/dashboard/{dashboard_id}"),
    ("POST", "/api/dashboard/{dashboard_id}/panel"),
    ("PUT", "/api/dashboard/{dashboard_id}/panel/{panel_id}"),
    ("DELETE", "/api/dashboard/{dashboard_id}/panel/{panel_id}"),
    ("PUT", "/api/dashboard/{dashboard_id}/layout"),
    ("POST", "/api/event/occurrences/{event_id}/resolve"),
    ("POST", "/api/ai/sql"),
    ("POST", "/api/ai/query-rule-sql"),
}


def _route_has_demo_guard(route: APIRoute) -> bool:
    # block_in_demo_mode() returns a fresh `_guard` closure per call site,
    # so identity comparison against one reference won't work -- match on
    # the closure's qualname instead, which is stable regardless of which
    # call site (or which `reason=` override) produced it.
    return any(
        getattr(dependency.call, "__qualname__", "").startswith(
            "block_in_demo_mode.<locals>._guard"
        )
        for dependency in route.dependant.dependencies
    )


def test_every_mutating_route_is_gated_and_nothing_else_is() -> None:
    api_routes = [route for route in app.routes if isinstance(route, APIRoute)]
    actual_gated = {
        (method, route.path)
        for route in api_routes
        for method in route.methods
        if method != "HEAD" and _route_has_demo_guard(route)
    }
    assert actual_gated == GATED_ROUTES


def test_mutating_route_blocked_in_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo", True)
    client = TestClient(app)

    response = client.post("/api/project", json={"name": "x", "description": ""})

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "This is a read-only demo instance. Create, edit, and delete actions are disabled."
    )


def test_ai_route_blocked_with_specific_message_in_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo", True)
    client = TestClient(app)

    response = client.post("/api/ai/sql", json={"prompt": "x", "variables": {}})

    assert response.status_code == 403
    assert response.json()["detail"] == "AI features are disabled in this demo environment."


def test_mutating_route_allowed_when_demo_mode_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "demo", False)
    service = build_project_service(tmp_path)
    app.dependency_overrides[get_project_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/api/project", json={"name": "x", "description": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
