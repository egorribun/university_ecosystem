"""Coverage tests for app/services/analytics.py (testing session 10).

Pure-fn tests for the Polars _compute_* helpers + AsyncMock-repo tests for the
async wrappers (get_news_repository / get_event_repository are module-level
imports at analytics.py:25-26 — monkeypatchable).

IMPORTANT: get_user_activity is tested with an AsyncMock session ONLY — its raw
SQL references the table name `event_attendees` while the real table is
`event_attendance` (app/models/events.py:126); running it against a real DB
would fail. The mismatch is filed as a follow-up fix (session 11), out of scope
for this test-only session.

shutdown() is exercised against a throwaway ThreadPoolExecutor monkeypatched in
so the shared module pool stays alive for sibling tests.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.analytics as analytics_module
from app.services.analytics import AnalyticsService, get_analytics_service, shutdown

NEWS_COLUMNS = ["id", "title", "likes_count", "comments_count", "date"]
EVENT_COLUMNS = ["id", "title", "location", "attendees_count", "max_attendees"]


def _news_rows() -> list[tuple]:
    return [
        ("n1", "First", 10, 2, "2026-06-01"),
        ("n2", "Second", 5, 1, "2026-06-01"),
        ("n3", "Third", 20, 0, "2026-06-02"),
    ]


def _event_rows() -> list[tuple]:
    return [
        ("e1", "Hackathon", "Hall A", 30, 50),
        ("e2", "Lecture", "Hall B", 10, 100),
        ("e3", "Meetup", "Hall A", 25, 40),
    ]


@pytest.fixture
def svc() -> AnalyticsService:
    return AnalyticsService()


# ------------------------------------------------------------ pure compute


def test_compute_news_stats(svc: AnalyticsService) -> None:
    stats = svc._compute_news_stats(_news_rows(), NEWS_COLUMNS)
    assert stats["total"] == 3
    assert stats["total_likes"] == 35
    assert stats["total_comments"] == 3
    by_date = {entry["date"]: entry for entry in stats["by_date"]}
    assert by_date["2026-06-01"]["count"] == 2
    assert by_date["2026-06-01"]["total_likes"] == 15
    assert by_date["2026-06-02"]["total_comments"] == 0
    assert stats["top_liked"][0]["id"] == "n3"  # sorted by likes desc
    assert stats["top_liked"][0]["likes_count"] == 20


def test_compute_events_stats(svc: AnalyticsService) -> None:
    stats = svc._compute_events_stats(_event_rows(), EVENT_COLUMNS)
    assert stats["total"] == 3
    assert stats["total_attendees"] == 65
    assert stats["by_location"][0]["location"] == "Hall A"  # 55 attendees
    assert stats["by_location"][0]["event_count"] == 2
    assert stats["by_location"][0]["total_attendees"] == 55
    assert stats["popular"][0]["id"] == "e1"
    assert stats["popular"][0]["max_attendees"] == 50


# -------------------------------------------------------- async wrappers


async def test_get_news_stats_empty(
    svc: AnalyticsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = MagicMock()
    repo.get_analytics_data = AsyncMock(return_value=([], []))
    monkeypatch.setattr(
        analytics_module, "get_news_repository", MagicMock(return_value=repo)
    )
    result = await svc.get_news_stats(AsyncMock())
    assert result == {"total": 0, "by_date": [], "top_liked": []}


async def test_get_news_stats_with_rows(
    svc: AnalyticsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = MagicMock()
    repo.get_analytics_data = AsyncMock(return_value=(_news_rows(), NEWS_COLUMNS))
    factory = MagicMock(return_value=repo)
    monkeypatch.setattr(analytics_module, "get_news_repository", factory)
    session = AsyncMock()
    result = await svc.get_news_stats(session, start_date=None, end_date=None)
    assert result["total"] == 3
    assert result["total_likes"] == 35
    factory.assert_called_once_with(session)


async def test_get_events_stats_empty(
    svc: AnalyticsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = MagicMock()
    repo.get_analytics_data = AsyncMock(return_value=([], []))
    monkeypatch.setattr(
        analytics_module, "get_event_repository", MagicMock(return_value=repo)
    )
    result = await svc.get_events_stats(AsyncMock())
    assert result == {"total": 0, "by_location": [], "popular": []}


async def test_get_events_stats_with_rows(
    svc: AnalyticsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = MagicMock()
    repo.get_analytics_data = AsyncMock(return_value=(_event_rows(), EVENT_COLUMNS))
    monkeypatch.setattr(
        analytics_module, "get_event_repository", MagicMock(return_value=repo)
    )
    result = await svc.get_events_stats(AsyncMock(), start_date=None)
    assert result["total"] == 3
    assert result["popular"][0]["title"] == "Hackathon"


async def test_get_user_activity_mocked_session(svc: AnalyticsService) -> None:
    """AsyncMock session ONLY — the raw SQL names a non-existent table
    (`event_attendees` vs real `event_attendance`); see module docstring."""
    rows = [("news_created", 5), ("events_attended", 2), ("messages_sent", 7)]
    result_proxy = MagicMock()
    result_proxy.fetchall.return_value = rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_proxy)
    result = await svc.get_user_activity(session, uuid.uuid4())
    assert result == {"news_created": 5, "events_attended": 2, "messages_sent": 7}
    session.execute.assert_awaited_once()


# ------------------------------------------------------- factory + shutdown


def test_get_analytics_service_returns_instance() -> None:
    instance = get_analytics_service()
    assert isinstance(instance, AnalyticsService)
    assert instance._database_url is None


def test_init_with_database_url() -> None:
    assert AnalyticsService("postgres://x")._database_url == "postgres://x"


async def test_shutdown_uses_module_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    throwaway = ThreadPoolExecutor(max_workers=1, thread_name_prefix="throwaway")
    monkeypatch.setattr(analytics_module, "_executor", throwaway)
    await shutdown()
    assert throwaway._shutdown is True
