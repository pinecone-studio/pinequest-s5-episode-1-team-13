from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, computed_field

from app.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH
from app.database.models import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    @computed_field
    @property
    def is_demo(self) -> bool:
        return get_settings().is_demo_email(self.email)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=100)
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    role: UserRole = UserRole.HUB_EMPLOYEE


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=100)
    password: SecretStr | None = Field(None, min_length=MIN_PASSWORD_LENGTH, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
