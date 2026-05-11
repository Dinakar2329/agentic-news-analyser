from datetime import datetime, timedelta, timezone
from hashlib import sha256

import jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    issued_at = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": subject, "exp": expires, "iat": issued_at, "typ": "access"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return str(payload["sub"])


def _fernet() -> Fernet:
    digest = sha256(settings.key_encryption_secret.encode("utf-8")).digest()
    return Fernet(Fernet.generate_key() if False else __import__("base64").urlsafe_b64encode(digest))


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key: str) -> str:
    return _fernet().decrypt(encrypted_key.encode("utf-8")).decode("utf-8")


def key_hint(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"
