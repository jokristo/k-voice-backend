from datetime import datetime, timedelta
from typing import Any, Dict

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_PASSWORD_BYTES = 72


def _validate_password_length(password: str) -> None:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    _validate_password_length(plain_password)
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    _validate_password_length(password)
    return pwd_context.hash(password)


def _create_token(data: Dict[str, Any], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str) -> str:
    expire = timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token({"sub": subject, "type": "access"}, expire)


def create_refresh_token(subject: str) -> str:
    expire = timedelta(minutes=settings.refresh_token_expire_minutes)
    return _create_token({"sub": subject, "type": "refresh"}, expire)
