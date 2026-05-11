import pytest

from app.providers.base import ProviderAuthError, ProviderError, ProviderRateLimitError
from app.providers.registry import _classify_provider_error, _with_provider_retries, provider_for_name, provider_model_ids, public_model_registry


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
