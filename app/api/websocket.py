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
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.ws.auth import (
    extract_bearer_token as _extract_bearer_token,
)
from app.api.ws.auth import (
    extract_token_from_subprotocol as _extract_token_from_subprotocol,
)
from app.api.ws.auth import (
    get_user_from_cookie,
    get_user_from_token,
)
from app.api.ws.auth import (
    select_subprotocol as _select_subprotocol,
)
from app.api.ws.auth import (
    update_last_seen as _update_last_seen,
)

# ── Sub-package imports (re-exported for backwards compat) ─────────────────────
from app.api.ws.connection_manager import (
    ConnectionManager,
    WebSocketRateLimiter,
    get_connection_manager,
    manager,
)
from app.api.ws.presence import (
    PRESENCE_SOURCE_CONNECT,
    PRESENCE_SOURCE_DISCONNECT,
    PRESENCE_SOURCE_PING,
    PRESENCE_SOURCE_PUBSUB,
    PresencePubSub,
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
    presence_pubsub,
)
from app.api.ws.serializers import build_presence_map, serialize_message
from app.core import metrics
from app.core.config import settings
from app.core.database import async_session
from app.core.feature_flags import feature_flags
from app.models.chat import Message
from app.models.enums import UserRole
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import SecurityEvent, audit_service

logger = logging.getLogger(__name__)
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


