"""SpiceDB Watch stream for permission-cache invalidation and session control.

``PermissionChecker.check_permission`` normally attempts a live
``CheckPermission`` call and caches successful responses. It uses a cached result
only when the call fails or the circuit breaker is open, within permission-specific
stale-age limits; an ``admin`` ALLOW result requires a live grant.

Each configured API process runs its own listener. Relationship updates evict
matching entries from that process-local cache, attempt Redis ``auth:perms``
invalidation for the affected user, and attempt a signed ``ws_hub.control``
disconnect. Redis invalidation and WebSocket-hub publication are best-effort.

If a Watch stream ends or errors, the listener clears its local cache before
reconnecting with exponential back-off. Live permission checks remain the
normal authorization path.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.spicedb import _parse_endpoint, create_async_spicedb_channel

logger = get_logger(__name__)

# Reconnect back-off parameters
_MIN_BACKOFF_S: float = 1.0
_MAX_BACKOFF_S: float = 60.0


async def _watch_once(token: str, host: str, port: int, use_ssl: bool) -> None:
    """Open a single Watch stream and process updates until it closes/errors."""
    from authzed.api.v1 import (  # type: ignore[attr-defined]
        WatchRequest,
        WatchServiceStub,
    )

    from app.auth.rbac import _permission_cache

    target = f"{host}:{port}"
    channel = create_async_spicedb_channel(target, token, use_ssl=use_ssl)

    try:
        stub = WatchServiceStub(channel)
        # Watch all object types — narrow if SpiceDB event volume becomes large.
        request = WatchRequest(optional_object_types=[])
        logger.info("SpiceDB Watch stream connected to %s", target)

        async for response in stub.Watch(request):
            for update in response.updates:
                await _invalidate_for_update(update, _permission_cache)
    finally:
        await channel.close()


async def _invalidate_for_update(
    update: object,
    cache: Any,
) -> None:
    """Process a SpiceDB relationship update and execute full revocation pipeline.

    Steps:
    1. Parse update payload (extract user_id, resource_type, resource_id).
    2. Evict matching entries from local _permission_cache.
    3. Invalidate Redis authorization cache keys ('auth:perms:<user_id>*').
    4. Publish HMAC-signed disconnect event to NATS subject 'ws_hub.control' via WsHubClient.
    5. Record metrics (spicedb_watch_events_total, ws_hub_sessions_revoked_total).
    """
    try:
        rel = update.relationship  # type: ignore[attr-defined]
        resource_type: str = rel.resource.object_type
        resource_id: str = rel.resource.object_id
        user_id: str = rel.subject.object.object_id
    except AttributeError:
        logger.debug("SpiceDB Watch: unrecognised update shape: %r", update)
        return

    # 1. Local _permission_cache eviction
    keys_to_evict = [
        k
        for k in cache
        if len(k) >= 3
        and k[0] == user_id
        and k[1] == resource_type
        and k[2] == resource_id
    ]
    for key in keys_to_evict:
        cache.pop(key, None)

    if keys_to_evict:
        logger.debug(
            "SpiceDB Watch: evicted %d local cache entries for %s:%s (user=%s)",
            len(keys_to_evict),
            resource_type,
            resource_id,
            user_id,
        )

    # 2. Redis authorization cache invalidation
    try:
        from app.deps.cache import get_cache

        redis_cache = get_cache()
        await redis_cache.invalidate(f"auth:perms:{user_id}*", f"auth:perms:{user_id}")
    except Exception:  # RZ-22-01-JUSTIFIED: defensive cache invalidation
        logger.warning(
            "SpiceDB Watch: failed to invalidate Redis authorization cache for user %s",
            user_id,
            exc_info=True,
        )

    # 3. NATS Disconnect Event Publish via WsHubClient
    try:
        from app.services.ws_hub_client import _get_client

        ws_client = _get_client()
        await ws_client.publish_control_event(
            user_id=user_id,
            action="disconnect",
            reason="access_revoked",
        )
    except Exception:  # RZ-22-01-JUSTIFIED: defensive NATS event publish
        logger.warning(
            "SpiceDB Watch: failed to publish NATS control disconnect event for user %s",
            user_id,
            exc_info=True,
        )

    # 4. Metrics recording
    try:
        from app.core.metrics import (
            record_spicedb_watch_event,
            record_ws_hub_session_revoked,
        )

        record_spicedb_watch_event(event_type="update")
        record_ws_hub_session_revoked(reason="access_revoked")
    except Exception:  # RZ-22-01-JUSTIFIED: defensive metrics guard
        logger.debug("SpiceDB Watch: failed to record metrics", exc_info=True)


async def start_permission_watch() -> None:
    """Background task: maintain a SpiceDB Watch stream with exponential back-off.

    Started from ``app.core.lifespan._startup_background_workers`` (API
    processes outside the testing environment) and cancelled with the other
    background tasks on shutdown.

    The task runs indefinitely, reconnecting after errors with back-off.
    """
    if not settings.spicedb_endpoint or not settings.spicedb_preshared_key:
        logger.info("SpiceDB Watch: disabled (no endpoint/key configured)")
        return

    host, port, use_ssl = _parse_endpoint(settings.spicedb_endpoint)
    token: str = settings.spicedb_preshared_key
    backoff = _MIN_BACKOFF_S

    from app.auth.rbac import _permission_cache

    while True:
        try:
            await _watch_once(token, host, port, use_ssl)
            # Stream ended cleanly (server closed it) — reconnect quickly.  Events
            # may have been missed while no stream was open, so drop cached
            # decisions here as well.
            backoff = _MIN_BACKOFF_S
            _permission_cache.clear()
        except asyncio.CancelledError:
            logger.info("SpiceDB Watch: task cancelled, stopping")
            return
        except Exception as exc:  # RZ-22-01-JUSTIFIED: handler-nak — reconnect loop must survive any stream error (reviewed TD-27-04)
            logger.warning(
                "SpiceDB Watch: stream error (%s) — reconnecting in %.0fs",
                exc,
                backoff,
            )
            # Clear cache so the first post-reconnect request hits SpiceDB live.
            _permission_cache.clear()
            logger.debug("SpiceDB Watch: permission cache cleared after disconnect")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF_S)
        logger.info("SpiceDB Watch: reconnecting...")


def get_watch_task_age() -> float | None:
    """Return seconds since the watch cache was last populated, or None."""
    from app.auth.rbac import _permission_cache

    if not _permission_cache:
        return None
    oldest = min(v[1] for v in _permission_cache.values())
    return time.monotonic() - oldest
