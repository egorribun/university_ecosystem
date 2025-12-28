"""Repository package initialization."""

from app.repositories.base import BaseRepository, ReadOnlyRepository
from app.repositories.event_repository import EventRepository, get_event_repository
from app.repositories.news_repository import NewsRepository, get_news_repository
from app.repositories.notification_repository import (
    NotificationRepository,
    get_notification_repository,
)
from app.repositories.session_repository import (
    SessionRepository,
    get_session_repository,
)
from app.repositories.story_repository import StoryRepository, get_story_repository
from app.repositories.unit_of_work import UnitOfWork, get_unit_of_work
from app.repositories.user_repository import UserRepository, get_user_repository

__all__ = [
    # Base
    "BaseRepository",
    "ReadOnlyRepository",
    # Repositories
    "UserRepository",
    "get_user_repository",
    "EventRepository",
    "get_event_repository",
    "NotificationRepository",
    "get_notification_repository",
    "NewsRepository",
    "get_news_repository",
    "StoryRepository",
    "get_story_repository",
    "SessionRepository",
    "get_session_repository",
    # Unit of Work
    "UnitOfWork",
    "get_unit_of_work",
]
