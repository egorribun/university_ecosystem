from datetime import datetime, time
from typing import Any
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


class UserEmailConfirmIn(BaseModel):
    token: str


class UserPasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: UserRole = UserRole.STUDENT
    group_id: int | None = None
    avatar_url: str | None = None
    cover_url: str | None = None
    about: str | None = None
    record_book_number: str | None = None
    status: str | None = None
    institute: str | None = None
    course: str | None = None
    education_level: str | None = None
    track: str | None = None
    program: str | None = None
    telegram: str | None = None
    achievements: str | None = None
    department: str | None = None
    position: str | None = None
    spotify_connected: bool = False
    spotify_display_name: str | None = None
    dnd_enabled: bool = False
    dnd_start: time | None = None
    dnd_end: time | None = None
    timezone: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=200)
    invite_code: str | None = None


class MfaTotpEnrollmentOut(OrmModel):
    id: int
    user_id: int
    label: str | None = None
    is_active: bool
    confirmed_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class MfaRecoveryCodeOut(OrmModel):
    id: int
    user_id: int
    used_at: datetime | None = None
    created_at: datetime
    label: str | None = None


class MfaChallengeOut(OrmModel):
    id: int
    user_id: int
    session_id: int | None = None
    challenge_type: str
    token: str
    expires_at: datetime
    consumed_at: datetime | None = None
    created_at: datetime
    payload: dict[str, Any] | None = None
    attempt_count: int = 0


class MfaFactorStatusOut(BaseModel):
    disabled: bool
    mfa_default_method: str | None = None
    mfa_required: bool = False


class UserOut(OrmModel, UserBase):
    id: int
    is_active: bool
    pending_email: EmailStr | None = None
    spotify_is_connected: bool | None = None
    mfa_required: bool = False
    mfa_default_method: str | None = None
    mfa_last_verified_at: datetime | None = None
    mfa_recovery_codes_generated_at: datetime | None = None
    totp_enrollments: list[MfaTotpEnrollmentOut] = Field(default_factory=list)
    recovery_codes: list[MfaRecoveryCodeOut] = Field(default_factory=list)
    mfa_challenges: list[MfaChallengeOut] = Field(default_factory=list)


class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    role: UserRole | None = None
    group_id: int | None = None
    reset_mfa: bool | None = None


class UserMfaMethodsOut(BaseModel):
    totp_enrollments: list[MfaTotpEnrollmentOut] = Field(default_factory=list)
    recovery_codes: list[MfaRecoveryCodeOut] = Field(default_factory=list)
    pending_challenges: list[MfaChallengeOut] = Field(default_factory=list)


class PasswordChangeOut(BaseModel):
    ok: bool
    revoked_sessions: int = 0


class SessionBulkRevokeOut(BaseModel):
    revoked: int = 0


class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    about: str | None = None
    record_book_number: str | None = None
    status: str | None = None
    institute: str | None = None
    course: str | None = None
    education_level: str | None = None
    track: str | None = None
    program: str | None = None
    telegram: str | None = None
    achievements: str | None = None
    department: str | None = None
    position: str | None = None
    dnd_enabled: bool | None = None
    dnd_start: time | None = None
    dnd_end: time | None = None
    timezone: str | None = None

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
    course: int | None = None
    faculty: str | None = None


class GroupOut(OrmModel):
    id: int
    name: str
    course: int | None = None
    faculty: str | None = None


class ScheduleBase(BaseModel):
    group_id: int
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
    group_id: int | None = None
    subject: str | None = None
    teacher: str | None = None
    room: str | None = None
    weekday: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    parity: str | None = None
    lesson_type: str | None = None


class ScheduleOut(OrmModel, ScheduleBase):
    id: int
    lesson_type_display: str | None = None


class NewsCreate(BaseModel):
    title: str
    content: str
    title_en: str | None = None
    content_en: str | None = None
    image_url: str | None = None


class NewsUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    title_en: str | None = None
    content_en: str | None = None
    image_url: str | None = None


class NewsOut(OrmModel, NewsCreate):
    id: int
    created_at: datetime


class StoryCreate(BaseModel):
    title: str
    title_en: str | None = None
    short_text: str
    short_text_en: str | None = None
    cover_url: str | None = None
    cta_url: str | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True

    @field_validator("title_en", "short_text_en", "cover_url", "cta_url", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> str | None:
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
    title: str | None = None
    title_en: str | None = None
    short_text: str | None = None
    short_text_en: str | None = None
    cover_url: str | None = None
    cta_url: str | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None

    @field_validator("title_en", "short_text_en", "cover_url", "cta_url", mode="before")
    @classmethod
    def _strip_optional(cls, value: Any) -> str | None:
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
    title_en: str | None = None
    short_text: str
    short_text_en: str | None = None
    cover_url: str | None = None
    cta_url: str | None = None
    published_at: datetime
    expires_at: datetime
    is_active: bool
    created_by: int | None = None
    created_at: datetime


class EventFileOut(OrmModel):
    id: int
    event_id: int
    file_url: str
    description: str | None = None


class EventCreate(BaseModel):
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
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None
    about_en: str | None = None

    @model_validator(mode="after")
    def _validate_time_order(self):  # type: ignore[override]
        if self.ends_at <= self.starts_at:
            raise ValueError(translate("validation.events.end_after_start"))
        return self


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    title_en: str | None = None
    description_en: str | None = None
    location: str | None = None
    location_en: str | None = None
    event_type: str | None = None
    event_type_en: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None
    about_en: str | None = None

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
    description: str | None = None
    title_en: str | None = None
    description_en: str | None = None
    location: str | None = None
    location_en: str | None = None
    event_type: str | None = None
    event_type_en: str | None = None
    starts_at: datetime
    ends_at: datetime
    created_by: int
    created_at: datetime
    is_active: bool
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None
    about_en: str | None = None
    files: list[EventFileOut] = Field(default_factory=list)
    participant_count: int = 0
    is_registered: bool | None = None
    my_qr_token: str | None = None


class PaginatedEvents(BaseModel):
    items: list[EventOut]
    total: int | None = None
    limit: int
    cursor: str | None = None
    next_cursor: str | None = None
    has_more: bool


class EventAttendanceCreate(BaseModel):
    event_id: int


class EventAttendanceOut(OrmModel):
    id: int
    user_id: int
    event_id: int
    registered_at: datetime
    qr_token: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenWithProfile(Token):
    user: UserOut
    session: "SessionSigningKeyOut | None" = None


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
    progress_ms: int | None = None
    duration_ms: int | None = None
    track_id: str | None = None
    track_name: str | None = None
    artists: list[str] = Field(default_factory=list)
    album_name: str | None = None
    album_image_url: str | None = None
    track_url: str | None = None
    preview_url: str | None = None
    fetched_at: datetime


class NotificationCreate(BaseModel):
    user_id: int
    title: str
    body: str | None = None
    title_en: str | None = None
    body_en: str | None = None
    type: str | None = None
    url: str | None = None


class NotificationOut(OrmModel):
    id: int
    title: str
    body: str | None = None
    title_en: str | None = None
    body_en: str | None = None
    type: str | None = None
    url: str | None = None
    created_at: datetime
    read: bool
    read_at: datetime | None = None


class NotificationsListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int
    has_more: bool
    next_cursor: str | None = None


class NotificationMarkReadIn(BaseModel):
    id: int | None = None
    ids: list[int] | None = None


class NotificationDeadLetterJobOut(OrmModel):
    id: int
    kind: str
    record_id: int
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
    job_ids: list[int] = Field(min_length=1)

    @field_validator("job_ids")
    @classmethod
    def _ensure_positive_unique(cls, value: list[int]) -> list[int]:
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
