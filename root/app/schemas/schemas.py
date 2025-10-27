from datetime import datetime, time
from typing import Any, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.localization import translate
from app.models.enums import UserRole


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm(cls, obj):
        return cls.model_validate(obj)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class UserEmailChangeIn(BaseModel):
    email: EmailStr
    password: str


class UserPasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.STUDENT
    group_id: Optional[int] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    about: Optional[str] = None
    record_book_number: Optional[str] = None
    status: Optional[str] = None
    institute: Optional[str] = None
    course: Optional[str] = None
    education_level: Optional[str] = None
    track: Optional[str] = None
    program: Optional[str] = None
    telegram: Optional[str] = None
    achievements: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    spotify_connected: bool = False
    spotify_display_name: Optional[str] = None
    dnd_enabled: bool = False
    dnd_start: Optional[time] = None
    dnd_end: Optional[time] = None
    timezone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=200)
    invite_code: Optional[str] = None


class MfaTotpEnrollmentOut(OrmModel):
    id: int
    user_id: int
    label: Optional[str] = None
    is_active: bool
    confirmed_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime


class MfaWebAuthnCredentialOut(OrmModel):
    id: int
    user_id: int
    credential_id: str
    device_name: Optional[str] = None
    sign_count: int
    transports: Optional[list[str]] = None
    backed_up: bool
    clone_warning: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    is_active: bool


class MfaRecoveryCodeOut(OrmModel):
    id: int
    user_id: int
    used_at: Optional[datetime] = None
    created_at: datetime
    label: Optional[str] = None


class MfaChallengeOut(OrmModel):
    id: int
    user_id: int
    session_id: Optional[int] = None
    challenge_type: str
    token: str
    expires_at: datetime
    consumed_at: Optional[datetime] = None
    created_at: datetime
    payload: Optional[dict[str, Any]] = None


class UserOut(OrmModel, UserBase):
    id: int
    is_active: bool
    spotify_is_connected: Optional[bool] = None
    mfa_required: bool = False
    mfa_default_method: Optional[str] = None
    mfa_last_verified_at: Optional[datetime] = None
    mfa_recovery_codes_generated_at: Optional[datetime] = None
    totp_enrollments: List[MfaTotpEnrollmentOut] = Field(default_factory=list)
    webauthn_credentials: List[MfaWebAuthnCredentialOut] = Field(default_factory=list)
    recovery_codes: List[MfaRecoveryCodeOut] = Field(default_factory=list)
    mfa_challenges: List[MfaChallengeOut] = Field(default_factory=list)


class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    group_id: Optional[int] = None
    reset_mfa: Optional[bool] = None


class UserMfaMethodsOut(BaseModel):
    totp_enrollments: List[MfaTotpEnrollmentOut] = Field(default_factory=list)
    webauthn_credentials: List[MfaWebAuthnCredentialOut] = Field(default_factory=list)
    recovery_codes: List[MfaRecoveryCodeOut] = Field(default_factory=list)
    pending_challenges: List[MfaChallengeOut] = Field(default_factory=list)


class PasswordChangeOut(BaseModel):
    ok: bool
    revoked_sessions: int = 0


class SessionBulkRevokeOut(BaseModel):
    revoked: int = 0


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    about: Optional[str] = None
    record_book_number: Optional[str] = None
    status: Optional[str] = None
    institute: Optional[str] = None
    course: Optional[str] = None
    education_level: Optional[str] = None
    track: Optional[str] = None
    program: Optional[str] = None
    telegram: Optional[str] = None
    achievements: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    dnd_enabled: Optional[bool] = None
    dnd_start: Optional[time] = None
    dnd_end: Optional[time] = None
    timezone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: Any) -> Optional[str]:
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


class GroupCreate(BaseModel):
    name: str
    course: Optional[int] = None
    faculty: Optional[str] = None


class GroupOut(OrmModel):
    id: int
    name: str
    course: Optional[int] = None
    faculty: Optional[str] = None


class ScheduleBase(BaseModel):
    group_id: int
    subject: str
    teacher: Optional[str] = None
    room: Optional[str] = None
    weekday: str
    start_time: datetime
    end_time: datetime
    parity: Optional[str] = "both"
    lesson_type: Optional[str] = None


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    group_id: Optional[int] = None
    subject: Optional[str] = None
    teacher: Optional[str] = None
    room: Optional[str] = None
    weekday: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    parity: Optional[str] = None
    lesson_type: Optional[str] = None


class ScheduleOut(OrmModel, ScheduleBase):
    id: int
    lesson_type_display: Optional[str] = None


class NewsCreate(BaseModel):
    title: str
    content: str
    title_en: Optional[str] = None
    content_en: Optional[str] = None
    image_url: Optional[str] = None


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    title_en: Optional[str] = None
    content_en: Optional[str] = None
    image_url: Optional[str] = None


class NewsOut(OrmModel, NewsCreate):
    id: int
    created_at: datetime


