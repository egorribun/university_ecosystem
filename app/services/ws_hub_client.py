"""Client for the ws-hub internal HTTP API.

TD-NEW-07 (audit 2026-03-07): The ws-hub caches auth checks for 60 seconds.
When a participant is removed from a chat the backend must explicitly invalidate
that entry so the user cannot continue sending WebSocket messages during the
remaining TTL window.

Usage example (in ChatService.remove_participant):
    await WsHubClient(settings).invalidate_cache(user_id=str(user_id), room_id=str(chat_id))
"""

from __future__ import annotations

import logging
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class WsHubClient:
    """Async client for ws-hub distributed cache invalidation via NATS.

    M-007 (audit 2026-03-10): Replaces the legacy HTTP-based invalidation with
    asynchronous NATS JetStream events. This ensures that the Python backend
    never blocks on the ws-hub internal API, and invalidation messages are
    persisted in JetStream if the ws-hub is temporarily unreachable.
    """

    def __init__(self) -> None:
        from app.core.nats_broker import broker

        self._broker = broker

    async def invalidate_cache(
        self,
        user_id: str | uuid.UUID,
        room_id: str | uuid.UUID,
    ) -> None:
        """Publish an invalidation event to NATS JetStream.

        Events are published to 'cache.invalidate' subject. The ws-hub
        subscribes to this subject to flush its internal auth cache.
        """
        payload = {
            "user_id": str(user_id),
            "room_id": str(room_id),
            "timestamp": uuid.uuid1().time,  # record order
        }
        try:
            # We don't await the full persistence if we want maximum speed,
            # but nats_broker.publish is async and we should await it for safety.
            await self._broker.publish("cache.invalidate", payload)
        except Exception:
            logger.warning(
                "Failed to publish ws-hub cache invalidation to NATS for user_id=%s room_id=%s",
                user_id,
                room_id,
                exc_info=True,
            )


_client = WsHubClient()


async def invalidate_ws_hub_cache(
    user_id: str | uuid.UUID,
    room_id: str | uuid.UUID,
) -> None:
    """Module-level convenience wrapper around the shared WsHubClient."""
    await _client.invalidate_cache(user_id=user_id, room_id=room_id)