async def _handle_presence_pubsub(payload: dict[str, Any]) -> None:
    """Handle a presence update received from Redis pub/sub.

    RZ-07 (audit 2026-03-04): Validate the user_id from the payload before
    broadcasting.  A misconfigured or compromised Redis channel could inject
    arbitrary user_ids, spoofing presence for any user's contacts.
    Only forward updates for users who already have an active connection on
    this pod.
    """
    try:
        raw_user_id = payload.get("user_id")
        if not raw_user_id:
            return
        user_id = uuid.UUID(str(raw_user_id))
    except (ValueError, AttributeError):
        logger.warning("presence pubsub: invalid user_id in payload")
        return

    if not manager.is_online(user_id):
        return

    active = bool(payload.get("active", False))
    last_seen_raw = payload.get("last_seen")
    try:
        last_seen = datetime.fromisoformat(last_seen_raw) if last_seen_raw else None
    except ValueError:
        last_seen = None

    await manager.broadcast_presence(
        user_id,
        active,
        last_seen,
        source=PRESENCE_SOURCE_PUBSUB,
        force=True,
        publish=False,
    )


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time chat.

    Authentication:
    - Send JWT in `Sec-WebSocket-Protocol` (e.g. `access_token, <JWT>`), OR
    - Send `Authorization: Bearer <JWT>` header, OR
    - Use cookie-based auth (access_token cookie)
    - Query param `token` can be enabled temporarily via
      feature flag `websocket_query_param_compat`

    Message types (from client):\n    - {"type": "ping"} - Keep-alive ping
    - {"type": "typing", "chat_id": "..."} - Typing indicator
    - {"type": "read", "chat_id": "...", "message_id": "..."} - Mark message as read

    Message types (to client):
    - {"type": "pong"} - Response to ping
    - {"type": "new_message", "chat_id": "...", "message": {...}} - New message received
    - {"type": "typing", "chat_id": "...", "user_id": ...} - Someone is typing
    - {"type": "read", "chat_id": "...", "message_id": "...", "user_id": ...}
      - Message read
    - {"type": "presence", "user_id": ..., "active": true/false, "last_seen": "..."}
      - Participant presence updates
    - {"type": "error", "message": "..."} - Error message
    """
    # --- RZ-6: CSRF protection for WebSocket (audit 2026-02-26) ---
    # WebSocket upgrades are exempt from the CSRF middleware because they use
    # HTTP Upgrade — the browser attaches cookies automatically, making cookie-
    # authenticated WebSocket connections vulnerable to CSRF from any origin.
    # Mitigation: validate the Origin header against the CORS allowlist *before*
    # accepting the upgrade.  Allowed origins are the same set used by CORSMiddleware.
    # Native clients (no Origin header) are permitted to connect via explicit JWT.
    _origin = websocket.headers.get("origin")
    if _origin is not None:
        _allowed_origins: set[str] = set(
            getattr(settings, "cors_allow_origins_list", [])
            or getattr(settings, "frontend_origins", "").split(",")
        )
        # Normalise: strip trailing slash and lowercase scheme+host
        _origin_normalised = _origin.rstrip("/").lower()
        _allowed_normalised = {o.rstrip("/").lower() for o in _allowed_origins if o}
        if _origin_normalised not in _allowed_normalised:
            logger.warning("WebSocket rejected: Origin '%s' not in allowlist", _origin)
            await websocket.close(code=4403, reason="Origin not allowed")
            return
    # ------------------------------------------------------------------

    user = None
    session_jti = None

    # Debug: log incoming connection info

    auth_header = websocket.headers.get("authorization")
    protocol_header = websocket.headers.get("sec-websocket-protocol")
    header_token = _extract_bearer_token(auth_header)
    protocol_token = _extract_token_from_subprotocol(protocol_header)
    selected_subprotocol = _select_subprotocol(protocol_header)

    if header_token or protocol_token:
        logger.info(
            "Attempting WebSocket token auth from headers (auth=%s, protocol=%s)",
            bool(header_token),
            bool(protocol_token),
        )
        token_str = str(header_token or protocol_token)
        user, session_jti = await get_user_from_token(token_str)
        if user:
            logger.info("Token auth successful: user_id=%s", user.id)
        else:
            logger.warning("Token auth failed: invalid token")

    # Fallback to cookie-based auth
    if not user:
        # MOD-6: Use OpenFeature client for evaluations
        is_query_param_enabled = feature_flags.of_client.get_boolean_value(
            "websocket_query_param_compat",
            default_value=False,
        )
        if is_query_param_enabled:
            token = websocket.query_params.get("token")
            if token:
                # RZ-4 (audit 2026-02-26): Query-param tokens appear in nginx/caddy
                # access logs and browser history. Log a security event WITHOUT
                # logging the token value, then attempt authentication as normal.
                logger.warning(
                    "SECURITY DEPRECATION: WebSocket token passed via query param. "
                    "This exposure vector will be removed; use Authorization header or "
                    "Sec-WebSocket-Protocol instead. "
                    "Disable websocket_query_param_compat feature flag to block this path."
                )
                # Emit a structured security event for alerting pipelines.
                try:
                    from app.deps.cache import get_cache_client
                    from app.services.fraud_detection_service import (
                        FraudDetectionService,
                    )

                    _rc = await get_cache_client()
                    _fds = FraudDetectionService(_rc)
                    await _fds.record_event(
                        {
                            "event": "ws.token_query_param",
                            "severity": "medium",
                            "client_host": websocket.client.host
                            if websocket.client
                            else "",
                        }
                    )
                except Exception:
                    pass  # Fraud detection is best-effort, never block the request
                user, session_jti = await get_user_from_token(token)
                if user:
                    logger.info("Token auth successful: user_id=%s", user.id)
                else:
                    logger.warning("Token auth failed: invalid token")

    if not user:
        access_token = websocket.cookies.get("access_token_v2")
        logger.info(
            "Attempting cookie auth, access_token present: %s", bool(access_token)
        )
        if access_token:
            user, session_jti = await get_user_from_cookie(access_token)
            if user:
                logger.info("Cookie auth successful: user_id=%s", user.id)
            else:
                logger.warning("Cookie auth failed: invalid cookie")

    if not user:
        logger.warning("WebSocket auth failed - no valid credentials")
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
        # Send initial online status to user's contacts
        # (In a full implementation, you'd notify friends/chat participants)

        while True:
            try:
                # 1. Message Rate Limiting (Audit 6.3)
                if not manager.check_rate_limit(websocket):
                    logger.warning(
                        "WS rate limit exceeded for user %s - dropping message",
                        user.id,
                    )
                    await websocket.send_json(
                        {"type": "error", "message": "Rate limit exceeded"}
                    )
                    # We don't necessarily disconnect, just drop the spam message.
                    # But we should sleep a bit to prevent tight-looping on the client.
                    await asyncio.sleep(0.1)
                    continue

                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                last_seen = await _update_last_seen(session_jti)
                await websocket.send_json({"type": "pong"})
                await manager.broadcast_presence(
                    user.id,
                    True,
                    last_seen,
                    source=PRESENCE_SOURCE_PING,
                )

            elif msg_type == "typing":
                chat_id = data.get("chat_id")
                if chat_id:
                    # Validate user is participant to prevent IDOR
                    try:
                        chat_uuid = (
                            uuid.UUID(chat_id) if isinstance(chat_id, str) else chat_id
                        )
                        async with async_session() as session:
                            repo = ChatRepository(session)
                            is_participant = await repo.check_participant(
                                chat_uuid, user.id
                            )

                        if not is_participant:
                            logger.warning(
                                "Access denied: User %s tried to send typing "
                                "indicator to chat %s without being a participant",
                                user.id,
                                chat_id,
                            )
                            await websocket.send_json(
                                {"type": "error", "message": "Access denied"}
                            )
                            continue
                    except ValueError:
                        await websocket.send_json(
                            {"type": "error", "message": "Invalid chat_id format"}
                        )
                        continue

                    # Broadcast typing indicator to other participants
                    await manager.broadcast_to_chat(
                        chat_uuid,
                        {
                            "type": "typing",
                            "chat_id": str(chat_uuid),
                            "user_id": str(user.id),
                            "user_name": getattr(user.profile, "full_name", None)
                            if getattr(user, "profile", None)
                            else str(user.email),
                        },
                        exclude_user_id=user.id,
                    )

            elif msg_type == "read":
                chat_id = data.get("chat_id")
                message_id = data.get("message_id")
                if chat_id and message_id:
                    # Update message read status in DB
                    async with async_session() as session:
                        repo = ChatRepository(session)
                        # Verify that the user is a participant of the chat (Fix IDOR)
                        is_participant = await repo.check_participant(chat_id, user.id)

                        if not is_participant:
                            logger.warning(
                                f"User {user.id} tried to mark message {message_id} "
                                f"as read in chat {chat_id} without being a participant"
                            )
                            await websocket.send_json(
                                {"type": "error", "message": "Access denied"}
                            )
                            continue

                        msg = await repo.get_message_by_id(message_id)
                        if msg and msg.chat_id == chat_id and msg.sender_id != user.id:
                            await repo.mark_single_message_read(message_id)
                            await session.commit()

                            # Notify sender that message was read
                            await manager.send_to_user(
                                msg.sender_id,
                                {
                                    "type": "read",
                                    "chat_id": chat_id,
                                    "message_id": message_id,
                                    "user_id": user.id,
                                },
                            )

            elif msg_type == "get_online":
                if user.role != UserRole.ADMIN.value:
                    audit_service.log(
                        SecurityEvent.ACCESS_DENIED,
                        user_id=user.id,
                        reason="admin_required",
                        action="presence.get_online",
                        **_get_websocket_audit_context(websocket),
                    )
                    await websocket.send_json(
                        {"type": "error", "message": "Access denied"}
                    )
                    continue

                online = await _get_online_users_for_user(user.id)
                audit_service.log(
                    "presence.online_list",
                    user_id=user.id,
                    action="presence.get_online",
                    result_count=len(online),
                    scope="chat_participants",
                    **_get_websocket_audit_context(websocket),
                )
                await websocket.send_json({"type": "online_list", "users": online})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        last_seen = await _update_last_seen(session_jti)
        await manager.broadcast_presence(
            user.id,
            False,
            last_seen,
            source=PRESENCE_SOURCE_DISCONNECT,
            force=True,
        )
        logger.info("WebSocket disconnected for user %s", user.id)
    except Exception:
        # Unexpected error in the WebSocket loop: log at ERROR so Sentry captures
        # the full traceback. The connection is cleaned up regardless.
        logger.exception("WebSocket unexpectedly closed for user %s", user.id)
        await manager.disconnect(websocket)
        last_seen = await _update_last_seen(session_jti)
        await manager.broadcast_presence(
            user.id,
            False,
            last_seen,
            source=PRESENCE_SOURCE_DISCONNECT,
            force=True,
        )
    finally:
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
