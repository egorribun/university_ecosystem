"""Closure test for the bounded recent-event result path."""

from unittest.mock import AsyncMock, MagicMock

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


async def test_get_recent_events_uses_time_window_and_user_filter():
    redis = AsyncMock()
    redis.xrevrange = AsyncMock(
        return_value=[
            (b"2-0", {b"user_id": b"other", b"severity": b"high"}),
            (b"1-0", {b"user_id": b"u", b"severity": b"low"}),
        ]
    )

    events = await FraudDetectionService(redis).get_recent_events(
        user_id="u", count=2, within_seconds=10
    )

    assert events == [{"user_id": "u", "severity": "low"}]
    kwargs = redis.xrevrange.await_args.kwargs
    assert kwargs["min"].endswith("-0")
    assert kwargs["count"] == 20


async def test_record_high_event_without_user_skips_sorted_set_update():
    redis = AsyncMock()
    redis.xadd = AsyncMock()
    redis.pipeline = MagicMock()

    await FraudDetectionService(redis).record_event({"severity": "high"})

    redis.xadd.assert_awaited_once()
    redis.pipeline.assert_not_called()


async def test_count_high_severity_falls_back_to_stream_on_redis_error():
    redis = AsyncMock()
    redis.zcount = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    service = FraudDetectionService(redis)
    service.get_recent_events = AsyncMock(
        return_value=[
            {"severity": "high"},
            {"severity": "low"},
            {"severity": "high"},
        ]
    )

    count = await service.count_recent_high_severity("u", within_seconds=30)

    assert count == 2
    service.get_recent_events.assert_awaited_once_with(
        user_id="u", count=500, within_seconds=30
    )
