"""Closure test for the bounded recent-event result path."""

from unittest.mock import AsyncMock

from app.services.fraud_detection_service import FraudDetectionService


async def test_get_recent_events_stops_at_requested_count():
    redis = AsyncMock()
    redis.xrevrange = AsyncMock(
        return_value=[
            (b"2-0", {b"user_id": b"u", b"severity": b"high"}),
            (b"1-0", {b"user_id": b"u", b"severity": b"low"}),
        ]
    )

    events = await FraudDetectionService(redis).get_recent_events(count=1)

    assert len(events) == 1
    assert events[0]["severity"] == "high"
