"""Request coalescing for duplicate concurrent requests."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# In-flight request tracking
_in_flight_requests: dict[str, asyncio.Future] = {}
_request_locks: dict[str, asyncio.Lock] = {}


def _build_request_key(prefix: str, *args, **kwargs) -> str:
    """Build a unique key for a request based on its arguments."""
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode(), usedforsecurity=False).hexdigest()


def coalesce_requests(
    prefix: str | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator that coalesces duplicate concurrent requests.

    When multiple identical requests come in simultaneously, only one
    actually executes and the others wait for and share its result.

    This prevents redundant work (e.g., multiple users requesting the
    same resource at the exact same time).

    Args:
        prefix: Optional prefix for the request key
        key_builder: Optional custom function to build request key

    Example:
        @coalesce_requests(prefix="user_profile")
        async def get_user_profile(user_id: int):
            return await db.get_user(user_id)
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _prefix = prefix or func.__name__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if key_builder:
                request_key = key_builder(*args, **kwargs)
            else:
                request_key = _build_request_key(_prefix, *args, **kwargs)

            # Check if request is already in flight
            if request_key in _in_flight_requests:
                logger.debug("Coalescing request: %s", request_key)
                return await _in_flight_requests[request_key]

            # Get or create lock for this key pattern
            if request_key not in _request_locks:
                _request_locks[request_key] = asyncio.Lock()

            lock = _request_locks[request_key]

            async with lock:
                # Double-check after acquiring lock
                if request_key in _in_flight_requests:
                    return await _in_flight_requests[request_key]

                # Create future for this request
                future: asyncio.Future[R] = asyncio.get_event_loop().create_future()
                _in_flight_requests[request_key] = future

                try:
                    result = await func(*args, **kwargs)
                    future.set_result(result)
                    return result
                except Exception as exc:
                    future.set_exception(exc)
                    raise
                finally:
                    _in_flight_requests.pop(request_key, None)
                    # Clean up lock if no longer needed
                    if request_key in _request_locks:
                        _request_locks.pop(request_key, None)

        return wrapper

    return decorator


class RequestCoalescer:
    """
    Class-based request coalescer for more control.

    Useful when you need to coalesce requests across different functions
    that share the same underlying data.
    """

    def __init__(self, ttl_seconds: float = 0.5) -> None:
        self._in_flight: dict[str, asyncio.Future] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._ttl = ttl_seconds

    async def execute(
        self,
        key: str,
        func: Callable[[], Awaitable[R]],
    ) -> R:
        """
        Execute a function with request coalescing.

        Args:
            key: Unique key for this request
            func: Async function to execute

        Returns:
            Result from func (shared if coalesced)
        """
        if key in self._in_flight:
            return await self._in_flight[key]

        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            if key in self._in_flight:
                return await self._in_flight[key]

            future: asyncio.Future[R] = asyncio.get_event_loop().create_future()
            self._in_flight[key] = future

            try:
                result = await func()
                future.set_result(result)
                return result
            except Exception as exc:
                future.set_exception(exc)
                raise
            finally:
                self._in_flight.pop(key, None)
                self._locks.pop(key, None)
