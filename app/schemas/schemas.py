from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.localization import translate
from app.models.auth import ChallengeState
from app.models.enums import UserRole
from app.schemas.base import SecureBaseModel
from app.schemas.mappers.user_mapper import (
    map_user_orm_to_dict,
    map_user_orm_to_public_dict,
)
from app.schemas.validators import CleanStr, SafeRichText, SanitizedInput, SanitizedStr


class BaseModel(SecureBaseModel):
    pass


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    created_at: datetime | None = Field(default=None)

    @classmethod
    def from_orm(cls, obj: Any) -> OrmModel:
        return cls.model_validate(obj)


class PasswordResetTokenCreate(BaseModel):
    user_id: uuid.UUID  # RZ-33-17: was `int`, model uses UUID7 PKs
    token_hash: str
    expires_at: datetime
    used: bool = False


class EmailChangeTokenCreate(BaseModel):
    user_id: uuid.UUID  # RZ-33-17: was `int`, model uses UUID7 PKs
    new_email: EmailStr
    token_hash: str
    expires_at: datetime
    used: bool = False


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class UserEmailChangeIn(BaseModel):
    email: EmailStr
    password: str


class UserEmailConfirmIn(BaseModel):
    token: str


class UserPasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


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


class NewsCommentOut(BaseModel):
    id: uuid.UUID
    content: str
    user_id: uuid.UUID
    user_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NewsCommentCreate(BaseModel):
    content: SafeRichText = Field(..., min_length=1, max_length=1000)


class NewsCommentUpdate(BaseModel):
    content: SafeRichText = Field(..., min_length=1, max_length=1000)


class NewsInteractionsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    likes_count: int
    is_liked: bool
    comments: list[NewsCommentOut]
    comments_count: int


class MfaTotpEnrollmentOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    label: str | None = None
    is_active: bool
    confirmed_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class MfaChallengeOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    challenge_type: str
    token: str
    expires_at: datetime
    consumed_at: datetime | None = None
    created_at: datetime
    payload: dict[str, Any] | None = None
    attempt_count: int = 0
    # TD-W5-01: Added after the original payload shape was persisted.  The
    # default preserves deserialisation of pre-migration payloads that have no
    # state field; ORM rows created after the migration expose the enum value.
    state: ChallengeState = ChallengeState.PENDING


class MfaFactorStatusOut(BaseModel):
    disabled: bool
    mfa_default_method: str | None = None
    mfa_required: bool = False


class WebAuthnRegistrationOptionsOut(BaseModel):
    publicKey: dict[str, Any]
    challenge_token: str


class WebAuthnRegistrationVerifyIn(BaseModel):
    challenge: str
    response: dict[str, Any]
    label: str | None = None


class WebAuthnAuthenticationOptionsOut(BaseModel):
    publicKey: dict[str, Any]
    challenge_token: str


class WebAuthnAuthenticationVerifyIn(BaseModel):
    challenge: str
    response: dict[str, Any]


class RecoveryCodesGenerateOut(BaseModel):
    codes: list[str]
    created_at: datetime


class RecoveryCodeVerifyIn(BaseModel):
    code: str


