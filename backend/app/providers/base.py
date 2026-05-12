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
    supports_streaming: bool = False
    supports_structured_output: bool = False
    supports_tool_use: bool = False

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def capabilities(self) -> dict:
        return {
            "streaming": self.supports_streaming,
            "structured_output": self.supports_structured_output,
            "tool_use": self.supports_tool_use,
        }

    def is_runtime_available(self) -> bool:
        return True

    async def validate_key(self) -> bool:
        return bool(self.api_key and len(self.api_key) >= 8)

    def list_models(self) -> list[dict]:
        return self.models

    @abstractmethod
    async def generate(self, prompt: str, model: str) -> str:
        raise NotImplementedError

    async def stream_generate(self, prompt: str, model: str) -> AsyncIterator[str]:
        yield await self.generate(prompt, model)
