"""Grade history and cache contracts using persisted grades and public calls."""

from datetime import UTC, datetime, timedelta

import pytest

import app.models as models
from app.deps.cache import MemoryCache
from app.services.stats_cache import invalidate_user_stats_cache
from app.services.user import analytics_service
from app.services.user.analytics_service import UserAnalyticsService

NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_analytics_clock(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(analytics_service, "datetime", FixedDatetime)


@pytest.mark.asyncio
async def test_grade_summary_rounds_period_values_and_projects_exact_recent_dates(
    db_session, user_factory
):
    user = await user_factory()
    other = await user_factory()
    for student, subject, days, score in [
        (user, "Math", 1, 4),
        (user, "Physics", 2, 4),
        (user, "Literature", 30, 3),
        (user, "Previous A", 31, 5),
        (user, "Previous B", 40, 4),
        (user, "Previous C", 60, 4),
        (user, "Not in closed window", 0, 1),
        (user, "Too old", 61, 1),
        (other, "Other student", 1, 1),
    ]:
        db_session.add(
            models.Grade(
                student_id=student.id,
                subject=subject,
                score=score,
                created_at=NOW - timedelta(days=days),
            )
        )
    await db_session.flush()

    result = await UserAnalyticsService(db_session).get_grade_stats(
        user_id=user.id, period_days=30, period_key=" MONTH ", skip_cache=True
    )
    assert result == {
        "average": 3.67,
        "total_grades": 3,
        "scale": "5",
        "trend": -0.67,
        "period_key": "month",
        "recent": [
            {
                "course": "Math",
                "score": 4.0,
                "max": None,
                "date": "2026-09-29T12:00:00+00:00",
            },
            {
                "course": "Physics",
                "score": 4.0,
                "max": None,
                "date": "2026-09-28T12:00:00+00:00",
            },
            {
                "course": "Literature",
                "score": 3.0,
                "max": None,
                "date": "2026-08-31T12:00:00+00:00",
            },
        ],
    }


@pytest.mark.asyncio
async def test_grade_cache_honors_student_period_bypass_and_public_invalidation(
    db_session, user_factory
):
    user = await user_factory()
    other = await user_factory()
    service = UserAnalyticsService(db_session)
    cache = MemoryCache()
    empty = await service.get_grade_stats(user_id=user.id, period_days=7, cache=cache)
    assert empty["period_key"] == "7d"
    assert empty["total_grades"] == 0
    db_session.add(
        models.Grade(
            student_id=user.id,
            subject="New grade",
            score=5,
            created_at=NOW - timedelta(days=1),
        )
    )
    await db_session.flush()

    assert (
        await service.get_grade_stats(user_id=user.id, period_days=7, cache=cache)
        == empty
    )
    fresh = await service.get_grade_stats(
        user_id=user.id, period_days=7, cache=cache, skip_cache=True
    )
    assert fresh["average"] == 5.0
    assert fresh["total_grades"] == 1
    assert (
        await service.get_grade_stats(user_id=user.id, period_days=7, cache=cache)
        == empty
    )
    named = await service.get_grade_stats(
        user_id=user.id, period_days=7, period_key=" WEEK ", cache=cache
    )
    assert named["period_key"] == "week"
    assert named["total_grades"] == 1
    other_result = await service.get_grade_stats(
        user_id=other.id, period_days=7, period_key="week", cache=cache
    )
    assert other_result["total_grades"] == 0
    await invalidate_user_stats_cache(user_ids=user.id, period_keys=["7d"], cache=cache)
    refreshed = await service.get_grade_stats(
        user_id=user.id, period_days=7, cache=cache
    )
    assert refreshed["total_grades"] == 1
