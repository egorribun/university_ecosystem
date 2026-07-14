from __future__ import annotations

import asyncio
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
# MED-W19: Use a module-level threading.Lock for bootstrap to eliminate TOCTOU
# race where two concurrent callers both see _shared_clients_write_lock is None
# and each create a separate asyncio.Lock, losing mutual exclusion.
_shared_clients_bootstrap_lock: threading.Lock = threading.Lock()
_shared_clients_write_lock: asyncio.Lock | None = None


async def get_shared_client(redis_url: str) -> Redis[Any]:
    """Return a shared Redis client for *redis_url*."""
    global _shared_clients_write_lock
    client = _shared_clients.get(redis_url)
    if client is not None:
        return client

    with _shared_clients_bootstrap_lock:
        if _shared_clients_write_lock is None:
            _shared_clients_write_lock = asyncio.Lock()

    async with _shared_clients_write_lock:
        client = _shared_clients.get(redis_url)
        if client is None:
            client = _redis_factory(redis_url)
            _shared_clients[redis_url] = client
    return client


def set_rate_limit_client_factory(factory: _RedisFactory | None) -> None:
    global _redis_factory
    _redis_factory = _create_redis_pool if factory is None else factory
    _shared_clients.clear()
