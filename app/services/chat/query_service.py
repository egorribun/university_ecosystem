"""Chat query service — read-only operations on chats and messages.

This service owns every cursor-paginated read for the chat domain
(chat list, message list, single chat, attachment list) plus the
participant + presence enrichment that turns repository rows into
``ChatResponse`` / ``MessagesListOut`` DTOs.

It does NOT mutate state; that belongs to ``ChatCommandService``
(message dispatch, mark-read, clear-history) and ``ChatCreationService``
(DM creation, Redis lock).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast  # TD-23-04 (audit 2026-03-25 Wave 23)

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession
    from app.models import User
    from app.schemas.chat import (
        AttachmentResponse,
        ChatParticipant,
        ChatResponse,
        ChatsListOut,
        MessageResponse,
        MessagesListOut,
    )
    from app.schemas.dtos.chat import MessageReactionDTO

from app.api.validation import ensure_exists, raise_forbidden
from app.api.ws.presence import build_presence_map
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    ChatResponse,
    ChatsListOut,
    MessageResponse,
    MessagesListOut,
    PresenceStatus,
    ReactionAggregate,
)


def _aggregate_reactions(
    rows: list[MessageReactionDTO], current_user_id: uuid.UUID
) -> list[ReactionAggregate]:
    """Wave 206 — fold raw reaction rows into per-emoji aggregates.

    Preserves first-seen emoji order. ``reacted_by_me`` is set when the requesting
    user reacted with that emoji (server-computed here on the REST path; on the WS
    delta-frame path the client derives it locally). Built via plain counters and
    constructed at the end so it never mutates a (possibly frozen) pydantic model.
    """
    counts: dict[str, int] = {}
    mine: set[str] = set()
    order: list[str] = []
    for r in rows:
        if r.emoji not in counts:
            counts[r.emoji] = 0
            order.append(r.emoji)
        counts[r.emoji] += 1
        if r.user_id == current_user_id:
            mine.add(r.emoji)
    return [
        ReactionAggregate(emoji=e, count=counts[e], reacted_by_me=(e in mine))
        for e in order
    ]


class ChatQueryService:
    """Handles read-only operations for chats and messages. (TD-1)"""

    def __init__(
        self, session: AsyncDatabaseSession, repository: ChatRepository
    ) -> None:
        self.session = session
        self.repository = repository

    async def get_chats(
        self, user: User, cursor: str | None, limit: int
    ) -> ChatsListOut:
        """Fetch chat list for a user, including metadata and last messages."""
        rows, has_more, next_cursor = await self.repository.get_chats_for_user(
            user.id, cursor, limit
        )

        participant_ids: set[uuid.UUID] = set()
        chat_data_map: dict[str, dict[str, Any]] = {}

        for row in rows:
            chat = row[0]
            unread_count = row[1] or 0
            last_message_id = row[2]

            for participant in chat.participants:
                participant_ids.add(participant.id)

            chat_data_map[str(chat.id)] = {
                "chat": chat,
                "unread_count": unread_count,
                "last_message_id": last_message_id,
            }

        last_message_ids = [
            d["last_message_id"] for d in chat_data_map.values() if d["last_message_id"]
        ]
        last_messages_map = await self.repository.get_last_messages(last_message_ids)

        pre_responses: list[ChatResponse] = []
        for chat_id, data in chat_data_map.items():
            chat = data["chat"]
            last_message = last_messages_map.get(data["last_message_id"])

            pre_responses.append(
                ChatResponse(
                    id=chat.id,
                    participants=cast("list[ChatParticipant]", chat.participants),
                    last_message=cast("MessageResponse | None", last_message),
                    unread_count=data["unread_count"],
                    created_at=chat.created_at,
                    updated_at=chat.updated_at,
                )
            )

        presence_map = await build_presence_map(participant_ids, db=self.session)

        enriched_chats: list[ChatResponse] = []
        for chat_resp in pre_responses:
            l_msg = chat_resp.last_message
            if l_msg is not None:
                l_msg = MessageResponse(
                    id=l_msg.id,
                    chat_id=l_msg.chat_id,
                    sender_id=l_msg.sender_id,
                    content=l_msg.content,
                    created_at=l_msg.created_at,
                    read_status=l_msg.read_status,
                    read_at=l_msg.read_at,  # Wave 203 SW8 fix — was dropped (defaulted None)
                    edited_at=l_msg.edited_at,  # Wave 205 SW4 — W203 SW8 gotcha
                    deleted_at=l_msg.deleted_at,  # Wave 205 SW4 — W203 SW8 gotcha
                    sender=l_msg.sender,
                    attachments=l_msg.attachments,
                    sender_presence=presence_map.get(l_msg.sender_id),
                    # Wave 206 — chat-list last-message preview is a lightweight
                    # projection (no reaction selectinload); pills render only in the
                    # message list (W203-SW8 two-site rule — explicit empty here).
                    reactions=[],
                )

            participant_status: dict[uuid.UUID, PresenceStatus] = {}
            for p_item in chat_resp.participants:
                participant_status[p_item.id] = presence_map.get(
                    p_item.id, PresenceStatus()
                )

            enriched_chats.append(
                ChatResponse(
                    **chat_resp.model_dump(exclude={"last_message", "presence"}),
                    last_message=l_msg,
                    presence=participant_status,
                )
            )

        return ChatsListOut(
            items=enriched_chats,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def get_chat_details(
        self, chat_id: uuid.UUID, user: User, locale: str
    ) -> ChatResponse:
        """Get details for a specific chat."""
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        unread_count = await self.repository.get_unread_count(chat_id, user.id)
        last_message = await self.repository.get_last_message(chat_id)

        presence_map = await build_presence_map(
            [p.id for p in chat.participants], db=self.session
        )
        participant_status = {
            p.id: presence_map.get(p.id, PresenceStatus()) for p in chat.participants
        }

        return ChatResponse(
            id=chat.id,
            participants=cast("list[ChatParticipant]", chat.participants),
            last_message=cast("MessageResponse | None", last_message),
            unread_count=unread_count,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            presence=participant_status,
        )

    async def get_messages(
        self,
        chat_id: uuid.UUID,
        user: User,
        cursor: str | None,
        limit: int,
        locale: str,
    ) -> MessagesListOut:
        """Fetch messages for a chat."""
        chat = await self.repository.get_by_id(chat_id)
        ensure_exists(chat, "chat", locale)
        assert chat is not None  # noqa: S101

        participant_ids = {p.id for p in chat.participants}
        if user.id not in participant_ids:
            raise_forbidden(locale, "errors.chat.not_participant")

        messages, has_more, next_cursor = await self.repository.get_messages(
            chat_id, cursor, limit
        )

        messages = list(reversed(messages))

        presence_map = await build_presence_map(
            {msg.sender_id for msg in messages}, db=self.session
        )

        response_items = [
            MessageResponse(
                id=msg.id,
                chat_id=msg.chat_id,
                sender_id=msg.sender_id,
                content=msg.content,
                created_at=msg.created_at,
                read_status=msg.read_status,
                read_at=msg.read_at,  # Wave 203 SW8 fix — was dropped (defaulted None)
                edited_at=msg.edited_at,  # Wave 205 SW4 — W203 SW8 gotcha
                deleted_at=msg.deleted_at,  # Wave 205 SW4 — W203 SW8 gotcha
                # LOW-W19: sender is intentionally omitted here.  The message
                # list query uses a lightweight projection that does not eagerly
                # load the full sender relationship in order to avoid N+1 queries.
                # Caller receives sender_id and can resolve the profile separately
                # if needed.  If full sender data is required, add a joined-load
                # to ChatRepository.get_messages() and remove this comment.
                sender=None,
                attachments=cast("list[AttachmentResponse]", msg.attachments),
                sender_presence=presence_map.get(msg.sender_id),
                # Wave 206 — aggregate the selectinload'd reaction rows; reacted_by_me
                # is computed for the requesting user (W203-SW8 two-site rule).
                reactions=_aggregate_reactions(msg.reactions, user.id),
            )
            for msg in messages
        ]

        return MessagesListOut(
            items=response_items,
            has_more=has_more,
            next_cursor=next_cursor,
        )
