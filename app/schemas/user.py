from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import RoleEnum


class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: RoleEnum = RoleEnum.member
    avatar: Optional[str] = None
    organization_id: str


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: Optional[RoleEnum] = None
    avatar: Optional[str] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: RoleEnum
    avatar: Optional[str] = None
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
