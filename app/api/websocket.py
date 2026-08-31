"""
WebSocket endpoint for real-time chat messaging.

TD-9 / MOD-9 (audit 2026-03-05): This module was decomposed into a sub-package
(app/api/ws/) for SRP compliance. This file now contains ONLY route handlers.
Backwards-compatibility re-exports are listed in __all__ below.

New code should import directly from the sub-package modules:
    from app.api.ws.connection_manager import ConnectionManager, manager
    from app.api.ws.presence import PresencePubSub, presence_pubsub
    from app.api.ws.auth import get_user_from_token
    from app.api.ws.serializers import serialize_message, build_presence_map
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.ws.auth import (
    update_last_seen as _update_last_seen,
)

# ── Sub-package imports (re-exported for backwards compat) ─────────────────────
from app.api.ws.connection_manager import (
    manager,
)
from app.api.ws.presence import (
    PRESENCE_SOURCE_CONNECT,
    PRESENCE_SOURCE_DISCONNECT,
    build_presence_map,
    presence_pubsub,
)
from app.api.ws.serializers import serialize_message
from app.core import metrics
from app.core.config.storage import (
    CHAT_MAX_MESSAGE_LENGTH,
    CHAT_MAX_WEBSOCKET_FRAME_BYTES,
)
from app.core.logging import get_logger
from app.models.chat import Message

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# ── Route-handler helpers (still needed here) ──────────────────────────────
# These helpers are used by websocket_chat route handler which is defined below.
# Everything else has moved to app/api/ws/ subpackage.


async def _get_online_users_for_user(user_id: uuid.UUID) -> list[uuid.UUID]:
    """Return online user IDs limited to the current user's chat participants."""
    from app.api.ws.presence import _get_presence_audience

    audience = await _get_presence_audience(user_id)
    return [target_id for target_id in audience if manager.is_online(target_id)]


def _get_websocket_audit_context(websocket: WebSocket) -> dict[str, Any]:
    client = websocket.client
    return {
        "ws_path": websocket.url.path,
        "ws_client": client.host if client else None,
    }


async def start_presence_pubsub() -> None:
    await presence_pubsub.initialize()


async def stop_presence_pubsub() -> None:
    await presence_pubsub.shutdown()


