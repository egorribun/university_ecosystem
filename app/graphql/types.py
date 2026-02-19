"""GraphQL type definitions for the University Ecosystem API.

This module defines Strawberry GraphQL types that map to the domain models.
Types are designed to be flexible for client queries while maintaining
strong typing and documentation.
"""

from datetime import datetime

import strawberry


@strawberry.type(description="User profile information")
class UserType:
    id: strawberry.ID
    email: str
    full_name: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


@strawberry.type(description="News article")
class NewsType:
    id: strawberry.ID
    title: str
    content: str
    summary: str | None = None
    image_url: str | None = None
    author: UserType | None = None
    created_at: datetime
    updated_at: datetime | None = None
    likes_count: int = 0
    comments_count: int = 0


@strawberry.type(description="Event information")
class EventType:
    id: strawberry.ID
    title: str
    description: str | None = None
    location: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    is_active: bool = True
    image_url: str | None = None
    organizer: UserType | None = None
    attendees_count: int = 0
    max_attendees: int | None = None
    created_at: datetime


@strawberry.type(description="Schedule entry")
class ScheduleEntryType:
    id: strawberry.ID
    day_of_week: str
    time_start: str
    time_end: str
    subject: str
    teacher: str | None = None
    room: str | None = None
    type: str | None = None  # lecture, seminar, lab


@strawberry.type(description="Chat message")
class MessageType:
    id: strawberry.ID
    content: str
    sender: UserType
    created_at: datetime
    read_status: bool = False


@strawberry.type(description="Chat conversation")
class ChatType:
    id: strawberry.ID
    participants: list[UserType]
    last_message: MessageType | None = None
    unread_count: int = 0
    updated_at: datetime


@strawberry.type(description="Paginated list metadata")
class PageInfo:
    has_next_page: bool
    has_previous_page: bool = False
    total_count: int | None = None
    cursor: str | None = None


@strawberry.type(description="Paginated news list")
class NewsConnection:
    items: list[NewsType]
    page_info: PageInfo


@strawberry.type(description="Paginated events list")
class EventsConnection:
    items: list[EventType]
    page_info: PageInfo
