import uuid
from typing import Any

from fastapi import WebSocket

from app.api.ws.auth import update_last_seen
from app.api.ws.presence import PRESENCE_SOURCE_PING
from app.core.database import async_session
from app.core.logging import get_logger
from app.models.enums import UserRole
from app.repositories.chat_repository import ChatRepository
from app.services.audit_service import SecurityEvent, audit_service

logger = get_logger(__name__)


class MessageDispatcher:
    """Dispatches incoming WebSocket messages to appropriate handlers."""

    def __init__(self, manager: Any):
        self.manager = manager

    async def _get_online_users_for_user(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Return online user IDs limited to the current user's chat participants."""
        from app.api.ws.presence import _get_presence_audience

        audience = await _get_presence_audience(user_id)
        return [
            target_id for target_id in audience if self.manager.is_online(target_id)
        ]

    def _get_websocket_audit_context(self, websocket: WebSocket) -> dict[str, Any]:
        client = websocket.client
        return {
            "ws_path": websocket.url.path,
            "ws_client": client.host if client else None,
        }

    async def dispatch(
        self,
        websocket: WebSocket,
        user: Any,
        session_jti: str | None,
        data: dict[str, Any],
    ) -> None:
        """Process a single JSON message from the client."""
        msg_type = data.get("type")

        if msg_type == "ping":
            last_seen = await update_last_seen(session_jti)
            await websocket.send_json({"type": "pong"})
            await self.manager.broadcast_presence(
                user.id,
                True,
                last_seen,
                source=PRESENCE_SOURCE_PING,
            )

        elif msg_type == "read":
            # Legacy direct-backend clients may still send a chat-level read
            # command. The browser-facing ws-hub path uses REST mark-read as the
            # canonical owner, but retaining this compatibility path avoids
            # breaking standalone backend deployments and old clients.
            chat_id = data.get("chat_id")
            if chat_id:
                try:
                    chat_uuid = (
                        uuid.UUID(chat_id) if isinstance(chat_id, str) else chat_id
                    )
                except ValueError:
                    await websocket.send_json(
                        {"type": "error", "message": "Invalid chat_id format"}
                    )
                    return

                async with async_session() as session:
                    repo = ChatRepository(session)
                    is_participant = await repo.check_participant(chat_uuid, user.id)

                    if not is_participant:
                        logger.warning(
                            "User %s tried to mark chat %s read without being a participant",
                            user.id,
                            chat_id,
                        )
                        await websocket.send_json(
                            {"type": "error", "message": "Access denied"}
                        )
                        return

                    # The dispatcher does not load the chat (only checks
                    # participation), so fetch chat_type before selecting the
                    # DM read_status or group high-water-mark implementation.
                    chat_type = await repo.get_chat_type(chat_uuid)
                    read_at, affected = await repo.mark_messages_read(
                        chat_uuid, user.id, chat_type or "dm"
                    )
                    await session.commit()

                if affected > 0:
                    await self.manager.broadcast_to_chat(
                        chat_uuid,
                        {
                            "type": "read",
                            "chat_id": str(chat_uuid),
                            "user_id": str(user.id),
                            "read_at": read_at.isoformat(),
                        },
                        exclude_user_id=user.id,
                    )

        elif msg_type == "get_online":
            if user.role != UserRole.ADMIN:
                audit_service.log(
                    SecurityEvent.ACCESS_DENIED,
                    user_id=user.id,
                    reason="admin_required",
                    action="presence.get_online",
                    **self._get_websocket_audit_context(websocket),
                )
                await websocket.send_json({"type": "error", "message": "Access denied"})
                return

            online = await self._get_online_users_for_user(user.id)
            audit_service.log(
                "presence.online_list",
                user_id=user.id,
                action="presence.get_online",
                result_count=len(online),
                scope="chat_participants",
                **self._get_websocket_audit_context(websocket),
            )
            # RZ-33-08: Convert UUIDs to strings — json.dumps cannot serialize uuid.UUID.
            await websocket.send_json(
                {"type": "online_list", "users": [str(u) for u in online]}
            )

        else:
            await websocket.send_json(
                {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )
