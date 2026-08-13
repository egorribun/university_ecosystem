from __future__ import annotations

import uuid
from datetime import datetime

from app.core.config import _NamespaceView
from app.core.config.database import DatabaseSettings
from app.models.dead_letter import DeadLetterJob
from app.models.domain_events import StoredEvent
from app.models.events import EventAttendance
from app.models.failed_outbox_events import FailedOutboxEvent
from app.models.grade import Grade
from app.models.news import News, NewsLike
from app.models.notifications import (
    Notification,
    NotificationDelivery,
    NotificationQueueJob,
    UserPushTopic,
)
from app.models.schedule import Group, Schedule
from app.models.spotify import SpotifyIntegration
from app.models.users import (
    EducationPath,
    InviteCode,
    User,
    UserPreferences,
    UserProfile,
    UserStats,
)
from app.models.vector_shard import VectorChunk


def test_remaining_model_reprs_are_mapped_in_mutmut_stats() -> None:
    """Exercise every model repr that is part of the full mutation universe."""

    identifier = uuid.uuid4()
    other_identifier = uuid.uuid4()
    timestamp = datetime(2026, 8, 13, 12, 30)

    assert repr(DeadLetterJob(id=7, job_type="email", status="failed")) == (
        "<DeadLetterJob(id=7, job_type='email', status='failed')>"
    )
    assert (
        repr(
            StoredEvent(
                id=identifier,
                event_type="UserCreated",
                aggregate_type="User",
                aggregate_id="user-1",
            )
        )
        == "<StoredEvent(type=UserCreated, aggregate=User:user-1)>"
    )
    assert repr(
        EventAttendance(id=identifier, user_id=other_identifier, event_id=identifier)
    ) == (
        f"<EventAttendance(id={identifier}, user_id={other_identifier}, "
        f"event_id={identifier})>"
    )
    assert repr(
        FailedOutboxEvent(
            event_type="TaskFailed",
            aggregate_type="User",
            aggregate_id="user-1",
            retry_count=2,
        )
    ) == (
        "<FailedOutboxEvent(event_type='TaskFailed', aggregate=User:user-1, retries=2)>"
    )
    assert repr(
        Grade(
            id=identifier,
            student_id=other_identifier,
            subject="mathematics",
            score=4.5,
        )
    ) == (
        f"<Grade(id={identifier}, student={other_identifier}, "
        "subject=mathematics, score=4.5)>"
    )
    assert repr(News(id=identifier, title="N" * 40, content="body")) == (
        f"<News(id={identifier}, title='{'N' * 30}...')>"
    )
    assert repr(
        NewsLike(id=identifier, news_id=identifier, user_id=other_identifier)
    ) == (
        f"<NewsLike(id={identifier}, news_id={identifier}, user_id={other_identifier})>"
    )
    assert (
        repr(
            Notification(
                id=identifier,
                user_id=other_identifier,
                title="T" * 30,
            )
        )
        == f"<Notification(id={identifier}, user_id={other_identifier}, title='{'T' * 20}...')>"
    )
    assert (
        repr(NotificationQueueJob(kind="news", record_id=identifier))
        == f"<NotificationQueueJob(kind='news', record_id={identifier})>"
    )
    assert (
        repr(NotificationDelivery(channel="push", status="delivered"))
        == "<NotificationDelivery(channel='push', status='delivered')>"
    )
    assert repr(UserPushTopic(user_id=identifier, topics=["news"])) == (
        f"<UserPushTopic(user_id={identifier}, topics=['news'])>"
    )
    assert repr(Group(id=identifier, name="Group A")) == (
        f"<Group(id={identifier}, name='Group A')>"
    )
    assert repr(
        Schedule(
            id=identifier,
            group_id=other_identifier,
            subject="S" * 30,
            start_time=timestamp,
        )
    ) == (
        f"<Schedule(id={identifier}, group_id={other_identifier}, "
        f"subject='{'S' * 20}...', starts={timestamp})>"
    )
    assert (
        repr(
            SpotifyIntegration(
                user_id=identifier,
                is_connected=True,
                is_playing=False,
            )
        )
        == f"<SpotifyIntegration(user_id={identifier}, connected=True, playing=False)>"
    )
    user = User(
        id=identifier,
        email="student@example.test",
        hashed_password="argon2id-hash",  # pragma: allowlist secret
        role="student",
    )
    assert repr(user) == f"<User(id={identifier}, role='student')>"
    assert repr(UserPreferences(user_id=identifier, dnd_enabled=True)) == (
        f"<UserPreferences(user_id={identifier}, dnd=True)>"
    )
    assert repr(UserProfile(user_id=identifier)) == (
        f"<UserProfile(user_id={identifier})>"
    )
    assert repr(EducationPath(user_id=identifier, program="Computer Science")) == (
        f"<EducationPath(user_id={identifier}, program='Computer Science')>"
    )
    assert repr(InviteCode(id=identifier, code="INVITE-1", is_used=False)) == (
        f"<InviteCode(id={identifier}, code='INVITE-1', used=False)>"
    )
    assert repr(UserStats(user_id=identifier)) == f"<UserStats(user_id={identifier})>"
    assert repr(
        VectorChunk(
            id=identifier,
            tenant_id=other_identifier,
            document_id="document-1",
            chunk_index=3,
        )
    ) == (
        f"<VectorChunk(id={identifier}, tenant_id={other_identifier}, "
        "doc=document-1, chunk=3)>"
    )
    namespace = _NamespaceView(object(), DatabaseSettings)
    assert repr(namespace) == "<_NamespaceView(DatabaseSettings)>"
