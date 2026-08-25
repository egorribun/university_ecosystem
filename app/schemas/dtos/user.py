from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import AliasPath, ConfigDict, EmailStr, Field

from app.models.enums import UserRole
from app.schemas.base import SecureBaseModel


class DTOModel(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class UserDTO(DTOModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    group_id: uuid.UUID | None
    is_active: bool
    mfa_required: bool
    mfa_default_method: str | None
    mfa_last_verified_at: datetime | None
    created_at: datetime | None
    pending_email: EmailStr | None = None

    # Flattened profile fields
    full_name: str | None = Field(
        None, validation_alias=AliasPath("profile", "full_name")
    )
    avatar_url: str | None = Field(
        None, validation_alias=AliasPath("profile", "avatar_url")
    )
    email_verified_at: datetime | None = None
    email_mfa_enabled_at: datetime | None = None
    mfa_epoch: int = 0

    # Nested DTOs
    profile: UserProfileDTO | None = None
    preferences: UserPreferencesDTO | None = None


class UserAuthDTO(UserDTO):
    hashed_password: str


class UserProfileDTO(DTOModel):
    user_id: uuid.UUID
    full_name: str | None
    avatar_url: str | None
    cover_url: str | None
    about: str | None
    telegram: str | None
    status: str | None
    achievements: str | None
    position: str | None
    department: str | None


class UserPreferencesDTO(DTOModel):
    user_id: uuid.UUID
    dnd_enabled: bool
    dnd_start: time | None
    dnd_end: time | None
    timezone: str | None


class UserListingDTO(DTOModel):
    id: uuid.UUID
    email: str
    role: UserRole
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime
