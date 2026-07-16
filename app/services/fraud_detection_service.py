"""FraudDetectionService — durable, cross-worker security event correlation.

Replaces the in-process ``SuspiciousActivityDetector._events`` list with a
Redis Streams–backed store. Each uvicorn worker writes events to a shared
stream; any worker (or a dedicated consumer group) can read the full picture.

Key properties:
- **Durability:** events survive pod restarts (Redis persistence).
- **Multi-worker visibility:** all workers share one stream — no blind spots.
- **Bounded size:** ``MAXLEN ~`` trims the stream to ``MAX_STREAM_LEN``
  entries with O(1) amortised cost (Redis radix-tree).
- **Consumer groups (optional):** add a ``XREADGROUP`` consumer to feed a
  real-time alerting pipeline (e.g., alert on 3+ HIGH events / 5 min for
  one user).

This module is intentionally NOT wired as a global singleton — it receives a
redis client via __init__ and is registered in the dishka DI container.
(MOD-4 / TD-4: audit 2026-02-24)
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from app.core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = get_logger(__name__)

# Maximum number of entries kept in the Redis Stream.
# ~500 bytes per entry × 50 000 = ~25 MB ceiling.
_MAX_STREAM_LEN: int = 50_000
_STREAM_KEY: str = "security:suspicious_events"


# TTL for the per-user high-severity counter (seconds).
# Must be >= the maximum `within_seconds` used in count_recent_high_severity.
_HIGH_SEVERITY_COUNTER_TTL: int = 3600  # 1 hour


class FraudDetectionService:
    """Writes and queries suspicious session activity events in Redis Streams.

    Designed to be used as an APP-scoped singleton in the dishka DI container
    so that the Redis connection is reused across requests.
    """

    def __init__(self, redis_client: aioredis.Redis[Any]) -> None:
        self._redis = redis_client

    async def record_event(self, event_data: dict[str, str]) -> None:
        """Append *event_data* to the Redis Stream and update the O(1) counter.

        Uses ``MAXLEN ~`` (approximate trimming) for O(1) amortised memory
        bounding without blocking the append.

        PERF-4 fix (audit 2026-02-26): When severity == "high", stores a
        timestamp in a per-user Redis Sorted Set so count_recent_high_severity
        can answer arbitrary time-window queries in O(log N) without over-counting.
        The previous approach used a fixed 1-hour TTL counter but answered
        ``within_seconds=300`` queries, returning values up to 12x too large.
        """
        try:
            await cast(
                "Awaitable[Any]",
                self._redis.xadd(
                    _STREAM_KEY,
                    cast(Any, event_data),
                    maxlen=_MAX_STREAM_LEN,
                    approximate=True,  # Trim ~MAX_STREAM_LEN (O(1) rather than O(N))
                ),
            )

            # Sliding-window Sorted Set for high-severity events per user.
            if event_data.get("severity") == "high" and (
                user_id := event_data.get("user_id")
            ):
                import time as _time

                now_ms = int(_time.time() * 1000)
                zset_key = f"security:high_events:{user_id}"
                pipe = self._redis.pipeline(transaction=False)
                # HIGH-W19: use a unique member to avoid two events at the same
                # millisecond overwriting each other in the sorted set.
                # Score = unix-millisecond timestamp (used for range queries).
                member = f"{now_ms}:{uuid4().hex[:8]}"
                pipe.zadd(zset_key, {member: now_ms})
                # Keep the set auto-expired 1 hour after last write.
                pipe.expire(zset_key, _HIGH_SEVERITY_COUNTER_TTL)
                await cast("Awaitable[Any]", pipe.execute())

        except (ConnectionError, TimeoutError, OSError):
            # RZ-20-04 (audit 2026-03-24): Narrowed from bare Exception to
            # connection-failure family.  Security events must never crash the
            # request pipeline, but logic bugs (TypeError from malformed
            # event_data) should propagate and be caught by Sentry.
            logger.exception("FraudDetectionService: failed to record event to Redis")

    async def get_recent_events(
        self,
        user_id: uuid.UUID | str | None = None,
        count: int = 100,
        within_seconds: int | None = None,
    ) -> list[dict[str, str]]:
        """Return up to *count* most-recent events, optionally filtered by user.

        Reads in reverse-chronological order using ``XREVRANGE``.
        Intended for full audit/admin listing, NOT for threshold counting.
        Use count_recent_high_severity for O(1) counting.

        OZ-4 (audit 2026-02-26): Parameter type corrected from ``int`` to
        ``uuid.UUID | str | None``. Redis stores user_id as ``str(UUID)``; an
        ``int`` annotation was misleading and caused silently incorrect comparisons
        when callers passed a UUID object.
        """
        import time

        fetch_count = count if user_id is None else count * 10
        min_id = "-"
        if within_seconds:
            # Redis stream IDs are timestamp-seq.
            min_ts = int((time.time() - within_seconds) * 1000)
            min_id = f"{min_ts}-0"

        try:
            raw: list[tuple[bytes, dict[bytes, bytes]]] = await cast(
                "Awaitable[Any]",
                self._redis.xrevrange(
                    _STREAM_KEY, max="+", min=min_id, count=fetch_count
                ),
            )
        except (ConnectionError, TimeoutError, OSError):
            # RZ-20-04: Narrowed — Redis stream read failure.
            logger.exception("FraudDetectionService: failed to read events from Redis")
            return []

        results: list[dict[str, str]] = []
        for _entry_id, fields in raw:
            decoded = {k.decode(): v.decode() for k, v in fields.items()}
            if user_id is not None:
                if decoded.get("user_id") != str(user_id):
                    continue
            results.append(decoded)
            if len(results) >= count:
                break
        return results

    async def count_recent_high_severity(
        self,
        user_id: uuid.UUID | str,
        within_seconds: int = 300,
    ) -> int:
        """Count HIGH-severity events for *user_id* in the last N seconds.

        PERF-4 fix (audit 2026-02-26): Uses a Redis Sorted Set (ZCOUNT by score
        range) instead of a fixed-TTL counter to support arbitrary time windows.
        The previous counter had a 1-hour TTL but was queried with
        within_seconds=300, returning values up to 12x too large.

        Complexity: O(log N) where N is the number of high-severity events in the
        sorted set (bounded to the last hour by the set TTL).
        """
        import time as _time

        zset_key = f"security:high_events:{user_id}"
        now_ms = int(_time.time() * 1000)
        since_ms = now_ms - (within_seconds * 1000)
        try:
            count = await cast(
                "Awaitable[Any]", self._redis.zcount(zset_key, since_ms, now_ms)
            )
            return int(count)
        except (ConnectionError, TimeoutError, OSError):
            # RZ-20-04: Narrowed — Redis sorted set query failure.
            logger.exception("FraudDetectionService: failed to read high_count (zset)")
            # Graceful degradation: fall back to stream scan so we don't
            # silently allow fraudulent accounts on Redis errors.
            events = await self.get_recent_events(
                user_id=user_id, count=500, within_seconds=within_seconds
            )
            return sum(1 for e in events if e.get("severity") == "high")
