"""Closure tests for runtime calls through protocol default stubs."""

from typing import Any

from app.core.protocols import DatabaseSession, UserAnalyticsServiceProtocol


def test_database_session_protocol_stub_methods_are_callable():
    class Session(DatabaseSession):
        pass

    session = Session()
    assert session.execute(None) is None
    assert session.commit() is None
    assert session.rollback() is None
    assert session.add(object()) is None
    assert session.flush() is None
    assert session.refresh(object()) is None


async def test_user_analytics_protocol_stub_methods_are_awaitable():
    class Analytics(UserAnalyticsServiceProtocol):
        pass

    service = Analytics()
    kwargs: dict[str, Any] = {"user_id": "user", "period_days": 7}

    assert await service.get_attendance_stats(**kwargs) is None
    assert await service.get_grade_stats(**kwargs) is None
    assert await service.get_participation_stats(**kwargs) is None
