"""
Event retry mechanism with exponential backoff.

Provides middleware for automatic retry of failed event handlers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.events import DomainEvent

logger = logging.getLogger(__name__)


class EventRetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(
        self,
        event: "DomainEvent",
        original_error: Exception,
        attempts: int,
    ) -> None:
        self.event = event
        self.original_error = original_error
        self.attempts = attempts
        super().__init__(
            f"Event {event.event_type} failed after {attempts} attempts: {original_error}"
        )


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 0.1
    max_delay: float = 10.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)


class RetryMiddleware:
    """
    Middleware that wraps event handling with retry logic.

    Uses exponential backoff with configurable parameters.
    Failed events after exhausting retries are passed to the
    dead letter queue if configured.

    Example:
        middleware = RetryMiddleware(max_retries=3)
        bus.add_middleware(middleware)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
        retryable_exceptions: tuple[type[Exception], ...] | None = None,
    ) -> None:
        """
        Initialize retry middleware.

        Args:
            max_retries: Maximum number of retry attempts (0 = no retries).
            base_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.
            exponential_base: Base for exponential backoff calculation.
            retryable_exceptions: Tuple of exception types to retry.
                                  Defaults to all exceptions.
        """
        self.config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            retryable_exceptions=retryable_exceptions or (Exception,),
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number."""
        delay = self.config.base_delay * (self.config.exponential_base**attempt)
        return min(delay, self.config.max_delay)

    def _is_retryable(self, error: Exception) -> bool:
        """Check if the exception is retryable."""
        return isinstance(error, self.config.retryable_exceptions)

    async def __call__(
        self,
        event: "DomainEvent",
        next_handler: Callable[["DomainEvent"], Awaitable[None]],
    ) -> None:
        """
        Execute the handler with retry logic.

        Args:
            event: The domain event to process.
            next_handler: The next handler in the middleware chain.

        Raises:
            EventRetryExhausted: When all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # Update retry metadata if available
                if hasattr(event, "metadata") and hasattr(event.metadata, "retry_count"):
                    event.metadata.retry_count = attempt

                await next_handler(event)
                return  # Success, exit

            except Exception as e:
                last_error = e

                # Check if this exception type should be retried
                if not self._is_retryable(e):
                    logger.warning(
                        "Non-retryable exception for event %s: %s",
                        event.event_type,
                        e,
                    )
                    raise

                # If we have more attempts, wait and retry
                if attempt < self.config.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "Event %s failed (attempt %d/%d), retrying in %.2fs: %s",
                        event.event_type,
                        attempt + 1,
                        self.config.max_retries + 1,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Event %s failed after %d attempts: %s",
                        event.event_type,
                        attempt + 1,
                        e,
                    )

        # All retries exhausted
        if last_error is not None:
            raise EventRetryExhausted(
                event=event,
                original_error=last_error,
                attempts=self.config.max_retries + 1,
            )


def with_retry(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 10.0,
) -> Callable[
    [Callable[["DomainEvent"], Awaitable[None]]],
    Callable[["DomainEvent"], Awaitable[None]],
]:
    """
    Decorator to add retry logic to individual handlers.

    Example:
        @with_retry(max_retries=5)
        async def handle_important_event(event: DomainEvent) -> None:
            ...
    """

    def decorator(
        func: Callable[["DomainEvent"], Awaitable[None]],
    ) -> Callable[["DomainEvent"], Awaitable[None]]:
        middleware = RetryMiddleware(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
        )

        async def wrapper(event: "DomainEvent") -> None:
            await middleware(event, func)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


__all__ = [
    "EventRetryExhausted",
    "RetryConfig",
    "RetryMiddleware",
    "with_retry",
]
