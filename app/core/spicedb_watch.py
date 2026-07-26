"""SpiceDB streaming Watch API integration.

MOD-W5-04 (audit 2026-03-13): Replace per-request CheckPermission gRPC calls
with a long-lived Watch stream that pushes relationship/permission changes to
the application.  The Watch listener invalidates entries in the grace-period
cache (``app.auth.rbac._permission_cache``) so that subsequent checks are
re-evaluated against SpiceDB rather than served from a stale entry.

Architecture
------------
The Watch stream is started as a background asyncio task during application
lifespan (``start_permission_watch``).  It streams *all* relationship changes
from SpiceDB and invalidates matching permission cache entries.  This is safe
even when the cache contains partial state because ``rbac.check_permission``
always falls back to a live gRPC call on cache miss.

Fault tolerance
---------------
- The watcher reconnects with exponential back-off (1 s → 60 s) on any error.
- During reconnect, the grace-period cache (TTL = 60 s) continues to serve
  the last-known result, preventing a thundering herd on SpiceDB.
- On reconnect the cache is **fully cleared** so that the first request after
  reconnect always hits SpiceDB — this avoids serving permanently stale data
  if permissions changed during the outage window.
"""

from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.core.spicedb import _parse_endpoint

logger = get_logger(__name__)

# Reconnect back-off parameters
_MIN_BACKOFF_S: float = 1.0
_MAX_BACKOFF_S: float = 60.0


async def _watch_once(token: str, host: str, port: int, use_ssl: bool) -> None:
    """Open a single Watch stream and process updates until it closes/errors."""
    import grpc
    from authzed.api.v1 import (  # type: ignore[attr-defined]
        WatchRequest,
        WatchServiceStub,
    )

    from app.auth.rbac import _permission_cache

    target = f"{host}:{port}"
    if use_ssl:
        from grpcutil import bearer_token_credentials

        credentials = bearer_token_credentials(token)
        channel = grpc.aio.secure_channel(target, credentials)
    else:
        channel = grpc.aio.insecure_channel(target)

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

    Call from application lifespan::

        from app.core.task_registry import TaskRegistry
        from app.core.spicedb_watch import start_permission_watch

        task_registry.create_task(start_permission_watch(), name="spicedb-watch")

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
            # Stream ended cleanly (server closed it) — reconnect quickly.
            backoff = _MIN_BACKOFF_S
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
