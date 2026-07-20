from typing import Any

import anthropic

from app.ai.chat_provider import ChatMessage, ChatProviderError


class AnthropicChatProvider:
    """Thinnest possible wrapper -- Anthropic's own response.content blocks
    already are the normalized shape ChatProvider promises (`.type`,
    `.text` / `.id`/`.name`/`.input`), and the SDK already accepts its own
    prior response objects back as history unchanged (that's what
    AiService's loop has always done, pre-dating this abstraction). No
    translation needed in either direction -- only Gemini's provider has
    real conversion work."""

    def __init__(self, client: anthropic.AsyncAnthropic, model: str) -> None:
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
        kwargs: dict[str, Any] = {"model": self._model, "max_tokens": max_tokens, "messages": messages}
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = tools
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise ChatProviderError(str(exc)) from exc
        return ChatMessage(content=list(response.content))
