import asyncio
import logging
from typing import Any

import anthropic
import openai
from anthropic import AsyncAnthropic
from google import genai
from openai import AsyncOpenAI

try:
    from mistralai import Mistral as _Mistral
except ImportError:  # mistralai is currently quarantined on PyPI
    _Mistral = None

from app.core.config import settings
from app.providers.base import ModelProvider, ProviderAuthError, ProviderError, ProviderRateLimitError


_TYPED_AUTH_ERRORS: tuple[type[Exception], ...] = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
)
_TYPED_RATE_LIMIT_ERRORS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    anthropic.RateLimitError,
)
_TYPED_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


SYSTEM_INSTRUCTION = (
    "You are an evidence-first fact-checking analyst. Be concise, calibrated, "
    "and cite source titles/domains from the supplied evidence."
)

logger = logging.getLogger(__name__)


def _classify_provider_error(display_name: str, exc: Exception) -> ProviderError:
    if isinstance(exc, TimeoutError):
        return ProviderError(f"{display_name} generation timed out", retryable=True)
    if isinstance(exc, _TYPED_AUTH_ERRORS):
        return ProviderAuthError(f"{display_name} authentication failed")
    if isinstance(exc, _TYPED_RATE_LIMIT_ERRORS):
        return ProviderRateLimitError(f"{display_name} rate limit reached")
    if isinstance(exc, _TYPED_RETRYABLE_ERRORS):
        return ProviderError(f"{display_name} generation temporarily failed", retryable=True)

    status_code = getattr(exc, "status_code", None)
    message = str(exc).lower()
    if status_code in {401, 403} or "unauthorized" in message or "invalid api key" in message:
        return ProviderAuthError(f"{display_name} authentication failed")
    if status_code == 429 or "rate limit" in message or "quota" in message:
        return ProviderRateLimitError(f"{display_name} rate limit reached")
    retryable_statuses = {408, 409, 425, 500, 502, 503, 504}
    if status_code in retryable_statuses or "timeout" in message or "temporarily" in message:
        return ProviderError(f"{display_name} generation temporarily failed", retryable=True)
    return ProviderError(f"{display_name} generation failed", retryable=False)


async def _with_provider_retries(operation, display_name: str, attempts: int = 3):
    last_error: ProviderError | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.wait_for(operation(), timeout=settings.provider_timeout)
        except Exception as exc:
            provider_error = exc if isinstance(exc, ProviderError) else _classify_provider_error(display_name, exc)
            last_error = provider_error
            if not provider_error.retryable or attempt == attempts - 1:
                raise provider_error from exc
            logger.warning("provider_retry provider=%s attempt=%s error=%s", display_name, attempt + 1, provider_error)
            await asyncio.sleep(min(4.0, 0.5 * (2**attempt)))
    if last_error:
        raise last_error
    raise ProviderError(f"{display_name} generation failed", retryable=False)


