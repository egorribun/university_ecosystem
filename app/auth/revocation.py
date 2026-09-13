"""Fail-closed Redis session revocation primitives.

The gateway accepts access tokens for at most 24 hours from ``iat``.  A
revocation tombstone therefore remains authoritative even when the cached
session key was evicted or lost its TTL, while avoiding permanent deny-list
entries for unique JTIs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from typing import TYPE_CHECKING, Any

from redis.exceptions import ResponseError

if TYPE_CHECKING:
    from redis.asyncio import Redis


MAX_REVOCATION_TOMBSTONE_TTL_SECONDS = 24 * 60 * 60

_REVOKE_WITH_TOMBSTONE_SCRIPT = """
local ttl = redis.call('TTL', KEYS[1])
if ttl <= 0 then
    ttl = tonumber(ARGV[1])
end
redis.call('SET', KEYS[2], '1', 'EX', ttl)
redis.call('DEL', KEYS[1])
return ttl
"""


def calculate_revocation_tombstone_ttl(
    expires_at: datetime | None,
    *,
    now: datetime | None = None,
) -> int:
    """Return a bounded positive TTL for a missing or unbounded session key."""
    if expires_at is None:
        return MAX_REVOCATION_TOMBSTONE_TTL_SECONDS

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    remaining = ceil((expires_at - current).total_seconds())
    return min(
        max(remaining, 1),
        MAX_REVOCATION_TOMBSTONE_TTL_SECONDS,
    )


async def revoke_with_tombstone(
    redis_client: Redis[Any] | None,
    *,
    session_key: str,
    jti: str,
    expires_at: datetime | None,
    revocation_redis_client: Redis[Any] | None = None,
) -> int:
    """Create a revocation tombstone before deleting the cached session.

    Redis executes the normal Lua path atomically.  If a Redis-compatible test
    or managed service disables ``EVAL``, the fallback deliberately writes the
    tombstone first and deletes only after that write succeeds.  Transport and
    write failures propagate so callers cannot report a successful revocation.
    """
    fallback_ttl = calculate_revocation_tombstone_ttl(expires_at)
    revoked_key = f"revoked:jti:{jti}"
    security_client = (
        revocation_redis_client if revocation_redis_client is not None else redis_client
    )
    if security_client is None:
        raise RuntimeError("revocation Redis client is unavailable")

    if redis_client is not security_client:
        await security_client.set(revoked_key, "1", ex=fallback_ttl)
        if redis_client is not None:
            await redis_client.delete(session_key)
        return fallback_ttl

    try:
        result = await security_client.eval(  # type: ignore[no-untyped-call]
            _REVOKE_WITH_TOMBSTONE_SCRIPT,
            2,
            session_key,
            revoked_key,
            fallback_ttl,
        )
        return int(result)
    except ResponseError:
        remaining_ttl = int(await security_client.ttl(session_key))
        tombstone_ttl = remaining_ttl if remaining_ttl > 0 else fallback_ttl
        await security_client.set(revoked_key, "1", ex=tombstone_ttl)
        await security_client.delete(session_key)
        return tombstone_ttl


async def get_revocation_redis_client() -> Redis[Any]:
    """Return the shared client for the isolated revocation datastore."""
    from app.core.config import settings
    from app.core.config.cache import DEFAULT_REVOCATION_REDIS_URL
    from app.core.ratelimit import get_shared_client

    if not bool(getattr(settings, "revocation_redis_access_enabled", True)):
        role = str(getattr(settings, "app_process_role", "unknown") or "unknown")
        raise RuntimeError(
            f"REVOCATION_REDIS access is disabled for this process role ({role!r})"
        )
    redis_url = str(settings.revocation_redis_url).strip()
    environment = str(
        getattr(settings, "environment", "production") or "production"
    ).lower()
    # The loopback URL is an intentional development/testing default (the local
    # compose revocation Redis listens on 6380).  Production still fails closed
    # when the default is left in place; only an explicitly configured URL may
    # be used by authentication-capable deployments.
    if not redis_url or (
        redis_url == DEFAULT_REVOCATION_REDIS_URL
        and environment not in {"development", "local", "testing"}
    ):
        raise RuntimeError("REVOCATION_REDIS_URL is not configured")
    return await get_shared_client(redis_url)
