from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, validator

from app.core.security import MAX_PASSWORD_BYTES
from app.models import RoleEnum


class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: RoleEnum = RoleEnum.member
    avatar: Optional[str] = None
    organization_id: str


class UserCreate(UserBase):
    password: str

    @validator("password")
    def password_within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
        return value


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: Optional[RoleEnum] = None
    avatar: Optional[str] = None
    password: Optional[str] = None

    @validator("password")
    def password_update_within_bcrypt_limit(cls, value: Optional[str]) -> Optional[str]:
        if value and len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    name: str
    role: RoleEnum
    avatar: Optional[str] = None
    organization_id: str
    created_at: datetime
    updated_at: datetime
