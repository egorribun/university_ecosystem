from __future__ import annotations

import uuid
from datetime import datetime

from app.models.events import Event, EventFile
from app.models.news import NewsComment


def test_event_repr_includes_identity_title_and_start_time() -> None:
    """Keep the Event repr mapped in the mutmut population."""

    event_id = uuid.uuid4()
    starts_at = datetime(2026, 8, 13, 12, 30)
    record = Event(id=event_id, title="A" * 30, starts_at=starts_at)

    assert repr(record) == (
        f"<Event(id={event_id}, title='AAAAAAAAAAAAAAAAAAAA...', "
        f"starts_at={starts_at})>"
    )


def test_event_file_repr_includes_identity_and_truncated_url() -> None:
    """Keep the EventFile repr mapped in the mutmut population."""

    event_id = uuid.uuid4()
    file_id = uuid.uuid4()
    record = EventFile(
        id=file_id,
        event_id=event_id,
        file_url="https://cdn.example.test/uploads/event-handout.pdf",
    )

    assert repr(record) == (
        f"<EventFile(id={file_id}, eid={event_id}, url='https://cdn.example....')>"
    )


def test_news_comment_repr_includes_identity_and_truncated_content() -> None:
    """Keep the NewsComment repr mapped in the mutmut population."""

    comment_id = uuid.uuid4()
    news_id = uuid.uuid4()
    record = NewsComment(
        id=comment_id,
        news_id=news_id,
        content="B" * 30,
    )

    assert repr(record) == (
        f"<NewsComment(id={comment_id}, news_id={news_id}, "
        "content='BBBBBBBBBBBBBBBBBBBB...')>"
    )
