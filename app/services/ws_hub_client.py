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
    """Thin async client for ws-hub internal cache invalidation endpoint.

    RZ-F-04 (audit 2026-03-07): Uses a persistent httpx.AsyncClient so that
    TCP connections are reused across calls instead of being created and torn
    down on every invalidation request.  The previous `async with
    httpx.AsyncClient()` pattern did a full TCP+TLS handshake per call, which
    exhausts ephemeral ports under high participant-removal throughput.
    """

    def __init__(self) -> None:
        base = settings.ws_hub_internal_url.rstrip("/")
        self._url = f"{base}/internal/cache/invalidate"
        self._secret = settings.ws_hub_internal_secret
        # Persistent connection pool — reused for the lifetime of the process.
        self._client = httpx.AsyncClient(timeout=2.0)

    def _headers(self) -> dict[str, str]:
        if self._secret:
            return {"Authorization": f"Bearer {self._secret}"}
        return {}

    async def invalidate_cache(
        self,
        user_id: str | uuid.UUID,
        room_id: str | uuid.UUID,
    ) -> None:
        """Evict the (user_id, room_id) entry from the ws-hub auth cache.

        Failures are logged but never raised — a failed invalidation means the
        old cached result lingers for at most 60 seconds, which is tolerable.
        The calling code should not block on this best-effort call.
        """
        params = {"user_id": str(user_id), "room_id": str(room_id)}
        try:
            response = await self._client.post(
                self._url,
                params=params,
                headers=self._headers(),
            )
            if response.status_code not in (204, 404):
                logger.warning(
                    "ws-hub cache invalidation returned unexpected status %d "
                    "for user_id=%s room_id=%s",
                    response.status_code,
                    user_id,
                    room_id,
                )
        except Exception:
            logger.warning(
                "ws-hub cache invalidation failed for user_id=%s room_id=%s",
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
