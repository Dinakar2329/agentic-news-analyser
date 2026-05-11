import jwt
import pytest

from app.auth.security import create_access_token, decode_access_token
from app.core.config import Settings, settings


def test_access_token_contains_expected_type():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_decode_rejects_non_access_token():
    token = jwt.encode({"sub": "user-123", "typ": "refresh"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_production_config_rejects_demo_secrets():
    settings = Settings(environment="production")
    with pytest.raises(RuntimeError) as exc:
        settings.validate_production()
    assert "JWT_SECRET" in str(exc.value)
    assert "KEY_ENCRYPTION_SECRET" in str(exc.value)


def test_development_config_allows_local_defaults():
    Settings(environment="development").validate_production()
