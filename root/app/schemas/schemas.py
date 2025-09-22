from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field

class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    @classmethod
    def from_orm(cls, obj):
        return cls.model_validate(obj)

class ForgotPasswordIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str
    password: str

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: Optional[str] = "student"
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

class UserCreate(UserBase):
    password: str
    invite_code: Optional[str] = None

class UserOut(OrmModel, UserBase):
    id: int
    is_active: bool
    spotify_is_connected: Optional[bool] = None

class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
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
    lesson_type: Optional[str] = "Лекция"

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

class NewsCreate(BaseModel):
    title: str
    content: str
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
    location: Optional[str] = None
    event_type: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    speaker: Optional[str] = None
    image_url: Optional[str] = None
    about: Optional[str] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    event_type: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    speaker: Optional[str] = None
    image_url: Optional[str] = None
    about: Optional[str] = None

class EventOut(OrmModel):
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    event_type: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    created_by: int
    created_at: datetime
    is_active: bool
    speaker: Optional[str] = None
    image_url: Optional[str] = None
    about: Optional[str] = None
    files: List[EventFileOut] = Field(default_factory=list)
    participant_count: int = 0
    is_registered: Optional[bool] = None

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
    type: Optional[str] = None
    url: Optional[str] = None

class NotificationOut(OrmModel):
    id: int
    title: str
    body: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    created_at: datetime
    read: bool
    read_at: Optional[datetime] = None

class NotificationsListOut(BaseModel):
    items: List[NotificationOut]
    unread_count: int
    has_more: bool

class NotificationMarkReadIn(BaseModel):
    id: Optional[int] = None
    ids: Optional[List[int]] = None