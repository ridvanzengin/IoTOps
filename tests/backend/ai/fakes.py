from types import SimpleNamespace
from typing import Any

from app.shared.exceptions import EntityNotFoundError


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name: str, input: dict[str, Any], id: str = "toolu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


def message(*blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks))


class FakeMessages:
    """Stands in for AsyncAnthropic().messages -- .create() returns the next
    queued response (or raises it, if it's an Exception), in order. Captures
    every call's kwargs so tests can assert on the request shape (system
    prompt, tools, message history) without hitting the real API."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages.create called more times than responses configured")
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeAnthropicClient:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = FakeMessages(responses)


class FakeProjectService:
    """Stands in for ProjectService -- AiService only ever calls .get() to
    read a project's ai_context, so a full ProjectService (which pulls in
    real Collector/Automater/Dashboard/QueryRule services just to support
    its own delete() cascade) is unnecessary machinery for AI-module
    tests."""

    def __init__(self, ai_context: str = "") -> None:
        self._ai_context = ai_context

    async def get(self, project_id: Any) -> Any:
        return SimpleNamespace(ai_context=self._ai_context)


class FakeAutomaterService:
    """Stands in for AutomaterService -- the suggest-automation intent's
    list_existing_rules tool only ever calls .list(), so a full
    AutomaterService (which pulls in a real Docker manager) is
    unnecessary machinery for AI-module tests."""

    def __init__(self, automaters: list[Any] | None = None) -> None:
        self._automaters = automaters or []

    async def list(self) -> list[Any]:
        return self._automaters


class FakeQueryRuleService:
    """Stands in for QueryRuleService -- list_existing_rules only ever
    calls .list(project_id)."""

    def __init__(self, query_rules: list[Any] | None = None) -> None:
        self._query_rules = query_rules or []

    async def list(self, project_id: Any = None) -> list[Any]:
        return [qr for qr in self._query_rules if qr.project_id == project_id]


class FakeDashboardService:
    """Stands in for DashboardService -- list_existing_panels only ever
    calls .list() (no project filter, same gap as FakeAutomaterService's
    own .list()), and answer_copilot_question's dashboard_hint resolution
    only ever calls .get()."""

    def __init__(self, dashboards: list[Any] | None = None) -> None:
        self._dashboards = dashboards or []

    async def list(self) -> list[Any]:
        return self._dashboards

    async def get(self, dashboard_id: Any) -> Any:
        match = next((d for d in self._dashboards if d.id == dashboard_id), None)
        if match is None:
            raise EntityNotFoundError("Dashboard", dashboard_id)
        return match


class FakeCollectorService:
    """Stands in for CollectorService -- AiService only ever calls
    .list() (no project filter, same as the real one) to derive which
    telemetry tables belong to the current project. A full CollectorService
    (which pulls in a real Docker manager) is unnecessary machinery for
    AI-module tests."""

    def __init__(self, collectors: list[Any] | None = None) -> None:
        self._collectors = collectors or []

    async def list(self) -> list[Any]:
        return self._collectors
