"""Unit tests for FraudDetectionService (MOD-4 / audit 2026-02-24).

Uses AsyncMock to simulate Redis client responses without a real Redis instance.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.fraud_detection_service import _STREAM_KEY, FraudDetectionService


@pytest.fixture
def mock_redis() -> Any:
    client = MagicMock()
    client.xadd = AsyncMock()
    client.xrevrange = AsyncMock(return_value=[])
    return client


@pytest.fixture
def service(mock_redis: Any) -> FraudDetectionService:
    return FraudDetectionService(redis_client=cast(Any, mock_redis))


class TestRecordEvent:
    async def test_calls_xadd_with_correct_stream_key(
        self, service: FraudDetectionService, mock_redis: AsyncMock
    ) -> None:
        await service.record_event({"user_id": "42", "severity": "high"})
        mock_redis.xadd.assert_awaited_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == _STREAM_KEY

    async def test_does_not_raise_on_redis_error(
        self, service: FraudDetectionService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xadd.side_effect = ConnectionError("Redis unavailable")
        # Must not propagate the exception — security events must not crash the app.
        await service.record_event({"user_id": "1", "severity": "high"})


class TestGetRecentEvents:
    async def test_returns_decoded_events(
        self, service: FraudDetectionService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xrevrange.return_value = [
            (b"1-0", {b"user_id": b"10", b"severity": b"high"}),
            (b"2-0", {b"user_id": b"11", b"severity": b"medium"}),
        ]
        events = await service.get_recent_events()
        assert len(events) == 2
        assert events[0]["user_id"] == "10"
        assert events[1]["severity"] == "medium"

    async def test_filters_by_user_id(
        self, service: FraudDetectionService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xrevrange.return_value = [
            (b"1-0", {b"user_id": b"42", b"severity": b"high"}),
            (b"2-0", {b"user_id": b"99", b"severity": b"low"}),
        ]
        events = await service.get_recent_events(user_id="42")
        assert len(events) == 1
        assert events[0]["user_id"] == "42"

    async def test_returns_empty_list_on_redis_error(
        self, service: FraudDetectionService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xrevrange.side_effect = ConnectionError("Redis unavailable")
        events = await service.get_recent_events()
        assert events == []


class TestCountRecentHighSeverity:
    async def test_counts_high_severity_events(
        self, service: FraudDetectionService, mock_redis: AsyncMock
    ) -> None:
        mock_redis.xrevrange.return_value = [
            (b"1-0", {b"user_id": b"5", b"severity": b"high"}),
            (b"2-0", {b"user_id": b"5", b"severity": b"high"}),
            (b"3-0", {b"user_id": b"5", b"severity": b"medium"}),
        ]
        count = await service.count_recent_high_severity(user_id="5")
        assert count == 2