class OpenAICompatibleProvider(ModelProvider):
    def __init__(
        self,
        name: str,
        display_name: str,
        models: list[dict],
        api_key: str | None = None,
        base_url: str | None = None,
        openai_reasoning_chat: bool = False,
        supports_tool_use: bool = True,
    ):
        self.name = name
        self.display_name = display_name
        self.models = models
        self.base_url = base_url
        self.openai_reasoning_chat = openai_reasoning_chat
        self._reasoning_model_ids = {entry["id"] for entry in models if entry.get("reasoning")}
        self.supports_tool_use = supports_tool_use
        super().__init__(api_key)

    def _client(self) -> AsyncOpenAI:
        if not self.api_key:
            raise ProviderAuthError(f"{self.display_name} API key is not configured")
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return AsyncOpenAI(**kwargs)

    async def validate_key(self) -> bool:
        if not await super().validate_key():
            return False
        await self._client().models.list()
        return True

    def _is_reasoning(self, model: str) -> bool:
        return model in self._reasoning_model_ids

    async def generate(self, prompt: str, model: str) -> str:
        is_reasoning = self._is_reasoning(model)
        uses_openai_reasoning_chat = is_reasoning and self.openai_reasoning_chat
        system_role = "developer" if uses_openai_reasoning_chat else "system"
        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": system_role, "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
        }
        if uses_openai_reasoning_chat:
            request_kwargs["max_completion_tokens"] = 2000
        else:
            request_kwargs["max_tokens"] = 1500

        async def operation():
            return await self._client().chat.completions.create(**request_kwargs)

        response = await _with_provider_retries(operation, self.display_name)
        return response.choices[0].message.content or ""


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    display_name = "Anthropic"

    def __init__(self, models: list[dict], api_key: str | None = None):
        self.models = models
        self.supports_tool_use = True
        super().__init__(api_key)

    def _client(self) -> AsyncAnthropic:
        if not self.api_key:
            raise ProviderAuthError("Anthropic API key is not configured")
        return AsyncAnthropic(api_key=self.api_key)

    async def validate_key(self) -> bool:
        if not await super().validate_key():
            return False
        await self._client().models.list(limit=1)
        return True

    async def generate(self, prompt: str, model: str) -> str:
        async def operation():
            response = await self._client().messages.create(
                model=model,
                max_tokens=900,
                system=SYSTEM_INSTRUCTION,
                messages=[{"role": "user", "content": prompt}],
            )
            return response

        response = await _with_provider_retries(operation, self.display_name)
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


class GoogleProvider(ModelProvider):
    name = "google"
    display_name = "Google Gemini"

    def __init__(self, models: list[dict], api_key: str | None = None):
        self.models = models
        self.supports_tool_use = True
        super().__init__(api_key)

    def _client(self):
        if not self.api_key:
            raise ProviderAuthError("Google Gemini API key is not configured")
        return genai.Client(api_key=self.api_key)

    async def validate_key(self) -> bool:
        if not await super().validate_key():
            return False
        try:
            await asyncio.to_thread(lambda: list(self._client().models.list()))
            return True
        except Exception as exc:
            if getattr(exc, "status_code", None) == 501 or "UNIMPLEMENTED" in str(exc):
                # Some Google Gemini API keys or endpoints do not support models.list.
                # Try a lightweight generation call instead.
                model_id = next(
                    (entry["id"] for entry in self.models if entry["id"] == "gemini-2.5-flash"),
                    self.models[0]["id"] if self.models else "gemini-2.5-flash",
                )

                def _test_generate():
                    return self._client().models.generate_content(
                        model=model_id,
                        contents="Hello",
                        config={"temperature": 0.0},
                    )

                try:
                    await asyncio.to_thread(_test_generate)
                    return True
                except Exception as exc2:
                    if getattr(exc2, "status_code", None) == 429 or "RESOURCE_EXHAUSTED" in str(exc2):
                        return True
                    if getattr(exc2, "status_code", None) in {401, 403}:
                        return False
                    raise
            if getattr(exc, "status_code", None) in {401, 403}:
                return False
            raise

    async def generate(self, prompt: str, model: str) -> str:
        async def operation():
            response = await asyncio.to_thread(
                self._client().models.generate_content,
                model=model,
                contents=prompt,
                config={"system_instruction": SYSTEM_INSTRUCTION},
            )
            return response

        response = await _with_provider_retries(operation, self.display_name)
        return getattr(response, "text", "") or ""


class MistralProvider(ModelProvider):
    name = "mistral"
    display_name = "Mistral"

    def __init__(self, models: list[dict], api_key: str | None = None):
        self.models = models
        self.supports_tool_use = True
        super().__init__(api_key)

    def is_runtime_available(self) -> bool:
        return _Mistral is not None

    def _client(self):
        if _Mistral is None:
            raise ProviderError(
                "Mistral SDK is not installed (the `mistralai` package is currently unavailable on PyPI)",
                retryable=False,
            )
        if not self.api_key:
            raise ProviderAuthError("Mistral API key is not configured")
        return _Mistral(api_key=self.api_key)

    async def validate_key(self) -> bool:
        if not await super().validate_key():
            return False
        await self._client().models.list_async()
        return True

    async def generate(self, prompt: str, model: str) -> str:
        async def operation():
            response = await self._client().chat.complete_async(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=900,
            )
            return response

        response = await _with_provider_retries(operation, self.display_name)
        if not response or not response.choices:
            return ""
        return response.choices[0].message.content or ""


