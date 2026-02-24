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

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Maximum number of entries kept in the Redis Stream.
# ~500 bytes per entry × 50 000 = ~25 MB ceiling.
_MAX_STREAM_LEN: int = 50_000
_STREAM_KEY: str = "security:suspicious_events"


class FraudDetectionService:
    """Writes and queries suspicious session activity events in Redis Streams.

    Designed to be used as an APP-scoped singleton in the dishka DI container
    so that the Redis connection is reused across requests.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis_client

    async def record_event(self, event_data: dict[str, str]) -> None:
        """Append *event_data* to the Redis Stream.

        Uses ``MAXLEN ~`` (approximate trimming) for O(1) amortised memory
        bounding without blocking the append.
        """
        try:
            await self._redis.xadd(
                _STREAM_KEY,
                event_data,
                maxlen=_MAX_STREAM_LEN,
                approximate=True,  # Trim ~MAX_STREAM_LEN (O(1) rather than O(N))
            )
        except Exception:
            # Security events must never crash application code.
            # Log at ERROR but do not propagate.
            logger.exception("FraudDetectionService: failed to record event")

    async def get_recent_events(
        self,
        user_id: int | None = None,
        count: int = 100,
        within_seconds: int | None = None,
    ) -> list[dict[str, str]]:
        """Return up to *count* most-recent events, optionally filtered by user.

        Reads in reverse-chronological order using ``XREVRANGE``.
        (PERF-1: audit 2026-02-24) Uses time-windowing to avoid scanning stale entries.
        """
        import time

        fetch_count = count if user_id is None else count * 10
        min_id = "-"
        if within_seconds:
            # Redis stream IDs are timestamp-seq.
            min_ts = int((time.time() - within_seconds) * 1000)
            min_id = f"{min_ts}-0"

        try:
            raw: list[tuple[bytes, dict[bytes, bytes]]] = await self._redis.xrevrange(
                _STREAM_KEY, max="+", min=min_id, count=fetch_count
            )
        except Exception:
            logger.exception("FraudDetectionService: failed to read events")
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
        user_id: int,
        within_seconds: int = 300,
    ) -> int:
        """Count HIGH-severity events for *user_id* in the last N seconds.

        (PERF-1: audit 2026-02-24) Uses 500-event ceiling but bounds by time.
        Useful for threshold-based alerting: ≥ 3 HIGH events → block account.
        """
        events = await self.get_recent_events(
            user_id=user_id, count=500, within_seconds=within_seconds
        )
        return sum(1 for e in events if e.get("severity") == "high")
