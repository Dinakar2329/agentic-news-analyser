from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class ValidateKeyRequest(BaseModel):
    provider: str
    api_key: str = Field(min_length=8)


class InvestigationCreate(BaseModel):
    claim: str = Field(min_length=8)
    agent_count: int = Field(default=3, ge=1, le=4)
    provider: str = "openai"
    model: str = "gpt-4o"
    search_depth: int = Field(default=3, ge=1, le=5)
    speed_accuracy: int = Field(default=60, ge=0, le=100)


class InvestigationResponse(BaseModel):
    id: str
    claim: str
    status: str
    verdict: str | None = None
    confidence: float | None = None
    created_at: datetime


class EventEnvelope(BaseModel):
    type: str
    investigation_id: str
    payload: dict[str, Any]
    created_at: str | None = None