PROVIDER_SPECS = {
    "openai": {
        "display": "OpenAI",
        "env_key": "openai_api_key",
        "kind": "openai_compatible",
        "openai_reasoning_chat": True,
        "models": [
            {"id": "gpt-4o", "label": "GPT-4o", "reasoning": False},
            {"id": "gpt-5", "label": "GPT-5", "reasoning": True},
            {"id": "o3", "label": "o3", "reasoning": True},
        ],
    },
    "anthropic": {
        "display": "Anthropic",
        "env_key": "anthropic_api_key",
        "kind": "anthropic",
        "models": [
            {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet", "reasoning": True},
            {"id": "claude-opus-4-1-20250805", "label": "Claude Opus", "reasoning": True},
        ],
    },
    "google": {
        "display": "Google Gemini",
        "env_key": "google_api_key",
        "kind": "google",
        "models": [
            {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview", "reasoning": True},
            {
                "id": "gemini-3.1-pro-preview-customtools",
                "label": "Gemini 3.1 Pro Preview Custom Tools",
                "reasoning": True,
            },
            {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash Preview", "reasoning": True},
            {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash-Lite", "reasoning": True},
            {"id": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash-Lite Preview", "reasoning": True},
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "reasoning": True},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "reasoning": True},
            {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash-Lite", "reasoning": True},
        ],
    },
    "mistral": {
        "display": "Mistral",
        "env_key": "mistral_api_key",
        "kind": "mistral",
        "models": [{"id": "mistral-large-latest", "label": "Mistral Large", "reasoning": False}],
    },
    "groq": {
        "display": "Groq",
        "env_key": "groq_api_key",
        "kind": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            {"id": "openai/gpt-oss-20b", "label": "GPT OSS 20B", "reasoning": True},
            {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B", "reasoning": False},
        ],
    },
    "deepseek": {
        "display": "DeepSeek",
        "env_key": "deepseek_api_key",
        "kind": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "models": [{"id": "deepseek-reasoner", "label": "DeepSeek R1", "reasoning": True}],
    },
}


def provider_for_name(name: str, api_key: str | None = None) -> ModelProvider:
    spec = PROVIDER_SPECS[name]
    resolved_key = api_key if api_key is not None else getattr(settings, spec["env_key"], None)
    if spec["kind"] == "anthropic":
        return AnthropicProvider(models=spec["models"], api_key=resolved_key)
    if spec["kind"] == "google":
        return GoogleProvider(models=spec["models"], api_key=resolved_key)
    if spec["kind"] == "mistral":
        return MistralProvider(models=spec["models"], api_key=resolved_key)
    return OpenAICompatibleProvider(
        name=name,
        display_name=spec["display"],
        models=spec["models"],
        api_key=resolved_key,
        base_url=spec.get("base_url"),
        openai_reasoning_chat=bool(spec.get("openai_reasoning_chat")),
        supports_tool_use=bool(spec.get("supports_tool_use", True)),
    )


def provider_registry() -> dict[str, ModelProvider]:
    return {name: provider_for_name(name) for name in PROVIDER_SPECS}


def provider_model_ids(provider_name: str) -> set[str]:
    if provider_name not in PROVIDER_SPECS:
        return set()
    return {model["id"] for model in PROVIDER_SPECS[provider_name]["models"]}


def public_model_registry(configured: set[str] | None = None) -> list[dict]:
    configured = configured or set()
    rows = []
    for name, provider in provider_registry().items():
        runtime_available = provider.is_runtime_available()
        available = runtime_available and (bool(provider.api_key) or name in configured)
        unavailable_reason = None if runtime_available else "Provider SDK is not installed in this backend runtime"
        rows.append(
            {
                "id": name,
                "name": provider.display_name,
                "available": available,
                "runtime_available": runtime_available,
                "unavailable_reason": unavailable_reason,
                "capabilities": provider.capabilities(),
                "models": provider.list_models(),
            }
        )
    return rows
