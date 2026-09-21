"""User profile, preference and account-lifecycle schemas."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.localization import translate
from app.models.enums import UserRole
from app.schemas.common import BaseModel, OrmModel
from app.schemas.identity import MfaTotpEnrollmentOut, SessionSigningKeyOut, Token
from app.schemas.mappers.user_mapper import (
    map_user_orm_to_dict,
    map_user_orm_to_public_dict,
)


class UserProfileBase(BaseModel):
    about: str | None = None
    telegram: str | None = None
    status: str | None = None
    achievements: str | None = None
    department: str | None = None
    position: str | None = None


class UserPreferencesBase(OrmModel):
    dnd_enabled: bool | None = None
    dnd_start: time | None = None
    dnd_end: time | None = None
    timezone: str | None = None

    @field_validator("dnd_enabled", mode="before")
    @classmethod
    def _default_dnd_enabled(cls, value: bool | None) -> bool:
        """Ensure a boolean is always returned even when preferences are missing."""
        return bool(value) if value is not None else False

    @model_validator(mode="before")
    def _validate_dnd(cls, data: Any) -> Any:
        raw = data.data if hasattr(data, "data") and hasattr(data, "context") else data
        payload = raw if isinstance(raw, dict) else {}
        enabled = payload.get("dnd_enabled")
        start = payload.get("dnd_start")
        end = payload.get("dnd_end")
        if enabled and (start is None or end is None):
            raise ValueError(translate("validation.dnd.times_required"))
        return raw

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            ZoneInfo(text)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise PydanticCustomError(
                "timezone.invalid",
                translate("validation.timezone.invalid"),
            ) from exc
        return text


class UserEducationBase(BaseModel):
    institute: str | None = None
    course: str | None = None
    education_level: str | None = None
    track: str | None = None
    program: str | None = None
    record_book_number: str | None = None


class UserProfilePublicFlattened(BaseModel):
    about: str | None = None
    telegram: str | None = None
    profile_status: str | None = None
    profile_department: str | None = None
    position: str | None = None
    course: str | None = None
    institute: str | None = None


class UserProfileFullFlattened(UserProfilePublicFlattened):
    achievements: str | None = None
    education_level: str | None = None
    track: str | None = None
    program: str | None = None
    record_book_number: str | None = None
    timezone: str | None = None
    dnd_enabled: bool | None = None
    dnd_start: time | None = Field(default=None, title="Dnd Start")
    dnd_end: time | None = Field(default=None, title="Dnd End")


class UserBase(UserProfileFullFlattened):
    email: EmailStr
    full_name: str | None = None
    role: UserRole = UserRole.STUDENT
    group_id: uuid.UUID | None = None
    avatar_url: str | None = None
    cover_url: str | None = None
    spotify_connected: bool = False
    spotify_display_name: str | None = None

    # Overrides for Identity schemas where these have strict types/defaults
    dnd_enabled: bool = Field(default=False, title="Dnd Enabled")


class UserSearchFilter(BaseModel):
    full_name: str | None = None
    search: str | None = None
    group_id: uuid.UUID | None = None
    role: UserRole | None = None
    # RZ-07 (audit 2026-03-04): Enforce a server-side page-size ceiling.
    # Without bounds, an admin could request 10 000 rows in one call,
    # causing OOM on the process and read-replica locking under load.
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    after_id: uuid.UUID | None = Field(
        default=None,
        description="Keyset cursor: fetch users with id > after_id",
    )


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=200)
    invite_code: str | None = None


class UserOut(OrmModel, UserBase):
    id: uuid.UUID
    is_active: bool
    pending_email: EmailStr | None = None
    email_verified_at: datetime | None = None
    email_mfa_enabled_at: datetime | None = None
    spotify_is_connected: bool | None = None
    mfa_required: bool = False
    mfa_default_method: Literal["totp", "email_otp"] | None = None
    mfa_last_verified_at: datetime | None = None
    totp_enrollments: list[MfaTotpEnrollmentOut] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    recovery_codes_left: int = 0

    # Nested related models
    profile_detail: UserProfileBase | None = None
    preferences: UserPreferencesBase | None = None
    education_path: UserEducationBase | None = None

    # Optimized URLs are calculated asynchronously or by the client to prevent CPU-blocking
    # HMAC generation in the main event loop during list serialization.
    avatar_url_optimized: str | None = None
    cover_url_optimized: str | None = None

    @field_validator("dnd_enabled", mode="before")
    @classmethod
    def _default_dnd_enabled(cls, value: bool | None) -> bool:
        """Ensure a boolean is always returned even when preferences are missing."""
        return bool(value) if value is not None else False

    @model_validator(mode="before")
    @classmethod
    def _flatten_user_data(cls, data: Any) -> Any:
        """Flatten UserProfile and UserPreferences into the main User dict/object."""
        if isinstance(data, dict):
            return data
        return map_user_orm_to_dict(data)


class UserPublicOut(OrmModel, UserProfilePublicFlattened):
    """Publicly visible user profile information (PII-safe)."""

    id: uuid.UUID
    full_name: str | None = None
    role: UserRole = UserRole.STUDENT
    group_id: uuid.UUID | None = None
    avatar_url: str | None = None
    cover_url: str | None = None
    profile_detail: UserProfileBase | None = None
    education_path: UserEducationBase | None = None
    is_active: bool

    @model_validator(mode="before")
    @classmethod
    def _flatten_public_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        return map_user_orm_to_public_dict(data)

    avatar_url_optimized: str | None = None


class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    role: UserRole | None = None
    group_id: uuid.UUID | None = None
    reset_mfa: bool | None = None


class DataExportOut(BaseModel):
    profile: dict[str, Any]
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    mfa_challenge_count: int = 0
    mfa_enrollments: list[dict[str, Any]] = Field(default_factory=list)
    access_logs: list[dict[str, Any]] = Field(default_factory=list)


class DataDeletionRequest(BaseModel):
    confirm: bool = Field(..., description="Explicit consent to remove personal data")


class DataDeletionOut(BaseModel):
    deleted: bool
    anonymized_email: EmailStr


class UserProfileUpdate(UserProfileBase, UserPreferencesBase, UserEducationBase):
    full_name: str | None = None
    profile_detail: UserProfileBase | None = None
    preferences: UserPreferencesBase | None = None
    education_path: UserEducationBase | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_email_mutation(cls, data: Any) -> Any:
        if isinstance(data, dict) and "email" in data:
            raise ValueError(
                "Email cannot be changed through the profile endpoint; "
                "use /users/me/email"
            )
        return data


class TokenWithProfile(Token):
    user: UserOut
    session: SessionSigningKeyOut | None = None
