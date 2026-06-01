"""Chat notification service — fan-out for new-message events.

Two delivery channels run in parallel for every new message:

1. WebSocket broadcast via ``ws_manager.broadcast_to_chat`` — every
   connected participant *except the sender* receives a serialised
   message payload in real time.
2. Push notification via ``create_notifications_for_users`` — every
   non-sender participant gets an in-app + push entry. UUIDs in
   ``payload_data`` are stringified because UUID is not natively
   JSON-serialisable. Wave 208 — when the message replies to another
   user, that quoted author is *superseded* off the generic
   ``chat.message`` onto a specific ``chat.reply`` entry (see
   ``notify_new_message``); no double-notify.

The body preview is truncated at 100 chars + "..." to keep push payloads
under platform-imposed size limits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any  # TD-23-04 (audit 2026-03-25 Wave 23)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.protocols import AsyncDatabaseSession
    from app.models import User
    from app.models.chat import Message
    from app.schemas.dtos import ChatParticipantDTO

from app.api.ws.connection_manager import manager as ws_manager
from app.api.ws.presence import build_presence_map
from app.api.ws.serializers import serialize_message
from app.services.notifications import create_notifications_for_users


class ChatNotificationService:
    """Handles real-time and push notifications for chat events. (TD-1)"""

    def __init__(self, session: AsyncDatabaseSession) -> None:
        self.session = session

    async def notify_new_message(
        self,
        message: Message,
        chat_participants: Sequence[User | ChatParticipantDTO],
        sender: User,
        replied: Any = None,
        chat_type: str = "dm",
        chat_name: str | None = None,
    ) -> None:
        """Notify participants about a new message.

        Wave 207 — ``replied`` is the replied-to message (a MessageDTO, loaded by
        handle_message_sent) or None; it is passed to serialize_message so the
        recipient's live new_message bubble carries the reply quote preview.

        Wave 208 — reply-notification SUPERSEDE: when ``replied`` belongs to a
        DIFFERENT user, that quoted author is dropped from the generic
        ``chat.message`` push and instead receives a specific ``chat.reply``
        notification — no double-notify. In a 1-on-1 DM the quoted author is the
        only other participant, so the generic list empties and they receive
        exactly one ``chat.reply`` entry. The live WebSocket frame above is
        unchanged — only the persistent bell/push entry upgrades. Self-replies
        (``replied.sender_id == sender.id``) are ignored.

        Wave 210 G3 — group notification re-tiering. The fan-out was already
        N-participant-capable (the recipient list excludes only the sender); G3
        makes a GROUP push DISTINGUISHABLE from a DM push by carrying the group's
        identity: a DM titles by sender name with a bare body (the recipient knows
        the 1-on-1 counterpart), while a GROUP titles by ``chat_name`` and prefixes
        the body with the sender ("Alice: hi") so the recipient learns BOTH which
        group AND who posted. ``chat_type``/``chat_name`` are passed by
        handle_message_sent (which already holds the chat DTO); they default to a
        DM so existing callers/tests are unaffected.
        """
        # WebSocket real-time notification
        presence = await build_presence_map([message.sender_id])
        await ws_manager.broadcast_to_chat(
            message.chat_id,
            {
                "type": "new_message",
                "chat_id": str(message.chat_id),
                "message": serialize_message(message, presence, replied=replied),
            },
            exclude_user_id=sender.id,
        )

        # Push Notification
        other_participants = [p.id for p in chat_participants if p.id != sender.id]

        # Wave 208 — reply-notification SUPERSEDE. When this message replies to
        # ANOTHER user, drop that quoted author from the generic chat.message
        # recipients and send them a specific chat.reply entry below instead, so
        # they are notified exactly once. Self-replies are ignored (no exclusion,
        # no chat.reply). ``replied`` is None when the message is not a reply or
        # its target was hard-deleted (the SET NULL self-FK already nulled the
        # column by the time handle_message_sent reads it).
        is_reply_to_other = replied is not None and replied.sender_id != sender.id
        if is_reply_to_other:
            other_participants = [
                uid for uid in other_participants if uid != replied.sender_id
            ]

        if other_participants or is_reply_to_other:
            sender_name = (sender.profile and sender.profile.full_name) or "User"
            content = message.content or ""
            body_preview = content[:100] + "..." if len(content) > 100 else content

            # Wave 210 G3 — group pushes carry the group's identity (see the
            # method docstring). A DM keeps sender-name title + bare body; a group
            # titles by name + prefixes the body with the sender. The empty-body
            # guard avoids a dangling "Alice: " when an attachment-only message
            # has no text.
            if chat_type == "group":
                notif_title = chat_name or "Group"
                notif_body = (
                    f"{sender_name}: {body_preview}" if body_preview else sender_name
                )
            else:
                notif_title = sender_name
                notif_body = body_preview

            if other_participants:
                await create_notifications_for_users(
                    self.session,
                    title=notif_title,
                    body=notif_body,
                    type="chat.message",
                    url=f"/messenger/{message.chat_id}",
                    tag=f"chat:{message.chat_id}",
                    user_ids=other_participants,
                    topic="chat",
                    payload_data={
                        # HIGH-W19: wrap UUID fields with str() to avoid JSON
                        # serialization errors — UUID is not natively JSON-serialisable.
                        "chatId": str(message.chat_id),
                        "senderId": str(sender.id),
                        "messageId": str(message.id),
                    },
                )

            if is_reply_to_other:
                # Specific "X replied to your message" entry for the quoted author.
                # dedupe_key is keyed on the *replying* message id so an outbox
                # retry of the same reply is idempotent, while each new reply stays
                # a distinct notification. ``type`` alone distinguishes it for the
                # FE (NotificationsBell renders generically) — no new FE i18n key.
                await create_notifications_for_users(
                    self.session,
                    title=notif_title,
                    body=notif_body,
                    type="chat.reply",
                    url=f"/messenger/{message.chat_id}",
                    tag=f"chat-reply:{replied.id}",
                    dedupe_key=f"chat-reply:{message.id}",
                    user_ids=[replied.sender_id],
                    topic="chat",
                    payload_data={
                        "chatId": str(message.chat_id),
                        "repliedToMessageId": str(replied.id),
                        "replyingMessageId": str(message.id),
                        "senderId": str(sender.id),
                    },
                )
