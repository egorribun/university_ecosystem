from __future__ import annotations

import threading  # MED-W19
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from redis.asyncio import Redis

if TYPE_CHECKING:
    pass

type _RedisFactory = Callable[[str], Redis[Any]]


def _create_redis_pool(url: str) -> Redis[Any]:
    return cast(
        "Redis[Any]",
        Redis.from_url(
            url, encoding="utf-8", decode_responses=False, health_check_interval=30
        ),
    )


_redis_factory: _RedisFactory = _create_redis_pool
_shared_clients: dict[str, Redis[Any]] = {}
# Client lookup and creation are synchronous. This guard coordinates only cache
# and factory access; Redis client and pool operations remain bound to the single
# ASGI event loop that uses them in each worker process.
_shared_clients_guard: threading.Lock = threading.Lock()


async def get_shared_client(redis_url: str) -> Redis[Any]:
    """Return a shared Redis client for *redis_url*."""
    with _shared_clients_guard:
        client = _shared_clients.get(redis_url)
        if client is None:
            client = _redis_factory(redis_url)
            _shared_clients[redis_url] = client
    return client


def set_rate_limit_client_factory(factory: _RedisFactory | None) -> None:
    global _redis_factory
    with _shared_clients_guard:
        _redis_factory = _create_redis_pool if factory is None else factory
        _shared_clients.clear()
