import pytest

import app.dependencies as dependencies
from app.ai.providers.anthropic_provider import AnthropicChatProvider
from app.ai.providers.gemini_provider import GeminiChatProvider
from app.config import settings
from app.dependencies import get_chat_provider
from app.shared.exceptions import AiGenerationError


def test_get_chat_provider_returns_anthropic_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "anthropic")

    assert isinstance(get_chat_provider(), AnthropicChatProvider)


def test_get_chat_provider_returns_gemini_when_configured(monkeypatch) -> None:
    # Unlike anthropic.AsyncAnthropic (which accepts an empty key and only
    # fails on the first real call), genai.Client validates api_key
    # eagerly at construction -- a real key is required here even though
    # nothing actually calls the API in this test.
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "dummy-key")

    assert isinstance(get_chat_provider(), GeminiChatProvider)


def test_get_chat_provider_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "bogus")

    with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
        get_chat_provider()


def test_get_chat_provider_raises_a_clean_error_when_gemini_key_is_missing(monkeypatch) -> None:
    # Regression: genai.Client raises a raw ValueError immediately if
    # constructed with an empty key, and that type has no
    # exception_handler in main.py -- left unguarded, a self-hoster who
    # sets AI_PROVIDER=gemini without GEMINI_API_KEY would get an
    # unhandled 500 with a full traceback on their first AI request
    # instead of the same clean, actionable AiGenerationError (-> 502)
    # every other AI failure already produces.
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "demo", False)
    monkeypatch.setattr(dependencies, "_gemini_client", None)

    with pytest.raises(AiGenerationError, match="GEMINI_API_KEY is not set"):
        get_chat_provider()


def test_get_chat_provider_shows_the_demo_message_when_gemini_key_is_missing_in_demo_mode(
    monkeypatch,
) -> None:
    # Regression: this specific failure (missing key) is raised at
    # dependency-construction time, before AiService's own try/except
    # around ChatProviderError ever runs -- without its own demo-mode
    # branch, a public demo visitor would see the raw "GEMINI_API_KEY is
    # not set" message instead of the same friendly one every other AI
    # failure already degrades to in demo mode.
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "demo", True)
    monkeypatch.setattr(dependencies, "_gemini_client", None)

    with pytest.raises(AiGenerationError, match="This is a demo"):
        get_chat_provider()
