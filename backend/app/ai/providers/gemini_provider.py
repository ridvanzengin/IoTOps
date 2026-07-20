from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.chat_provider import ChatMessage, ChatProviderError, TextBlock, ToolUseBlock

# Gemini's role names differ from the {"user", "assistant"} pair AiService's
# loop already uses (inherited from Anthropic's convention, baked into every
# message dict the loop builds/appends) -- translate at the boundary rather
# than changing the loop's own vocabulary, so this provider is the only
# place that needs to know either side's naming.
_ROLE_TO_GEMINI = {"user": "user", "assistant": "model"}


def _tools_to_gemini(tools: list[dict[str, Any]]) -> list[types.Tool]:
    # Each of our tool dicts is already a plain JSON-schema-shaped
    # {"name", "description", "input_schema"} -- Gemini's
    # parameters_json_schema field takes that same shape directly (a raw
    # dict, not a hand-built Schema object graph), so this is a field
    # rename, not a real translation.
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters_json_schema=tool.get("input_schema"),
                )
                for tool in tools
            ]
        )
    ]


def _messages_to_gemini(messages: list[dict[str, Any]]) -> list[types.Content]:
    # Walked in order so a tool_result turn (which only carries the
    # tool_use_id AiService's loop generated -- see ToolUseBlock) can be
    # matched back to the function name Gemini's FunctionResponse expects,
    # by remembering ids from the assistant turn that immediately precedes
    # it. Only meaningful within one conversation that's used this same
    # provider throughout -- ids/names this provider itself synthesized
    # earlier in the same `messages` list, not a cross-provider contract.
    id_to_name: dict[str, str] = {}
    contents: list[types.Content] = []

    for message in messages:
        role = _ROLE_TO_GEMINI.get(message["role"], "user")
        content = message["content"]

        if isinstance(content, str):
            contents.append(types.Content(role=role, parts=[types.Part(text=content)]))
            continue

        parts: list[types.Part] = []
        for item in content:
            # Two shapes of list content reach here: this provider's own
            # prior-turn blocks (TextBlock/ToolUseBlock, echoed back by
            # AiService's loop as an "assistant" message) and tool-result
            # dicts (built fresh by the loop each iteration, as a "user"
            # message) -- never both in the same list.
            if isinstance(item, TextBlock):
                parts.append(types.Part(text=item.text))
            elif isinstance(item, ToolUseBlock):
                id_to_name[item.id] = item.name
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(id=item.id, name=item.name, args=item.input),
                        # "Thinking" Gemini models reject a replayed
                        # function-call turn missing the signature they
                        # originally signed it with -- see ToolUseBlock's
                        # own comment. Only set when the model actually
                        # returned one (some don't use thinking at all).
                        thought_signature=item.thought_signature,
                    )
                )
            elif isinstance(item, dict) and item.get("type") == "tool_result":
                tool_use_id = item["tool_use_id"]
                parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=tool_use_id,
                            name=id_to_name.get(tool_use_id, tool_use_id),
                            response={"result": item["content"]},
                        )
                    )
                )
        if parts:
            contents.append(types.Content(role=role, parts=parts))

    return contents


class GeminiChatProvider:
    """Free-tier alternative to AnthropicChatProvider -- same ChatProvider
    interface, different wire format underneath. Unlike Anthropic's provider,
    this one does real translation both ways: our tool schemas and message
    history are Anthropic-shaped (that's what AiService's loop was written
    against first), so every create_message call re-derives Gemini's own
    Content/Part/FunctionCall/FunctionResponse structures from them, and
    converts the response back into the same TextBlock/ToolUseBlock shape
    AnthropicChatProvider returns natively."""

    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self._model = model

    async def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            system_instruction=system,
            tools=_tools_to_gemini(tools) if tools else None,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_messages_to_gemini(messages),
                config=config,
            )
        except genai_errors.APIError as exc:
            raise ChatProviderError(str(exc)) from exc

        candidates = response.candidates or []
        parts = candidates[0].content.parts if candidates and candidates[0].content else []
        if parts is None:
            parts = []

        content: list[Any] = []
        for index, part in enumerate(parts):
            if part.function_call is not None:
                call = part.function_call
                content.append(
                    ToolUseBlock(
                        id=call.id or f"call_{index}",
                        name=call.name or "",
                        input=call.args or {},
                        thought_signature=part.thought_signature,
                    )
                )
            elif part.text:
                content.append(TextBlock(text=part.text))

        return ChatMessage(content=content)
