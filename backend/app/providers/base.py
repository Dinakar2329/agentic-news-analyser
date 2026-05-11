from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class ProviderAuthError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class ModelProvider(ABC):
    name: str
    display_name: str
    models: list[dict]

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def capabilities(self) -> dict:
        return {
            "streaming": True,
            "structured_output": True,
            "tool_use": self.name in {"openai", "anthropic", "google", "mistral"},
        }

    async def validate_key(self) -> bool:
        return bool(self.api_key and len(self.api_key) >= 8)

    def list_models(self) -> list[dict]:
        return self.models

    @abstractmethod
    async def generate(self, prompt: str, model: str) -> str:
        raise NotImplementedError

    async def stream_generate(self, prompt: str, model: str) -> AsyncIterator[str]:
        yield await self.generate(prompt, model)
