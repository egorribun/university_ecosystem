from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from opentelemetry import trace
from sqlalchemy import and_, delete, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.core.protocols import AsyncDatabaseSession
from app.models import User
from app.models.chat import (
    Chat,
    Message,
    MessageReaction,
    chat_participants,
    utc_now,
)
from app.repositories.base import BaseRepository
from app.schemas.dtos.chat import ChatDTO, MessageDTO
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

# P-02 (audit 2026-03-08): Module-level tracer for chat repository spans.
# SQLAlchemyInstrumentor (observability.py) already adds DB-level spans;
# these add semantic context (chat_id, user_id) for easier trace filtering.
_tracer = trace.get_tracer("app.repositories.chat")


class ChatRepository(BaseRepository[Chat, ChatDTO, dict[str, Any], dict[str, Any]]):
    @property
    def model(self) -> type[Chat]:
        return Chat

    @property
    def dto_class(self) -> type[ChatDTO]:
        return ChatDTO

    async def _set_rls_user(self, user_id: uuid.UUID) -> None:
        """Set app.current_user_id for the current transaction.

        MOD-02 (audit Wave 11): PostgreSQL RLS on the ``messages`` table uses
        ``current_setting('app.current_user_id', TRUE)`` to filter rows.
        ``SET LOCAL`` scopes the GUC to the current transaction, so the value
        is automatically cleared when the transaction commits or rolls back —
        no explicit cleanup required.  Must be called inside an open
        transaction before any query that touches ``messages``.
        """
        # HIGH-W19: SET LOCAL is only valid inside an active transaction;
        # outside one it would silently apply for the rest of the session
        assert self.db.in_transaction(), "SET LOCAL requires an active transaction"  # noqa: S101
        await self.db.execute(
            text("SET LOCAL app.current_user_id = :uid"),
            {"uid": str(user_id)},
        )

    async def get_by_id(
        self, chat_id: uuid.UUID, load_messages: bool = False
    ) -> ChatDTO | None:
        """
        Fetch a chat by its ID.
        """
        load_options = [selectinload(Chat.participants)]
        if load_messages:
            load_options.append(
                selectinload(Chat.messages).options(
                    selectinload(Message.sender),
                    selectinload(Message.attachments),
                )
            )
        row = await self.db.get(Chat, chat_id, options=load_options)
        return self._to_dto(row) if row else None

    async def get_chats_for_user(
        self, user_id: uuid.UUID, cursor: str | None, limit: int
    ) -> tuple[list[tuple[ChatDTO, int, str | None]], bool, str | None]:
        """
        Fetch chats for a user with pagination and metadata.

        TD-NEW-03 (audit 2026-03): Replaced 3 correlated scalar subqueries with
        2 CTEs that each scan the ``message`` table once. The old pattern was
        O(N×3) per request (a separate index scan per Chat per subquery);
        the CTE approach is O(1) scans regardless of result-set size.

        CTE layout:
        - msg_stats: unread count + MAX(created_at) per chat_id in one pass.
        - last_msg:  DISTINCT ON to get the latest message ID per chat.
        Both are LEFT-JOINed so chats with no messages still appear.
        """
        with _tracer.start_as_current_span(
            "chat_repository.get_chats_for_user",
            attributes={"user.id": str(user_id), "chat.limit": limit},
        ):
            return await self._get_chats_for_user_impl(user_id, cursor, limit)

    async def _get_chats_for_user_impl(
        self,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[tuple[ChatDTO, int, str | None]], bool, str | None]:
        # CTE-1: aggregate message stats per chat in a single table scan.
        msg_stats_cte = (
            select(
                Message.chat_id.label("chat_id"),
                func.count()
                .filter(
                    Message.read_status == False,  # noqa: E712
                    Message.sender_id != user_id,
                )
                .label("unread_count"),
                func.max(Message.created_at).label("last_message_at"),
            )
            .select_from(Message)
            .group_by(Message.chat_id)
            .cte("msg_stats")
        )

        # CTE-2: latest message ID per chat via PostgreSQL DISTINCT ON.
        # ORDER BY (chat_id, created_at DESC, id DESC) keeps the tie-break
        # deterministic when two messages share the same timestamp.
        last_msg_cte = (
            select(
                Message.chat_id.label("chat_id"),
                Message.id.label("last_message_id"),
            )
            .distinct(Message.chat_id)
            .order_by(
                Message.chat_id,
                Message.created_at.desc(),
                Message.id.desc(),
            )
            .cte("last_msg")
        )

        query = (
            select(
                Chat,
                func.coalesce(msg_stats_cte.c.unread_count, 0).label("unread_count"),
                last_msg_cte.c.last_message_id.label("last_message_id"),
            )
            .join(chat_participants, Chat.id == chat_participants.c.chat_id)
            .outerjoin(msg_stats_cte, Chat.id == msg_stats_cte.c.chat_id)
            .outerjoin(last_msg_cte, Chat.id == last_msg_cte.c.chat_id)
            .where(chat_participants.c.user_id == user_id)
            .options(selectinload(Chat.participants))
        )

        cursor_info = decode_datetime_cursor(cursor)
        if cursor_info:
            cursor_dt, cursor_id = cursor_info
            query = query.where(
                or_(
                    Chat.updated_at < cursor_dt,
                    and_(Chat.updated_at == cursor_dt, Chat.id < cursor_id),
                )
            )

        query = query.order_by(
            msg_stats_cte.c.last_message_at.desc().nulls_last()
        ).limit(limit + 1)
        result = await self.db.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        chat_items = [tuple(row) for row in rows[:limit]]

        next_cursor = None
        if has_more and chat_items:
            last_chat = chat_items[-1][0]
            next_cursor = encode_datetime_cursor(last_chat.updated_at, last_chat.id)

        trace.get_current_span().set_attribute("chat.result_count", len(chat_items))
        return (
            [
                (self._to_dto(row[0]), row[1], str(row[2]) if row[2] else None)
                for row in chat_items
            ],
            has_more,
            next_cursor,
        )

    async def get_last_messages(
        self, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MessageDTO]:
        if not message_ids:
            return {}
        result = await self.db.execute(
            select(Message)
            .where(Message.id.in_(message_ids))
            .options(selectinload(Message.sender), selectinload(Message.attachments))
        )
        return {
            msg.id: MessageDTO.model_validate(msg) for msg in result.scalars().all()
        }

    async def find_existing_dm(
        self, user1_id: uuid.UUID, user2_id: uuid.UUID
    ) -> ChatDTO | None:
        """
        Find an existing Direct Message (DM) chat between two users.
        """
        cp = chat_participants
        existing_chat_stmt = (
            select(Chat)
            .where(Chat.id.in_(select(cp.c.chat_id).where(cp.c.user_id == user1_id)))
            .where(Chat.id.in_(select(cp.c.chat_id).where(cp.c.user_id == user2_id)))
            .where(
                select(func.count())
                .where(cp.c.chat_id == Chat.id)
                .correlate(Chat)
                .scalar_subquery()
                == 2
            )
            .options(selectinload(Chat.participants))
        )
        result = await self.db.execute(existing_chat_stmt)
        row = result.scalar_one_or_none()
        return self._to_dto(row) if row else None

    async def create_chat(self, participants: list[User]) -> ChatDTO:
        """
        Create a new chat with the given participants.
        """
        new_chat = Chat()
        for p in participants:
            new_chat.participants.append(p)
        self.db.add(new_chat)
        await self.db.flush()
        return self._to_dto(new_chat)

    async def get_unread_count(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """
        Count unread messages for a user in a chat.
        """
        # MOD-02 (audit Wave 11): set RLS user so the PostgreSQL
        # messages_participant_isolation policy applies.
        await self._set_rls_user(user_id)

        query = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.chat_id == chat_id,
                Message.read_status == False,  # noqa: E712
                Message.sender_id != user_id,
            )
        )
        return (await self.db.execute(query)).scalar_one()

    async def get_last_message(self, chat_id: uuid.UUID) -> MessageDTO | None:
        """
        Get the most recent message in a chat.

        Args:
            chat_id: The UUID of the chat.

        Returns:
            The latest Message object or None.
        """
        query = (
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc())
            .limit(1)
            .options(selectinload(Message.sender), selectinload(Message.attachments))
        )
        row = (await self.db.execute(query)).scalar_one_or_none()
        return MessageDTO.model_validate(row) if row else None

    async def get_messages(
        self,
        chat_id: uuid.UUID,
        cursor: str | None,
        limit: int,
        *,
        user_id: uuid.UUID | None = None,
    ) -> tuple[list[MessageDTO], bool, str | None]:
        """
        Fetch messages for a specific chat with pagination.

        MOD-02 (audit Wave 11): if ``user_id`` is provided, set the PostgreSQL
        RLS GUC so the ``messages_participant_isolation`` policy filters rows
        to only those in chats the user participates in.  This is a defense-
        in-depth layer on top of the existing SpiceDB authorization check.
        """
        if user_id is not None:
            await self._set_rls_user(user_id)

        query = (
            select(Message)
            .where(Message.chat_id == chat_id)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                # Wave 206 — one extra SELECT … WHERE message_id IN (…) per page;
                # the query service aggregates these into ReactionAggregate.
                selectinload(Message.reactions),
            )
        )

        cursor_info = decode_datetime_cursor(cursor)
        if cursor_info:
            cursor_dt, cursor_id = cursor_info
            query = query.where(
                or_(
                    Message.created_at < cursor_dt,
                    and_(Message.created_at == cursor_dt, Message.id < cursor_id),
                )
            )

        query = query.order_by(Message.created_at.desc()).limit(limit + 1)
        result = await self.db.execute(query)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            # oldest message is the last one in the desc list
            oldest_message = rows[-1]
            next_cursor = encode_datetime_cursor(
                oldest_message.created_at, str(oldest_message.id)
            )

        return [MessageDTO.model_validate(m) for m in rows], has_more, next_cursor

    async def create_message(self, message: Message) -> MessageDTO:
        """
        Persist a new message to the database.
        """
        self.db.add(message)
        await self.db.flush()
        return MessageDTO.model_validate(message)

    async def mark_messages_read(
        self, chat_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[datetime, int]:
        """Mark all unread messages in a chat as read for a user.

        Wave 203 SW4 — also stamps ``read_at`` and returns
        ``(read_at, affected_count)`` so the caller can broadcast a chat-level
        read receipt (only when ``affected_count > 0``) without a re-SELECT.
        ``read_at`` is generated in Python (``utc_now``) rather than SQL
        ``func.now()`` so the exact stored value is available to the broadcast
        frame. The ``read_status.is_(False)`` filter means only newly-read
        messages are stamped — an already-read message keeps its original
        ``read_at``.
        """
        read_at = utc_now()
        stmt = (
            update(Message)
            .where(
                and_(
                    Message.chat_id == chat_id,
                    Message.sender_id != user_id,
                    Message.read_status.is_(False),
                )
            )
            .values(read_status=True, read_at=read_at)
        )
        result = await self.db.execute(stmt)
        affected = int(getattr(result, "rowcount", 0) or 0)
        if affected < 0:
            affected = 0
        return read_at, affected

    async def edit_message(
        self, message_id: uuid.UUID, author_id: uuid.UUID, new_content: str
    ) -> tuple[datetime | None, int]:
        """Edit a message's content (author-only).

        Wave 205 SW3 — mirrors mark_messages_read: stamps ``edited_at`` in Python
        (``utc_now`` so the exact value is available to the broadcast frame) and
        returns ``(edited_at, affected)``. The WHERE clause is the author-only guard
        — ``sender_id == author_id AND deleted_at IS NULL`` — so a non-author or an
        already-deleted message yields ``affected == 0`` (the caller raises 404, no
        existence leak). ``edited_at`` is None when nothing matched.
        """
        edited_at = utc_now()
        stmt = (
            update(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.sender_id == author_id,
                    Message.deleted_at.is_(None),
                )
            )
            .values(content=new_content, edited_at=edited_at)
        )
        result = await self.db.execute(stmt)
        affected = int(getattr(result, "rowcount", 0) or 0)
        if affected < 0:
            affected = 0
        return (edited_at if affected > 0 else None), affected

    async def soft_delete_message(
        self, message_id: uuid.UUID, author_id: uuid.UUID
    ) -> tuple[datetime | None, int]:
        """Soft-delete a message (author-only).

        Wave 205 SW3 (D1) — sets ``deleted_at`` AND clears ``content`` (the deleted
        text must not linger in the DB or leak through any response path); the row
        persists as a tombstone the frontend renders as "Message deleted". Author-only
        WHERE (``sender_id == author_id AND deleted_at IS NULL``) makes a repeat-delete
        or a non-author a no-op (``affected == 0`` → caller raises 404). Returns
        ``(deleted_at, affected)``.
        """
        deleted_at = utc_now()
        stmt = (
            update(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.sender_id == author_id,
                    Message.deleted_at.is_(None),
                )
            )
            .values(deleted_at=deleted_at, content="")
        )
        result = await self.db.execute(stmt)
        affected = int(getattr(result, "rowcount", 0) or 0)
        if affected < 0:
            affected = 0
        return (deleted_at if affected > 0 else None), affected

    async def message_exists_in_chat(
        self, message_id: uuid.UUID, chat_id: uuid.UUID
    ) -> bool:
        """Whether a message with this id belongs to this chat (Wave 206).

        The reaction service calls this to return a clean 404 before an INSERT.
        Unlike edit/delete (author-only WHERE → affected == 0 surfaces a missing
        message), reactions are not author-gated, so a bogus message_id would
        otherwise FK-fail the INSERT mid-transaction — hence an explicit check.
        """
        stmt = select(
            exists().where(and_(Message.id == message_id, Message.chat_id == chat_id))
        )
        return bool((await self.db.execute(stmt)).scalar())

    async def add_reaction(
        self, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
    ) -> bool:
        """Add a reaction idempotently. Returns True iff a NEW row was inserted.

        Wave 206 — pg_insert(...).on_conflict_do_nothing targets the
        (user_id, message_id, emoji) unique constraint, so a repeat reaction is a
        no-op (returns False → the caller skips the broadcast). The id +
        created_at column defaults (generate_uuid7 / utc_now) are applied by the
        Core insert for the omitted columns.
        """
        stmt = (
            pg_insert(MessageReaction)
            .values(message_id=message_id, user_id=user_id, emoji=emoji)
            .on_conflict_do_nothing(index_elements=["user_id", "message_id", "emoji"])
        )
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0) > 0

    async def remove_reaction(
        self, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
    ) -> int:
        """Remove a reaction. Returns affected rowcount (0 = nothing to remove).

        Wave 206 — idempotent: removing a non-existent reaction is a benign no-op
        (the caller skips the broadcast when affected == 0).
        """
        stmt = delete(MessageReaction).where(
            and_(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji,
            )
        )
        result = await self.db.execute(stmt)
        affected = int(getattr(result, "rowcount", 0) or 0)
        return affected if affected > 0 else 0

    async def delete_messages(self, message_ids: list[uuid.UUID]) -> int:
        """
        Delete multiple messages by their IDs.
        """
        if not message_ids:
            return 0
        stmt = delete(Message).where(Message.id.in_(message_ids))
        result = await self.db.execute(stmt)
        # LOW-W19: use actual rowcount from the driver rather than input length —
        # some rows may have been deleted by a concurrent request.
        rc = getattr(result, "rowcount", 0) or 0
        if rc < 0:
            rc = 0
        return int(rc)

    async def delete_chat(self, chat_id: uuid.UUID) -> None:
        """
        Delete a chat by its ID.
        """
        stmt = delete(Chat).where(Chat.id == chat_id)
        await self.db.execute(stmt)

    async def update_timestamp_by_id(
        self, chat_id: uuid.UUID, timestamp: datetime
    ) -> None:
        """
        Update the `updated_at` timestamp of a chat by its ID.
        """
        stmt = update(Chat).where(Chat.id == chat_id).values(updated_at=timestamp)
        await self.db.execute(stmt)

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        """Fetch a User by primary key — used by ChatService to resolve participants."""
        return await self.db.get(User, user_id)

    async def check_participant(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Return True iff user_id is a participant of chat_id.

        TD-NEW-05 (audit 2026-03): Uses SELECT EXISTS instead of SELECT col +
        Python null-check so the database short-circuits on the first matching
        row and returns a single boolean without materialising any data.
        """
        with _tracer.start_as_current_span(
            "chat_repository.check_participant",
            attributes={"chat.id": str(chat_id), "user.id": str(user_id)},
        ):
            stmt = select(
                exists().where(
                    chat_participants.c.chat_id == chat_id,
                    chat_participants.c.user_id == user_id,
                )
            )
            result = await self.db.execute(stmt)
            return bool(result.scalar())

    async def get_participants(self, chat_id: uuid.UUID) -> list[uuid.UUID]:
        """Fetch all participant IDs for a chat."""
        stmt = select(chat_participants.c.user_id).where(
            chat_participants.c.chat_id == chat_id
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_message_by_id(self, message_id: uuid.UUID) -> MessageDTO | None:
        """Fetch a specific message by its ID, converted to DTO."""
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.sender), selectinload(Message.attachments))
        )
        result = await self.db.execute(stmt)
        msg = result.scalars().first()
        return MessageDTO.model_validate(msg) if msg else None

    async def mark_single_message_read(self, message_id: uuid.UUID) -> bool:
        """Mark a single message as read. Returns True if successful."""
        stmt = update(Message).where(Message.id == message_id).values(read_status=True)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return (int(getattr(result, "rowcount", 0) or 0)) > 0

    # P2-fix (audit 2026-02-26): Without a LIMIT the presence audience query is
    # O(chats × participants) and can load tens-of-thousands of UUIDs into memory
    # for heavily-connected users (e.g. admins in many group chats).
    # 500 recipients is generous for real-time presence while preventing exhaustion.
    _PRESENCE_AUDIENCE_LIMIT: int = 500

    async def get_presence_audience(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Resolve user IDs that should receive presence updates for user_id.

        Capped at ``_PRESENCE_AUDIENCE_LIMIT`` to prevent memory exhaustion for
        heavily-connected users. The cache in ``websocket._get_presence_audience``
        shields subsequent calls.
        """
        with _tracer.start_as_current_span(
            "chat_repository.get_presence_audience",
            attributes={
                "user.id": str(user_id),
                "presence.limit": self._PRESENCE_AUDIENCE_LIMIT,
            },
        ) as span:
            chat_ids_subquery = select(chat_participants.c.chat_id).where(
                chat_participants.c.user_id == user_id
            )
            stmt = (
                select(chat_participants.c.user_id)
                .distinct()
                .where(chat_participants.c.chat_id.in_(chat_ids_subquery))
                .limit(self._PRESENCE_AUDIENCE_LIMIT)
            )
            result = await self.db.execute(stmt)
            audience = {row[0] for row in result.all()}
            audience.discard(user_id)
            span.set_attribute("presence.audience_size", len(audience))
            return audience


def get_chat_repository(db: AsyncDatabaseSession) -> ChatRepository:
    return ChatRepository(db)