class UserOut(OrmModel, UserBase):
    id: uuid.UUID
    is_active: bool
    pending_email: EmailStr | None = None
    spotify_is_connected: bool | None = None
    mfa_required: bool = False
    mfa_default_method: str | None = None
    mfa_last_verified_at: datetime | None = None
    totp_enrollments: list[MfaTotpEnrollmentOut] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    mfa_challenges: list[MfaChallengeOut] = Field(
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


class UserMfaMethodsOut(BaseModel):
    totp_enrollments: list[MfaTotpEnrollmentOut] = Field(default_factory=list)
    pending_challenges: list[MfaChallengeOut] = Field(default_factory=list)


class PasswordChangeOut(BaseModel):
    ok: bool
    revoked_sessions: int = 0


class SessionBulkRevokeOut(BaseModel):
    revoked: int = 0


class DataExportOut(BaseModel):
    profile: dict[str, Any]
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    mfa_challenges: list[dict[str, Any]] = Field(default_factory=list)
    mfa_enrollments: list[dict[str, Any]] = Field(default_factory=list)
    access_logs: list[dict[str, Any]] = Field(default_factory=list)


class DataDeletionRequest(BaseModel):
    confirm: bool = Field(..., description="Explicit consent to remove personal data")


class DataDeletionOut(BaseModel):
    deleted: bool
    anonymized_email: EmailStr


class UserProfileUpdate(UserProfileBase, UserPreferencesBase, UserEducationBase):
    full_name: str | None = None
    email: EmailStr | None = None
    profile_detail: UserProfileBase | None = None
    preferences: UserPreferencesBase | None = None
    education_path: UserEducationBase | None = None


class GroupCreate(BaseModel):
    name: str
    course: int | None = None
    faculty: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    course: int | None = None
    faculty: str | None = None


class GroupOut(OrmModel):
    id: uuid.UUID
    name: str
    course: int | None = None
    faculty: str | None = None


class ScheduleBase(BaseModel):
    group_id: uuid.UUID
    subject: str
    teacher: str | None = None
    room: str | None = None
    weekday: str
    start_time: datetime
    end_time: datetime
    parity: str | None = "both"
    lesson_type: str | None = None


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    group_id: uuid.UUID | None = None
    subject: str | None = None
    teacher: str | None = None
    room: str | None = None
    weekday: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    parity: str | None = None
    lesson_type: str | None = None


class ScheduleOut(OrmModel, ScheduleBase):
    id: uuid.UUID
    lesson_type_display: str | None = None


class NewsCreate(BaseModel):
    title: SanitizedStr
    content: SafeRichText
    title_en: SanitizedInput = None
    content_en: SanitizedInput = None
    image_url: str | None = None


class NewsUpdate(BaseModel):
    title: SanitizedStr | None = None
    content: SafeRichText | None = None
    title_en: SanitizedInput = None
    content_en: SanitizedInput = None
    image_url: str | None = None


class NewsOut(OrmModel, NewsCreate):
    id: uuid.UUID
    created_at: datetime
    likes_count: int = 0
    comments_count: int = 0
    is_liked: bool = False

    image_url_optimized: str | None = None


class PaginatedNews(BaseModel):
    """Paginated news response with cursor-based pagination."""

    items: list[NewsOut]
    has_more: bool
    next_cursor: str | None = None


class StoryCreate(BaseModel):
    title: str
    title_en: SanitizedInput = None
    short_text: str
    short_text_en: SanitizedInput = None
    cover_url: SanitizedInput = None
    cta_url: SanitizedInput = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_expiration(self) -> StoryCreate:
        published = self.published_at
        expires = self.expires_at
        if expires is not None and published is not None and expires <= published:
            raise ValueError(translate("validation.stories.expires_after_publish"))
        return self


class StoryUpdate(BaseModel):
    title: str | None = None
    title_en: SanitizedInput = None
    short_text: str | None = None
    short_text_en: SanitizedInput = None
    cover_url: SanitizedInput = None
    cta_url: SanitizedInput = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate_expiration(self) -> StoryUpdate:
        provided = self.model_fields_set
        if "published_at" in provided and "expires_at" in provided:
            if self.published_at is not None and self.expires_at is not None:
                if self.expires_at <= self.published_at:
                    raise ValueError(
                        translate("validation.stories.expires_after_publish")
                    )
        return self


class StoryOut(OrmModel):
    id: uuid.UUID
    title: str
    title_en: str | None = None
    short_text: str
    short_text_en: str | None = None
    cover_url: str | None = None
    cta_url: str | None = None
    published_at: datetime
    expires_at: datetime
    is_active: bool
    created_by: str | Any | None = None
    created_at: datetime

    cover_url_optimized: str | None = None


class EventFileOut(OrmModel):
    id: uuid.UUID
    event_id: uuid.UUID
    file_url: str
    description: str | None = None


class EventCreate(BaseModel):
    title: CleanStr
    description: SafeRichText | None = None
    title_en: SanitizedInput = None
    description_en: SanitizedInput = None
    location: CleanStr | None = None
    location_en: SanitizedInput = None
    event_type: SanitizedInput = None
    event_type_en: SanitizedInput = None
    starts_at: datetime
    ends_at: datetime
    speaker: CleanStr | None = None
    image_url: str | None = None
    about: SafeRichText | None = None
    about_en: SanitizedInput = None

    @model_validator(mode="after")
    def _validate_time_order(self) -> EventCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError(translate("validation.events.end_after_start"))
        return self


class EventUpdate(BaseModel):
    title: CleanStr | None = None
    description: SafeRichText | None = None
    title_en: SanitizedInput = None
    description_en: SanitizedInput = None
    location: CleanStr | None = None
    location_en: SanitizedInput = None
    event_type: SanitizedInput = None
    event_type_en: SanitizedInput = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    speaker: CleanStr | None = None
    image_url: str | None = None
    about: SafeRichText | None = None
    about_en: SanitizedInput = None

    @model_validator(mode="after")
    def _validate_time_updates(self) -> EventUpdate:
        provided = self.model_fields_set
        starts_set = "starts_at" in provided
        ends_set = "ends_at" in provided
        if starts_set ^ ends_set:
            raise ValueError(translate("validation.events.times_required"))
        if starts_set or ends_set:
            if self.starts_at is None or self.ends_at is None:
                raise ValueError(translate("validation.events.times_required"))
            if self.ends_at <= self.starts_at:
                raise ValueError(translate("validation.events.end_after_start"))
        return self


class EventOut(OrmModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    title_en: str | None = None
    description_en: str | None = None
    location: str | None = None
    location_en: str | None = None
    event_type: str | None = None
    event_type_en: str | None = None
    starts_at: datetime
    ends_at: datetime
    created_by: str | Any
    created_at: datetime
    is_active: bool
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None
    about_en: str | None = None
    files: list[EventFileOut] = Field(
        default_factory=list, json_schema_extra={"default": []}
    )
    participant_count: int = 0
    is_registered: bool | None = None
    my_qr_token: str | None = None

    image_url_optimized: str | None = None


class PaginatedEvents(BaseModel):
    items: list[EventOut]
    total: int | None = None
    limit: int
    cursor: str | None = None
    next_cursor: str | None = None
    has_more: bool


class EventAttendanceCreate(BaseModel):
    event_id: uuid.UUID | int


class EventAttendanceOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    registered_at: datetime
    qr_token: str | None = None


class Token(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"


class TokenWithProfile(Token):
    user: UserOut
    session: SessionSigningKeyOut | None = None


class SessionSigningKeyOut(BaseModel):
    signing_key: str


class ActiveSessionOut(OrmModel):
    id: uuid.UUID
    user_id: uuid.UUID
    jti: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    last_seen_at: datetime | None = None
    mfa_required: bool = False
    mfa_completed_at: datetime | None = None
    mfa_method: str | None = None
    mfa_verified_at: datetime | None = None
    is_current: bool = False


class SpotifyAuthURL(BaseModel):
    url: str


class SpotifyNowPlayingOut(BaseModel):
    is_playing: bool
    progress_ms: int | None = None
    duration_ms: int | None = None
    track_id: str | None = None
    track_name: str | None = None
    artists: list[str] = Field(default_factory=list, json_schema_extra={"default": []})
    album_name: str | None = None
    album_image_url: str | None = None
    track_url: str | None = None
    preview_url: str | None = None
    fetched_at: datetime


class NotificationCreate(BaseModel):
    user_id: uuid.UUID
    title: str
    body: str | None = None
    title_en: SanitizedInput = None
    body_en: SanitizedInput = None
    type: SanitizedInput = None
    url: SanitizedInput = None


class NotificationOut(OrmModel):
    id: uuid.UUID
    title: str
    body: str | None = None
    title_en: SanitizedInput = None
    body_en: SanitizedInput = None
    type: SanitizedInput = None
    url: SanitizedInput = None
    created_at: datetime
    read: bool
    read_at: datetime | None = None


class NotificationsListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int
    has_more: bool
    next_cursor: str | None = None


class NotificationMarkReadIn(BaseModel):
    id: uuid.UUID | None = None
    ids: list[str | Any] | None = None


class NotificationDeadLetterJobOut(OrmModel):
    id: uuid.UUID
    kind: str
    record_id: uuid.UUID
    locale: str | None = None
    enqueued_at: datetime
    claimed_at: datetime | None = None
    attempts: int
    last_error: str | None = None
    next_retry_at: datetime | None = None


class NotificationDeadLetterListOut(BaseModel):
    items: list[NotificationDeadLetterJobOut]
    total: int


class _NotificationDeadLetterJobIds(BaseModel):
    job_ids: list[str | Any] = Field(min_length=1)

    @field_validator("job_ids")
    @classmethod
    def _ensure_unique(cls, value: list[str | Any]) -> list[str | Any]:
        normalized: list[str | Any] = []
        seen: set[str | Any] = set()
        for raw in value:
            parsed = raw  # No longer forcing int
            if parsed in seen:
                continue
            seen.add(parsed)
            normalized.append(parsed)
        if not normalized:
            raise ValueError("job_ids must contain at least one value")
        return normalized


class NotificationDeadLetterReplayIn(_NotificationDeadLetterJobIds):
    pass


class NotificationDeadLetterPurgeIn(_NotificationDeadLetterJobIds):
    pass


class FeatureFlagOut(BaseModel):
    name: str
    enabled: bool
    status: str = "active"
    description: str = ""
    percentage: int = 100
    allowed_users: list[str | Any] = Field(default_factory=list)
    allowed_groups: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpdateIn(BaseModel):
    enabled: bool | None = None
    status: str | None = None
    percentage: int | None = None
    description: str | None = None


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    actor_name: str | None = None
    subject_user_id: uuid.UUID | None = None
    subject_name: str | None = None
    resource_type: str
    resource_id: str | None = None
    action: str
    context: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    is_valid: bool


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    total: int
