"""Client for the ws-hub internal HTTP API.

TD-NEW-07 (audit 2026-03-07): The ws-hub caches auth checks for 60 seconds.
When a participant is removed from a chat the backend must explicitly invalidate
that entry so the user cannot continue sending WebSocket messages during the
remaining TTL window.

Usage example (in ChatService.remove_participant):
    await invalidate_ws_hub_cache(user_id=str(user_id), room_id=str(chat_id))
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import random
import threading
import time
import uuid

from prometheus_client import Counter

from app.core.logging import get_logger

logger = get_logger(__name__)

# RZ-14-04 (audit Wave 14): Prometheus counter for failed NATS invalidation
# publishes.  Enables alerting when cache-invalidation failures spike — the
# ws-hub would otherwise silently serve stale auth data for up to 60s.
_INVALIDATION_FAILURES = Counter(
    "ws_hub_invalidation_failures_total",
    "Failed NATS cache invalidation publishes (after retry)",
)

_MAX_PUBLISH_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 0.1


class WsHubClient:
    """Async client for ws-hub distributed cache invalidation via NATS.

    M-007 (audit 2026-03-10): Replaces the legacy HTTP-based invalidation with
    asynchronous NATS JetStream events. This ensures that the Python backend
    never blocks on the ws-hub internal API, and invalidation messages are
    persisted in JetStream if the ws-hub is temporarily unreachable.
    """

    def __init__(self) -> None:
        from app.core.config import settings
        from app.core.nats_broker import broker

        self._broker = broker
        self._secret = settings.ws_hub_internal_secret

    async def invalidate_cache(
        self,
        user_id: str | uuid.UUID,
        room_id: str | uuid.UUID,
    ) -> None:
        """Publish a signed invalidation event to NATS JetStream.

        Events are published to 'cache.invalidate' subject. The ws-hub
        subscribes to this subject and verifies the signature using the
        shared InternalSecret.

        RZ-14-04 (audit Wave 14): One retry with 100ms backoff covers transient
        NATS hiccups.  On final failure a Prometheus counter is incremented and
        the error is logged at ERROR level (not WARNING) so it surfaces in
        error-rate dashboards.
        """
        payload_content = {
            "user_id": str(user_id),
            "room_id": str(room_id),
            # RZ-14-02 (audit Wave 14): Replaced uuid.uuid1().time with
            # time.time_ns().  uuid1 leaks the host MAC address in its node
            # field; time_ns() provides equivalent nanosecond ordering without
            # the privacy risk or the overhead of MAC resolution.
            "timestamp": time.time_ns(),
        }

        # TD-NEW-07: Sign the payload to prevent unauthorized cache flushes.
        # Use deterministic JSON serialization for consistent signing.
        json_payload = json.dumps(
            payload_content, sort_keys=True, separators=(",", ":")
        )
        signature = hmac.new(
            self._secret.encode(),
            json_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        full_payload = {
            "data": payload_content,
            "signature": signature,
        }

        last_exc: Exception | None = None
        for attempt in range(_MAX_PUBLISH_ATTEMPTS):
            try:
                await self._broker.publish("cache.invalidate", full_payload)
                return
            except (ConnectionError, TimeoutError, OSError) as exc:
                # RZ-20-04: Narrowed — NATS publish retry catches infra errors.
                last_exc = exc
                if attempt < _MAX_PUBLISH_ATTEMPTS - 1:
                    # TD-30-06: Exponential backoff with jitter prevents
                    # thundering herd when NATS recovers after outage.
                    backoff = _RETRY_BACKOFF_SECONDS * (2**attempt)
                    jitter = random.uniform(0, backoff * 0.5)  # noqa: S311 — not security-sensitive  # nosec B311
                    await asyncio.sleep(backoff + jitter)

        # All attempts exhausted — record the failure for alerting.
        _INVALIDATION_FAILURES.inc()
        logger.error(
            "ws_hub_invalidation_failed",
            user_id=str(user_id),
            room_id=str(room_id),
            attempts=_MAX_PUBLISH_ATTEMPTS,
            exc_info=last_exc,
        )

    async def publish_control_event(
        self,
        user_id: str | uuid.UUID,
        action: str = "disconnect",
        reason: str = "access_revoked",
    ) -> None:
        """Publish a signed control event to NATS JetStream subject 'ws_hub.control'.

        The ws-hub listens on 'ws_hub.control', verifies the signature using
        ws_hub_internal_secret, and disconnects all active WebSocket connections for user_id.
        """
        payload_content = {
            "user_id": str(user_id),
            "action": action,
            "reason": reason,
            "timestamp": time.time_ns(),
        }

        json_payload = json.dumps(
            payload_content, sort_keys=True, separators=(",", ":")
        )
        signature = hmac.new(
            self._secret.encode(),
            json_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        full_payload = {
            "data": payload_content,
            "signature": signature,
        }

        last_exc: Exception | None = None
        for attempt in range(_MAX_PUBLISH_ATTEMPTS):
            try:
                await self._broker.publish("ws_hub.control", full_payload)
                return
            except (ConnectionError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < _MAX_PUBLISH_ATTEMPTS - 1:
                    backoff = _RETRY_BACKOFF_SECONDS * (2**attempt)
                    jitter = random.uniform(0, backoff * 0.5)  # noqa: S311 — not security-sensitive  # nosec B311
                    await asyncio.sleep(backoff + jitter)

        _INVALIDATION_FAILURES.inc()
        logger.error(
            "ws_hub_control_publish_failed",
            user_id=str(user_id),
            action=action,
            reason=reason,
            attempts=_MAX_PUBLISH_ATTEMPTS,
            exc_info=last_exc,
        )


# RZ-14-01 (audit Wave 14): Lazy singleton.  The previous code instantiated
# WsHubClient() at module import time, which triggered `settings` and `broker`
# resolution before the application lifespan had completed.  This caused
# AttributeError or stale config in test fixtures and CLI startup paths.
#
# RZ-30-01 (audit Wave 30): Double-checked locking with threading.Lock.
# Under Python 3.13+ free-threading (PYTHON_GIL=0) the original check-then-set
# was racy — two threads could both see _client is None and construct two
# WsHubClient instances, leaking one NATS connection.  The fast path (no lock)
# avoids contention after initialization.
_client_lock = threading.Lock()
_client: WsHubClient | None = None


def _get_client() -> WsHubClient:
    global _client
    if _client is not None:  # fast path — no lock after init
        return _client
    with _client_lock:  # slow path — double-checked locking
        if _client is None:
            _client = WsHubClient()
        return _client


async def invalidate_ws_hub_cache(
    user_id: str | uuid.UUID,
    room_id: str | uuid.UUID,
) -> None:
    """Module-level convenience wrapper around the shared WsHubClient."""
    await _get_client().invalidate_cache(user_id=user_id, room_id=room_id)


async def publish_ws_hub_control(
    user_id: str | uuid.UUID,
    action: str = "disconnect",
    reason: str = "access_revoked",
) -> None:
    """Convenience function to publish a ws-hub control disconnect event."""
    await _get_client().publish_control_event(
        user_id=user_id, action=action, reason=reason
    )
