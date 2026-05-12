import pytest
from types import SimpleNamespace

from app.providers.base import ProviderAuthError, ProviderError, ProviderRateLimitError
from app.providers.registry import _classify_provider_error, _Mistral, _with_provider_retries, provider_for_name, provider_model_ids, public_model_registry


def test_provider_registry_exposes_supported_models():
    assert "gpt-4o" in provider_model_ids("openai")
    assert "gemini-2.5-pro" in provider_model_ids("google")
    assert provider_model_ids("unknown") == set()


def test_provider_factory_returns_configured_provider_without_network_calls():
    provider = provider_for_name("openai", api_key="test-key")
    assert provider.name == "openai"
    assert provider.api_key == "test-key"


def test_public_registry_marks_byok_provider_available():
    providers = public_model_registry({"anthropic"})
    anthropic = next(provider for provider in providers if provider["id"] == "anthropic")
    assert anthropic["available"] is True


def test_public_registry_does_not_mark_missing_mistral_runtime_available():
    providers = public_model_registry({"mistral"})
    mistral = next(provider for provider in providers if provider["id"] == "mistral")
    if _Mistral is None:
        assert mistral["runtime_available"] is False
        assert mistral["available"] is False
        assert "SDK" in mistral["unavailable_reason"]


def test_provider_error_classifier_detects_rate_limits():
    error = _classify_provider_error("OpenAI", Exception("rate limit exceeded"))
    assert isinstance(error, ProviderRateLimitError)
    assert error.retryable is True


def test_provider_error_classifier_detects_auth_errors():
    error = _classify_provider_error("OpenAI", Exception("invalid api key"))
    assert isinstance(error, ProviderAuthError)
    assert error.retryable is False


@pytest.mark.asyncio
async def test_provider_retry_wrapper_retries_transient_errors():
    calls = {"count": 0}

    async def operation():
        calls["count"] += 1
        if calls["count"] == 1:
            raise ProviderError("temporary", retryable=True)
        return "ok"

    assert await _with_provider_retries(operation, "Test", attempts=2) == "ok"
    assert calls["count"] == 2


class _FakeChatClient:
    def __init__(self):
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content="ok")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_openai_reasoning_models_use_openai_specific_chat_shape():
    provider = provider_for_name("openai", api_key="test-key")
    client = _FakeChatClient()
    provider._client = lambda: client

    assert await provider.generate("Check this", "gpt-5") == "ok"
    assert client.kwargs["messages"][0]["role"] == "developer"
    assert "max_completion_tokens" in client.kwargs
    assert "max_tokens" not in client.kwargs


@pytest.mark.asyncio
async def test_openai_compatible_reasoning_models_do_not_inherit_openai_reasoning_shape():
    provider = provider_for_name("groq", api_key="test-key")
    client = _FakeChatClient()
    provider._client = lambda: client

    assert await provider.generate("Check this", "openai/gpt-oss-20b") == "ok"
    assert client.kwargs["messages"][0]["role"] == "system"
    assert "max_tokens" in client.kwargs
    assert "max_completion_tokens" not in client.kwargs
