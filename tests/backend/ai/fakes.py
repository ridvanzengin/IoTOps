from types import SimpleNamespace
from typing import Any


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
