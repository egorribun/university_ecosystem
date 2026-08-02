"""Branch closure tests for event retry middleware."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.core.event_retry as retry_module
from app.core.event_retry import EventRetryExhausted, RetryMiddleware, with_retry


def test_exhausted_error_keeps_event_error_and_attempt_count():
    event = SimpleNamespace(event_type="retry.event")
    original = RuntimeError("boom")

    error = EventRetryExhausted(event, original, 4)

    assert error.event is event
    assert error.original_error is original
    assert error.attempts == 4
    assert str(error) == "Event retry.event failed after 4 attempts: boom"


def test_delay_applies_jitter_and_maximum_cap(monkeypatch):
    middleware = RetryMiddleware(
        base_delay=2.0,
        max_delay=3.0,
        exponential_base=2.0,
    )
    monkeypatch.setattr(retry_module.random, "uniform", lambda _low, _high: 1.25)

    assert middleware._calculate_delay(0) == 2.5
    assert middleware._calculate_delay(10) == 3.0


def test_retryable_exception_filter_accepts_only_configured_types():
    middleware = RetryMiddleware(retryable_exceptions=(ValueError,))

    assert middleware._is_retryable(ValueError("retry")) is True
    assert middleware._is_retryable(TypeError("raise")) is False


@pytest.mark.asyncio
async def test_retry_metadata_without_retry_count_is_left_untouched():
    event = SimpleNamespace(event_type="metadata-edge", metadata=SimpleNamespace())

    async def handle(_event):
        return None

    await RetryMiddleware(max_retries=0)(event, handle)

    assert not hasattr(event.metadata, "retry_count")


@pytest.mark.asyncio
async def test_retry_metadata_is_updated_and_success_returns_immediately():
    event = SimpleNamespace(
        event_type="metadata",
        metadata=SimpleNamespace(retry_count=99),
    )
    calls = 0

    async def handle(_event):
        nonlocal calls
        calls += 1

    await RetryMiddleware(max_retries=2)(event, handle)

    assert calls == 1
    assert event.metadata.retry_count == 0


@pytest.mark.asyncio
async def test_non_retryable_error_is_reraised_without_sleep(monkeypatch):
    event = SimpleNamespace(event_type="non-retryable")

    async def forbidden_sleep(_delay):
        pytest.fail("non-retryable errors must not sleep")

    monkeypatch.setattr(retry_module.asyncio, "sleep", forbidden_sleep)

    async def handle(_event):
        raise TypeError("do not retry")

    with pytest.raises(TypeError, match="do not retry"):
        await RetryMiddleware(
            max_retries=2,
            retryable_exceptions=(ValueError,),
        )(event, handle)


@pytest.mark.asyncio
async def test_retryable_error_sleeps_then_succeeds(monkeypatch):
    event = SimpleNamespace(
        event_type="retryable",
        metadata=SimpleNamespace(retry_count=-1),
    )
    sleep = AsyncMock()
    monkeypatch.setattr(retry_module.asyncio, "sleep", sleep)
    calls = 0

    async def handle(_event):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("temporary")

    await RetryMiddleware(max_retries=1, base_delay=0.25)(event, handle)

    assert calls == 2
    assert event.metadata.retry_count == 1
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_exhaustion_raises_contextual_error(monkeypatch):
    event = SimpleNamespace(event_type="exhausted")
    sleep = AsyncMock()
    monkeypatch.setattr(retry_module.asyncio, "sleep", sleep)

    async def handle(_event):
        raise ValueError("permanent")

    with pytest.raises(EventRetryExhausted) as caught:
        await RetryMiddleware(max_retries=1, base_delay=0.01)(event, handle)

    assert caught.value.event is event
    assert caught.value.original_error.args == ("permanent",)
    assert caught.value.attempts == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_negative_retry_budget_exits_without_an_error():
    event = SimpleNamespace(event_type="empty-budget")

    await RetryMiddleware(max_retries=-1)(event, lambda _event: None)


@pytest.mark.asyncio
async def test_with_retry_decorator_preserves_metadata_and_invokes_handler():
    seen = []

    @with_retry(max_retries=0)
    async def handle(event):
        """Original handler documentation."""
        seen.append(event.event_type)

    event = SimpleNamespace(event_type="decorated")
    await handle(event)

    assert handle.__name__ == "handle"
    assert handle.__doc__ == "Original handler documentation."
    assert seen == ["decorated"]