class StoryCreate(BaseModel):
    title: str
    title_en: Optional[str] = None
    short_text: str
    short_text_en: Optional[str] = None
    cover_url: Optional[str] = None
    cta_url: Optional[str] = None
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

    @field_validator("title_en", "short_text_en", "cover_url", "cta_url", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def _validate_expiration(self):  # type: ignore[override]
        published = self.published_at
        expires = self.expires_at
        if expires is not None and published is not None and expires <= published:
            raise ValueError(translate("validation.stories.expires_after_publish"))
        return self


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    title_en: Optional[str] = None
    short_text: Optional[str] = None
    short_text_en: Optional[str] = None
    cover_url: Optional[str] = None
    cta_url: Optional[str] = None
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None

    @field_validator("title_en", "short_text_en", "cover_url", "cta_url", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def _validate_expiration(self):  # type: ignore[override]
        provided = self.model_fields_set
        if "published_at" in provided and "expires_at" in provided:
            if self.published_at is not None and self.expires_at is not None:
                if self.expires_at <= self.published_at:
                    raise ValueError(
                        translate("validation.stories.expires_after_publish")
                    )
        return self


class StoryOut(OrmModel):
    id: int
    title: str
    title_en: Optional[str] = None
    short_text: str
    short_text_en: Optional[str] = None
    cover_url: Optional[str] = None
    cta_url: Optional[str] = None
    published_at: datetime
    expires_at: datetime
    is_active: bool
    created_by: Optional[int] = None
    created_at: datetime


class EventFileOut(OrmModel):
    id: int
    event_id: int
    file_url: str
    description: Optional[str] = None


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    title_en: Optional[str] = None
    description_en: Optional[str] = None
    location: Optional[str] = None
    location_en: Optional[str] = None
    event_type: Optional[str] = None
    event_type_en: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    speaker: Optional[str] = None
    image_url: Optional[str] = None
    about: Optional[str] = None
    about_en: Optional[str] = None

    @model_validator(mode="after")
    def _validate_time_order(self):  # type: ignore[override]
        if self.ends_at <= self.starts_at:
            raise ValueError(translate("validation.events.end_after_start"))
        return self


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    title_en: Optional[str] = None
    description_en: Optional[str] = None
    location: Optional[str] = None
    location_en: Optional[str] = None
    event_type: Optional[str] = None
    event_type_en: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    speaker: Optional[str] = None
    image_url: Optional[str] = None
    about: Optional[str] = None
    about_en: Optional[str] = None

    @model_validator(mode="after")
    def _validate_time_updates(self):  # type: ignore[override]
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
    id: int
    title: str
    description: Optional[str] = None
    title_en: Optional[str] = None
    description_en: Optional[str] = None
    location: Optional[str] = None
    location_en: Optional[str] = None
    event_type: Optional[str] = None
    event_type_en: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    created_by: int
    created_at: datetime
    is_active: bool
    speaker: Optional[str] = None
    image_url: Optional[str] = None
    about: Optional[str] = None
    about_en: Optional[str] = None
    files: List[EventFileOut] = Field(default_factory=list)
    participant_count: int = 0
    is_registered: Optional[bool] = None
    my_qr_token: Optional[str] = None


class PaginatedEvents(BaseModel):
    items: List[EventOut]
    total: int
    limit: int
    cursor: Optional[str] = None
    next_cursor: Optional[str] = None
    has_more: bool


class EventAttendanceCreate(BaseModel):
    event_id: int


class EventAttendanceOut(OrmModel):
    id: int
    user_id: int
    event_id: int
    registered_at: datetime
    qr_token: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionSigningKeyOut(BaseModel):
    signing_key: str


class ActiveSessionOut(OrmModel):
    id: int
    user_id: int
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
    progress_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    track_id: Optional[str] = None
    track_name: Optional[str] = None
    artists: List[str] = Field(default_factory=list)
    album_name: Optional[str] = None
    album_image_url: Optional[str] = None
    track_url: Optional[str] = None
    preview_url: Optional[str] = None
    fetched_at: datetime


class NotificationCreate(BaseModel):
    user_id: int
    title: str
    body: Optional[str] = None
    title_en: Optional[str] = None
    body_en: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None


class NotificationOut(OrmModel):
    id: int
    title: str
    body: Optional[str] = None
    title_en: Optional[str] = None
    body_en: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    created_at: datetime
    read: bool
    read_at: Optional[datetime] = None


class NotificationsListOut(BaseModel):
    items: List[NotificationOut]
    unread_count: int
    has_more: bool
    next_cursor: Optional[str] = None


class NotificationMarkReadIn(BaseModel):
    id: Optional[int] = None
    ids: Optional[List[int]] = None


class NotificationDeadLetterJobOut(OrmModel):
    id: int
    kind: str
    record_id: int
    locale: Optional[str] = None
    enqueued_at: datetime
    claimed_at: Optional[datetime] = None
    attempts: int
    last_error: Optional[str] = None
    next_retry_at: Optional[datetime] = None


class NotificationDeadLetterListOut(BaseModel):
    items: List[NotificationDeadLetterJobOut]
    total: int


class _NotificationDeadLetterJobIds(BaseModel):
    job_ids: List[int] = Field(min_length=1)

    @field_validator("job_ids")
    @classmethod
    def _ensure_positive_unique(cls, value: List[int]) -> List[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for raw in value:
            try:
                parsed = int(raw)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
                raise ValueError("job_ids must contain integers") from exc
            if parsed <= 0:
                raise ValueError("job_ids must be positive integers")
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
