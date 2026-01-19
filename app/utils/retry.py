"""
Retry utilities with exponential backoff.

Provides decorators and functions for resilient async operations.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_error: Exception | None = None) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Retry exhausted after {attempts} attempts")


async def retry_async(
    fn: Callable[P, Awaitable[T]],
    *args: P.args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
    **kwargs: P.kwargs,
) -> T:
    """
    Execute an async function with exponential backoff retry.

    Args:
        fn: Async function to execute
        max_attempts: Maximum number of attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay cap in seconds (default 60.0)
        exponential_base: Base for exponential calculation (default 2.0)
        jitter: Add random jitter to delay (default True)
        retryable_exceptions: Tuple of exceptions to retry on
        on_retry: Callback called on each retry with attempt number and exception

    Returns:
        Result of the function call

    Raises:
        RetryExhausted: If all attempts fail
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except retryable_exceptions as e:
            last_error = e

            if attempt >= max_attempts:
                logger.warning(
                    "Retry exhausted for %s after %d attempts: %s",
                    fn.__name__,
                    attempt,
                    e,
                )
                raise RetryExhausted(attempt, last_error) from e

            # Calculate delay with exponential backoff
            exp_delay = base_delay * (exponential_base ** (attempt - 1))
            delay = min(exp_delay, max_delay)

            # Add jitter
            if jitter:
                delay = delay * (0.5 + random.random())

            logger.debug(
                "Retry %d/%d for %s after %.2fs: %s",
                attempt,
                max_attempts,
                fn.__name__,
                delay,
                e,
            )

            if on_retry:
                on_retry(attempt, e)

            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    raise RetryExhausted(max_attempts, last_error)


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Decorator for adding retry logic to async functions.

    Usage:
        @with_retry(max_attempts=3, base_delay=1.0)
        async def my_function():
            ...
    """

    def decorator(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await retry_async(
                fn,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                retryable_exceptions=retryable_exceptions,
                **kwargs,
            )

        return wrapper

    return decorator


__all__ = ["retry_async", "with_retry", "RetryExhausted"]
