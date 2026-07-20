from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.ai.service import AiService
from app.config import settings
from app.dependencies import get_ai_service, get_project_service
from app.event.repository import EventRepository
from app.event.service import EventService
from app.main import app
from app.plugin.registry import build_default_registry
from app.telemetry.repository import TelemetryRepository
from app.telemetry.service import TelemetryService
from tests.backend.ai.fakes import (
    FakeAutomaterService,
    FakeChatProvider,
    FakeCollectorService,
    FakeDashboardService,
    FakeProjectService,
    FakeQueryRuleService,
    message,
    text_block,
    tool_use_block,
)
from tests.backend.project.fakes import build_project_service
from tests.backend.telemetry.fakes import FakePool

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
    # The three /api/ai/* routes are deliberately NOT here -- see
    # app/ai/api.py's own comment. They used to be, back when AI features
    # needed a paid Anthropic key public demo traffic could burn through;
    # now that the default backend is Gemini's free tier, they run for
    # real in the public demo instead of blocking outright.
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


def test_suggest_dashboard_succeeds_in_demo_mode_but_creating_it_stays_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The concern this test exists to settle: /api/ai/* routes run for real
    # in demo mode now (see app/ai/api.py), but that must only ever mean
    # the Co-pilot can propose a dashboard -- suggest_dashboard (and every
    # other suggest_*/query_*/list_existing_* tool, see app/ai/tools.py)
    # only builds a Pydantic model in memory or reads existing data; it
    # never calls a repository's create/update/delete. Actually persisting
    # the suggestion is a distinct, separate POST /api/dashboard call from
    # the frontend once the user clicks "Create" -- and that route is (and
    # must remain) in GATED_ROUTES above, same as every other mutation.
    monkeypatch.setattr(settings, "demo", True)
    pool = FakePool(tables=["device_metrics"], schema={"device_metrics": []})
    ai_service = AiService(
        telemetry_service=TelemetryService(repository=TelemetryRepository(pool)),
        event_service=EventService(
            repository=EventRepository(
                AsyncMongoMockClient()["iotops"], pubsub_redis_client=AsyncMock(), firing_redis_client=AsyncMock()
            )
        ),
        project_service=FakeProjectService(),
        chat_provider=FakeChatProvider(
            [
                message(
                    tool_use_block(
                        "suggest_dashboard",
                        {
                            "name": "Overview",
                            "panels": [
                                {
                                    "title": "A",
                                    "chart_type": "line",
                                    "sql": "SELECT time, temperature FROM device_metrics",
                                    "x_axis": "time",
                                    "y_axis": "temperature",
                                },
                                {
                                    "title": "B",
                                    "chart_type": "line",
                                    "sql": "SELECT time, temperature FROM device_metrics",
                                    "x_axis": "time",
                                    "y_axis": "temperature",
                                },
                                {
                                    "title": "C",
                                    "chart_type": "line",
                                    "sql": "SELECT time, temperature FROM device_metrics",
                                    "x_axis": "time",
                                    "y_axis": "temperature",
                                },
                            ],
                        },
                    )
                ),
                message(text_block("Here's a draft dashboard for you.")),
            ]
        ),
        automater_service=FakeAutomaterService(),
        query_rule_service=FakeQueryRuleService(),
        collector_service=FakeCollectorService(),
        plugin_registry=build_default_registry(),
        dashboard_service=FakeDashboardService(),
        demo=True,
    )
    app.dependency_overrides[get_ai_service] = lambda: ai_service
    try:
        client = TestClient(app)
        suggest_response = client.post(
            "/api/ai/copilot",
            json={"project_id": "11111111-1111-1111-1111-111111111111", "question": "suggest a dashboard"},
        )
        create_response = client.post(
            "/api/dashboard",
            json={
                "project_id": "11111111-1111-1111-1111-111111111111",
                "name": "Overview",
                "panels": [],
                "variables": [],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert suggest_response.status_code == 200
    assert suggest_response.json()["suggestion"]["kind"] == "dashboard"
    assert create_response.status_code == 403
