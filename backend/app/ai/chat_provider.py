"""Provider-agnostic chat/tool-calling interface.

AiService's tool-calling loop (answer_copilot_question) and its SQL
generation (_generate_sql_from_prompt) don't care which model actually
answers -- they just need something that accepts a system prompt, a
message history, and optionally a tool list, and returns a normalized
response shaped like Anthropic's own `response.content`: a list of
objects each either `{type: "text", text: str}` or `{type: "tool_use",
id: str, name: str, input: dict}`. That shape was picked because it's
already what the rest of the codebase (the loop, and every test fake)
was written against when Anthropic was the only provider -- keeping it
as the normalized shape means AnthropicChatProvider needs no translation
at all (it returns the SDK's own response objects unchanged), and only
GeminiChatProvider has real conversion work to do.

Two providers, selected by Settings.ai_provider (see app/dependencies.py's
get_chat_provider) so the app can run entirely on a free-tier model when
the Anthropic budget runs out, without touching AiService itself.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"
    # Gemini-specific (opaque to every other provider, and to AiService's
    # own loop -- it's carried here purely so GeminiChatProvider can echo
    # it back unchanged): "thinking" Gemini models sign each function-call
    # Part with a thought_signature token and reject a later turn that
    # replays the call without it, live-tested via a direct 400
    # INVALID_ARGUMENT ("Function call is missing a thought_signature").
    # None for Anthropic (and for a Gemini model that doesn't use one).
    thought_signature: bytes | None = None


@dataclass
class ChatMessage:
    content: list[Any]


class ChatProviderError(Exception):
    """Raised by any ChatProvider on a provider-level failure (network,
    auth, rate limit, malformed response) -- AiService catches this one
    exception type regardless of which provider is configured, instead of
    an SDK-specific one."""


class ChatProvider(Protocol):
    async def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatMessage: ...
