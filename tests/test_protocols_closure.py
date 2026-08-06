"""Closure tests for protocol defaults and user identifier normalization."""

import uuid
from typing import Any

import pytest

from app.core.protocols import (
    DatabaseSession,
    UserAnalyticsServiceProtocol,
    extract_user_id,
)


def test_extract_user_id_accepts_uuid_string_uuid_and_object_id():
    value = uuid.uuid4()

    assert extract_user_id(str(value)) == value
    assert extract_user_id(value) == value
    assert extract_user_id(type("User", (), {"id": value})()) == value


def test_extract_user_id_rejects_malformed_string_with_context():
    with pytest.raises(ValueError, match="extract_user_id"):
        extract_user_id("not-a-uuid")


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
