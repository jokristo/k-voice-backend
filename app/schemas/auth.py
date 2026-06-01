from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator

from app.core.security import MAX_PASSWORD_BYTES
from app.schemas.organization import OrganizationOut
from app.schemas.user import UserOut


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    type: Optional[str] = None
    exp: Optional[datetime] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @validator("password")
    def password_within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
        return value


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    church_name: str = Field(..., min_length=2, max_length=200)
    city: str = Field(..., min_length=2, max_length=128)
    dial_code: str = Field(..., min_length=2, max_length=8)
    phone_local: str = Field(..., min_length=6, max_length=20)

    @validator("password")
    def password_within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
        return value

    @validator("dial_code")
    def dial_code_format(cls, value: str) -> str:
        v = value.strip()
        if not v.startswith("+"):
            v = f"+{v}"
        return v

    @validator("phone_local")
    def phone_digits_only(cls, value: str) -> str:
        digits = "".join(c for c in value if c.isdigit())
        if len(digits) < 6:
            raise ValueError("Numéro de téléphone invalide")
        return digits


class SignupResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    organization: OrganizationOut
