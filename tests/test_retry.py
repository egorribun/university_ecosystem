"""Tests for retry utilities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.retry import RetryExhausted, retry_async, with_retry


@pytest.mark.asyncio
async def test_retry_async_success_first_attempt():
    """Test successful execution on first attempt."""
    mock_fn = AsyncMock(return_value="success")

    result = await retry_async(mock_fn, max_attempts=3)

    assert result == "success"
    assert mock_fn.call_count == 1


@pytest.mark.asyncio
async def test_retry_async_success_after_retry():
    """Test successful execution after retries."""
    mock_fn = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "success"])

    result = await retry_async(
        mock_fn,
        max_attempts=3,
        base_delay=0.01,
        retryable_exceptions=(ValueError,),
    )

    assert result == "success"
    assert mock_fn.call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausted():
    """Test RetryExhausted when all attempts fail."""
    mock_fn = AsyncMock(side_effect=ValueError("always fails"))

    with pytest.raises(RetryExhausted) as exc_info:
        await asyncio.wait_for(
            retry_async(
                mock_fn,
                max_attempts=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
            ),
            timeout=1.0,
        )

    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, ValueError)


@pytest.mark.asyncio
async def test_retry_async_non_retryable_exception():
    """Test that non-retryable exceptions are raised immediately."""
    mock_fn = AsyncMock(side_effect=KeyError("not retryable"))

    with pytest.raises(KeyError):
        await retry_async(
            mock_fn,
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )

    assert mock_fn.call_count == 1


@pytest.mark.asyncio
async def test_retry_async_on_retry_callback():
    """Test on_retry callback is called on each retry."""
    mock_fn = AsyncMock(
        side_effect=[ValueError("fail1"), ValueError("fail2"), "success"]
    )
    callback = MagicMock()

    result = await retry_async(
        mock_fn,
        max_attempts=3,
        base_delay=0.01,
        retryable_exceptions=(ValueError,),
        on_retry=callback,
    )

    assert result == "success"
    assert callback.call_count == 2


@pytest.mark.asyncio
async def test_with_retry_decorator():
    """Test with_retry decorator."""
    call_count = 0

    @with_retry(max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,))
    async def decorated_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("fail")
        return "decorated success"

    result = await decorated_fn()

    assert result == "decorated success"
    assert call_count == 3


def test_retry_exhausted_exception():
    """Test RetryExhausted exception properties."""
    original = ValueError("original error")
    exc = RetryExhausted(5, original)

    assert exc.attempts == 5
    assert exc.last_error is original
    assert "5 attempts" in str(exc)


@pytest.mark.asyncio
async def test_retry_async_no_jitter():
    """Test retry_async when jitter is disabled."""
    mock_fn = AsyncMock(side_effect=[ValueError("fail"), "success"])
    result = await retry_async(
        mock_fn,
        max_attempts=3,
        base_delay=0.01,
        jitter=False,
        retryable_exceptions=(ValueError,),
    )
    assert result == "success"
