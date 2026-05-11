from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./agentic_factcheck.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    key_encryption_secret: str = "change-me-32-byte-minimum-secret"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    default_search_provider: str = "duckduckgo"
    duckduckgo_timeout: float = 8.0

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    mistral_api_key: str | None = None
    groq_api_key: str | None = None
    deepseek_api_key: str | None = None
    tavily_api_key: str | None = None

    @cached_property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def validate_production(self):
        if not self.is_production:
            return
        errors = []
        if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET must be a unique production secret with at least 32 characters")
        if self.key_encryption_secret == "change-me-32-byte-minimum-secret" or len(self.key_encryption_secret) < 32:
            errors.append("KEY_ENCRYPTION_SECRET must be a unique production secret with at least 32 characters")
        if "*" in self.cors_origins_list:
            errors.append("CORS_ORIGINS must not contain '*' in production")
        if self.database_url.startswith("sqlite"):
            errors.append("DATABASE_URL should use PostgreSQL or another production database in production")
        if errors:
            raise RuntimeError("Invalid production configuration: " + "; ".join(errors))


settings = Settings()
