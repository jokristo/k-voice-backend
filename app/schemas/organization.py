from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class OrganizationBase(BaseModel):
    name: str
    slug: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    logo: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    logo: Optional[str] = None


class OrganizationOut(OrganizationBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