# MOVED: _handle_presence_pubsub is now in app/api/ws/presence.py


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time chat.

    Authentication (RZ-W14-01 — JWT-in-protocol-header path removed):
    - Preferred: one-time upgrade ticket via ?ticket=<ott>
      (obtain via POST /ws/ticket while authenticated via cookie/Bearer)
    - Fallback: HttpOnly access_token_v2 cookie (cookie-capable browsers)

    Message types (from client):\n    - {"type": "ping"} - Keep-alive ping
    - {"type": "read", "chat_id": "..."} - Legacy direct-backend receipt (REST is canonical for ws-hub clients)
    - {"type": "get_online"} - Admin-only legacy presence query

    Message types (to client):
    - {"type": "pong"} - Response to ping
    - {"type": "new_message", "chat_id": "...", "message": {...}} - New message received
    - {"type": "typing", "chat_id": "...", "user_id": ...} - Someone is typing
    - {"type": "read", "chat_id": "...", "user_id": ..., "read_at": "..."}
      - Chat-level read receipt
    - {"type": "message_edited", "chat_id": "...", "message_id": "...", "content": "...", "edited_at": "..."}
      - REST edit broadcast
    - {"type": "message_deleted", "chat_id": "...", "message_id": "...", "deleted_at": "..."}
      - REST delete broadcast
    - {"type": "reaction_changed", "chat_id": "...", "message_id": "...", "user_id": "...", "emoji": "...", "action": "added|removed"}
      - REST reaction broadcast
    - {"type": "replay_checkpoint", "chat_id": "..."}
      - ws-hub replay poison-event checkpoint
    - {"type": "online_list", "users": ["..."]} - Admin presence response
    - {"type": "rate_limit_exceeded"} - ws-hub control frame
    - {"type": "presence", "user_id": ..., "active": true/false, "last_seen": "..."}
      - Participant presence updates
    - {"type": "error", "message": "..."} - Error message
    """
    # MED-W19: Origin check removed from here — it is a duplicate of the check
    # already performed inside authenticator.authenticate_upgrade() (see
    # app/api/ws/authenticator.py).  Keeping both was redundant and could cause
    # divergence if the allowlist logic was updated in only one place.

    import orjson

    from app.api.ws.authenticator import authenticator
    from app.api.ws.dispatcher import MessageDispatcher

    user, session_jti, selected_subprotocol = await authenticator.authenticate_upgrade(
        websocket
    )

    if not user:
        logger.warning(
            "WebSocket auth failed - no valid credentials"
        )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        await websocket.close(code=4001, reason="Authentication required")
        return

    # Connect and register — may reject if per-user limit is reached
    accepted = await manager.connect(
        websocket, user.id, subprotocol=selected_subprotocol
    )
    if not accepted:
        return  # close frame already sent inside connect()

    metrics.inc_ws_connections(path="/ws/chat")
    last_seen = await _update_last_seen(session_jti)
    await manager.broadcast_presence(
        user.id,
        True,
        last_seen,
        source=PRESENCE_SOURCE_CONNECT,
        force=True,
    )

    try:
        dispatcher = MessageDispatcher(manager)
        while True:
            try:
                text_data = await websocket.receive_text()
                if (
                    len(text_data) > CHAT_MAX_MESSAGE_LENGTH
                    or len(text_data.encode("utf-8")) > CHAT_MAX_WEBSOCKET_FRAME_BYTES
                ):
                    logger.warning(
                        "WS payload too large from user %s", user.id
                    )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                    await websocket.close(code=1009, reason="Payload too large")
                    return

                # 1. Message Rate Limiting (Audit 6.3)
                if not manager.check_rate_limit(websocket):
                    logger.warning(
                        "WS rate limit exceeded for user %s - dropping message",
                        user.id,
                    )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                    await websocket.send_json(
                        {"type": "error", "message": "Rate limit exceeded"}
                    )
                    await asyncio.sleep(0.1)
                    continue

                data = orjson.loads(text_data)
            except (json.JSONDecodeError, ValueError, orjson.JSONDecodeError) as exc:
                # MOD-14-04 (audit 2026-03-23): Log malformed frames with a frame preview
                # so ops can distinguish bugs (e.g. wrong Content-Type) from active
                # fuzzing probes during incident investigation. The 200-char truncation
                # prevents log inflation from crafted large payloads.
                frame_preview = (
                    text_data[:200] if isinstance(text_data, str) else "<non-text>"
                )
                logger.warning(
                    "Malformed WebSocket frame from user %s: %s — frame preview: %r",
                    getattr(user, "id", "unknown"),
                    exc,
                    frame_preview,
                )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            await dispatcher.dispatch(websocket, user, session_jti, data)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s", user.id)
    except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — WebSocket loop must not crash without cleanup (reviewed TD-27-04)
        # Unexpected error in the WebSocket loop: log at ERROR so Sentry captures
        # the full traceback. The connection is cleaned up regardless.
        logger.exception("WebSocket unexpectedly closed for user %s", user.id)
    finally:
        # Guaranteed execution of cleanup and presence state update to prevent Zombie Users
        await manager.disconnect(websocket)
        try:
            last_seen = await _update_last_seen(session_jti)
        except (
            OSError,
            ConnectionError,
        ):  # RZ-22-01: narrowed — DB/network errors during last_seen update
            last_seen = datetime.now(UTC)
        await manager.broadcast_presence(
            user.id,
            False,
            last_seen,
            source=PRESENCE_SOURCE_DISCONNECT,
            force=True,
        )
        metrics.dec_ws_connections(path="/ws/chat")
        logger.info("WebSocket cleanup for user %s", user.id)


async def notify_new_message(
    message: Message, exclude_user_id: uuid.UUID | None = None
) -> int:
    """
    Notify chat participants about a new message via WebSocket.
    Call this from the chat API after saving a message.

    Returns the number of successful notifications sent.
    """
    presence = await build_presence_map([message.sender_id])
    metrics.record_chat_message(channel=str(message.chat_id))
    return await manager.broadcast_to_chat(
        message.chat_id,
        {
            "type": "new_message",
            "chat_id": message.chat_id,
            "message": serialize_message(message, presence),
        },
        exclude_user_id=exclude_user_id,
    )
