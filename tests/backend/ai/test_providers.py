from types import SimpleNamespace

import anthropic
import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.chat_provider import ChatProviderError, TextBlock, ToolUseBlock
from app.ai.providers.anthropic_provider import AnthropicChatProvider
from app.ai.providers.gemini_provider import GeminiChatProvider


class _FakeAnthropicMessages:
    """Mimics AsyncAnthropic().messages -- the level AnthropicChatProvider
    itself talks to. Distinct from tests/backend/ai/fakes.py's
    FakeChatProvider, which stands in for the ChatProvider interface one
    layer up (what AiService talks to) -- this one exists specifically to
    verify AnthropicChatProvider's own translation is a straight passthrough."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _FakeAnthropicClient:
    def __init__(self, responses: list) -> None:
        self.messages = _FakeAnthropicMessages(responses)


async def test_anthropic_provider_forwards_model_max_tokens_and_messages() -> None:
    client = _FakeAnthropicClient([SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])])
    provider = AnthropicChatProvider(client, "claude-haiku-4-5")

    await provider.create_message(messages=[{"role": "user", "content": "hello"}], max_tokens=500)

    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["max_tokens"] == 500
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert "system" not in call
    assert "tools" not in call


async def test_anthropic_provider_forwards_system_and_tools_when_given() -> None:
    client = _FakeAnthropicClient([SimpleNamespace(content=[])])
    provider = AnthropicChatProvider(client, "claude-haiku-4-5")
    tools = [{"name": "do_thing", "description": "d", "input_schema": {"type": "object"}}]

    await provider.create_message(messages=[], max_tokens=500, system="be helpful", tools=tools)

    call = client.messages.calls[0]
    assert call["system"] == "be helpful"
    assert call["tools"] == tools


async def test_anthropic_provider_returns_response_content_unchanged() -> None:
    blocks = [SimpleNamespace(type="text", text="hi"), SimpleNamespace(type="tool_use", id="t1", name="f", input={})]
    client = _FakeAnthropicClient([SimpleNamespace(content=blocks)])
    provider = AnthropicChatProvider(client, "claude-haiku-4-5")

    result = await provider.create_message(messages=[], max_tokens=500)

    assert result.content == blocks


async def test_anthropic_provider_wraps_api_errors() -> None:
    error = anthropic.APIConnectionError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    client = _FakeAnthropicClient([error])
    provider = AnthropicChatProvider(client, "claude-haiku-4-5")

    with pytest.raises(ChatProviderError):
        await provider.create_message(messages=[], max_tokens=500)


class _FakeGeminiModels:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _FakeGeminiClient:
    def __init__(self, responses: list) -> None:
        self.aio = SimpleNamespace(models=_FakeGeminiModels(responses))


def _gemini_response(*parts: types.Part) -> SimpleNamespace:
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(parts)))])


async def test_gemini_provider_translates_a_plain_string_message() -> None:
    client = _FakeGeminiClient([_gemini_response(types.Part(text="hi"))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    await provider.create_message(messages=[{"role": "user", "content": "hello"}], max_tokens=500)

    contents = client.aio.models.calls[0]["contents"]
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "hello"


async def test_gemini_provider_maps_assistant_role_to_model() -> None:
    client = _FakeGeminiClient([_gemini_response(types.Part(text="hi"))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    await provider.create_message(
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [TextBlock(text="hi there")]},
        ],
        max_tokens=500,
    )

    contents = client.aio.models.calls[0]["contents"]
    assert contents[1].role == "model"


async def test_gemini_provider_converts_tool_schema_via_parameters_json_schema() -> None:
    client = _FakeGeminiClient([_gemini_response(types.Part(text="hi"))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")
    tools = [
        {
            "name": "suggest_panel",
            "description": "Propose a panel",
            "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
        }
    ]

    await provider.create_message(messages=[], max_tokens=500, tools=tools)

    config = client.aio.models.calls[0]["config"]
    declaration = config.tools[0].function_declarations[0]
    assert declaration.name == "suggest_panel"
    assert declaration.description == "Propose a panel"
    assert declaration.parameters_json_schema == tools[0]["input_schema"]


async def test_gemini_provider_sets_system_instruction() -> None:
    client = _FakeGeminiClient([_gemini_response(types.Part(text="hi"))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    await provider.create_message(messages=[], max_tokens=500, system="be helpful")

    assert client.aio.models.calls[0]["config"].system_instruction == "be helpful"


async def test_gemini_provider_parses_text_response() -> None:
    client = _FakeGeminiClient([_gemini_response(types.Part(text="the answer"))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    result = await provider.create_message(messages=[{"role": "user", "content": "hi"}], max_tokens=500)

    assert len(result.content) == 1
    assert isinstance(result.content[0], TextBlock)
    assert result.content[0].text == "the answer"


async def test_gemini_provider_parses_function_call_response() -> None:
    call = types.FunctionCall(id="call_1", name="suggest_panel", args={"title": "CPU"})
    client = _FakeGeminiClient([_gemini_response(types.Part(function_call=call))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    result = await provider.create_message(messages=[{"role": "user", "content": "hi"}], max_tokens=500)

    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.id == "call_1"
    assert block.name == "suggest_panel"
    assert block.input == {"title": "CPU"}


async def test_gemini_provider_captures_thought_signature_from_response() -> None:
    part = types.Part(function_call=types.FunctionCall(id="call_1", name="query_telemetry", args={}))
    part.thought_signature = b"opaque-token"
    client = _FakeGeminiClient([_gemini_response(part)])
    provider = GeminiChatProvider(client, "gemini-flash-lite-latest")

    result = await provider.create_message(messages=[{"role": "user", "content": "hi"}], max_tokens=500)

    assert result.content[0].thought_signature == b"opaque-token"


async def test_gemini_provider_replays_thought_signature_on_the_next_call() -> None:
    # Regression: live-tested directly against the real API -- a "thinking"
    # Gemini model (gemini-flash-lite-latest) rejects a replayed function-
    # call turn that's missing the thought_signature token it originally
    # signed the call with (400 INVALID_ARGUMENT, "Function call is
    # missing a thought_signature"). Dropping it (the original
    # implementation only carried id/name/input) broke every second-plus
    # tool-calling turn.
    client = _FakeGeminiClient([_gemini_response(types.Part(text="done"))])
    provider = GeminiChatProvider(client, "gemini-flash-lite-latest")

    await provider.create_message(
        messages=[
            {"role": "user", "content": "check the temperature"},
            {
                "role": "assistant",
                "content": [
                    ToolUseBlock(
                        id="call_1", name="query_telemetry", input={}, thought_signature=b"opaque-token"
                    )
                ],
            },
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "20C"}]},
        ],
        max_tokens=500,
    )

    contents = client.aio.models.calls[0]["contents"]
    replayed_part = contents[1].parts[0]
    assert replayed_part.thought_signature == b"opaque-token"


async def test_gemini_provider_synthesizes_an_id_when_the_api_omits_one() -> None:
    # Populating FunctionCall.id isn't guaranteed by every Gemini model/
    # config combination -- ToolUseBlock.id is still required downstream
    # (AiService's loop uses it to correlate a tool_result back to this
    # call within the same turn), so a missing one must never surface as
    # an empty/None id.
    call = types.FunctionCall(id=None, name="suggest_panel", args={})
    client = _FakeGeminiClient([_gemini_response(types.Part(function_call=call))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    result = await provider.create_message(messages=[{"role": "user", "content": "hi"}], max_tokens=500)

    assert result.content[0].id


async def test_gemini_provider_resolves_function_name_for_tool_result_via_prior_call_id() -> None:
    # A tool_result dict (built fresh each iteration by AiService's loop)
    # only carries tool_use_id, not the function's name -- GeminiChatProvider
    # has to recover the name from the ToolUseBlock earlier in the same
    # `messages` list (the assistant turn that made the call) to build a
    # valid FunctionResponse, since Gemini matches by name.
    client = _FakeGeminiClient([_gemini_response(types.Part(text="done"))])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    await provider.create_message(
        messages=[
            {"role": "user", "content": "check the temperature"},
            {"role": "assistant", "content": [ToolUseBlock(id="call_1", name="query_telemetry", input={})]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "20C"}]},
        ],
        max_tokens=500,
    )

    contents = client.aio.models.calls[0]["contents"]
    function_response = contents[-1].parts[0].function_response
    assert function_response.name == "query_telemetry"
    assert function_response.id == "call_1"
    assert function_response.response == {"result": "20C"}


async def test_gemini_provider_wraps_api_errors() -> None:
    error = genai_errors.ClientError(code=429, response_json={"error": {"message": "rate limited"}})
    client = _FakeGeminiClient([error])
    provider = GeminiChatProvider(client, "gemini-2.0-flash")

    with pytest.raises(ChatProviderError):
        await provider.create_message(messages=[{"role": "user", "content": "hi"}], max_tokens=500)
