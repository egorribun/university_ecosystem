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


class UserOut(OrmModel, UserBase):
    id: int
    is_active: bool
    spotify_is_connected: Optional[bool] = None


class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    group_id: Optional[int] = None


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
            raise ValueError(translate("validation.timezone.invalid")) from exc
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
    my_qr_code: Optional[str] = None


class PaginatedEvents(BaseModel):
    items: List[EventOut]
    total: int
    limit: int
    cursor: int
    next_cursor: Optional[int] = None
    has_more: bool


class EventAttendanceCreate(BaseModel):
    event_id: int


class EventAttendanceOut(OrmModel):
    id: int
    user_id: int
    event_id: int
    registered_at: datetime
    qr_code: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
