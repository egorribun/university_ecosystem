from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


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
    full_name: str | None = None
    role: str | None = "student"
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


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=200)
    invite_code: str | None = None


class UserOut(OrmModel, UserBase):
    id: int
    is_active: bool
    spotify_is_connected: bool | None = None


class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    role: str | None = None
    group_id: int | None = None


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

    @model_validator(mode="before")
    def _validate_dnd(cls, data: Any) -> Any:
        raw = data.data if hasattr(data, "data") and hasattr(data, "context") else data

        payload = raw if isinstance(raw, dict) else {}

        enabled = payload.get("dnd_enabled")
        start = payload.get("dnd_start")
        end = payload.get("dnd_end")
        if enabled and (start is None or end is None):
            raise ValueError('Укажите время начала и окончания режима "Не беспокоить"')

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
    lesson_type: str | None = "Лекция"


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


class NewsCreate(BaseModel):
    title: str
    content: str
    image_url: str | None = None


class NewsOut(OrmModel, NewsCreate):
    id: int
    created_at: datetime


class EventFileOut(OrmModel):
    id: int
    event_id: int
    file_url: str
    description: str | None = None


class EventCreate(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    event_type: str | None = None
    starts_at: datetime
    ends_at: datetime
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    event_type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None


class EventOut(OrmModel):
    id: int
    title: str
    description: str | None = None
    location: str | None = None
    event_type: str | None = None
    starts_at: datetime
    ends_at: datetime
    created_by: int
    created_at: datetime
    is_active: bool
    speaker: str | None = None
    image_url: str | None = None
    about: str | None = None
    files: list[EventFileOut] = Field(default_factory=list)
    participant_count: int = 0
    is_registered: bool | None = None


class EventAttendanceCreate(BaseModel):
    event_id: int


class EventAttendanceOut(OrmModel):
    id: int
    user_id: int
    event_id: int
    registered_at: datetime
    qr_code: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
    type: str | None = None
    url: str | None = None


class NotificationOut(OrmModel):
    id: int
    title: str
    body: str | None = None
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
