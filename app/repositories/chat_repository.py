from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from opentelemetry import trace
from sqlalchemy import (
    and_,
    case,
    delete,
    exists,
    func,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.core.protocols import AsyncDatabaseSession
from app.models import User
from app.models.chat import (
    Chat,
    ChatReadReceipt,
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
            text("SELECT set_config('app.current_user_id', :uid, true)"),
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

        # CTE-3 (Wave 210 G2): per-recipient unread for GROUP chats only. A
        # message counts as unread when it is from another sender AND either the
        # user has no read receipt yet OR the message post-dates their
        # high-water-mark (ChatReadReceipt.last_read_at). DM unread stays in
        # msg_stats_cte (Message.read_status) — Option A, byte-identical DM path.
        # The inner join to Chat (chat_type='group') scans only group messages, so
        # DM rows never reach this CTE. msg_stats_cte is deliberately NOT filtered
        # to DMs: its last_message_at column still orders ALL chats (groups
        # included) below — only the *count* is branched, never the ordering.
        group_unread_cte = (
            select(
                Message.chat_id.label("chat_id"),
                func.count().label("group_unread_count"),
            )
            .select_from(Message)
            .join(
                Chat,
                and_(Chat.id == Message.chat_id, Chat.chat_type == "group"),
            )
            .outerjoin(
                ChatReadReceipt,
                and_(
                    ChatReadReceipt.chat_id == Message.chat_id,
                    ChatReadReceipt.user_id == user_id,
                ),
            )
            .where(
                Message.sender_id != user_id,
                or_(
                    ChatReadReceipt.last_read_at.is_(None),
                    Message.created_at > ChatReadReceipt.last_read_at,
                ),
            )
            .group_by(Message.chat_id)
            .cte("group_unread")
        )

        query = (
            select(
                Chat,
                # Wave 210 G2: groups read their unread from the per-recipient
                # high-water-mark CTE; DMs keep the read_status-based msg_stats
                # count (byte-identical). The CASE picks the branch per row.
                case(
                    (
                        Chat.chat_type == "group",
                        func.coalesce(group_unread_cte.c.group_unread_count, 0),
                    ),
                    else_=func.coalesce(msg_stats_cte.c.unread_count, 0),
                ).label("unread_count"),
                last_msg_cte.c.last_message_id.label("last_message_id"),
            )
            .join(chat_participants, Chat.id == chat_participants.c.chat_id)
            .outerjoin(msg_stats_cte, Chat.id == msg_stats_cte.c.chat_id)
            .outerjoin(group_unread_cte, Chat.id == group_unread_cte.c.chat_id)
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
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                # Wave 207 — replied_to + its sender so the send response can build
                # the reply preview (chat-list last-message keeps it lightweight).
                selectinload(Message.replied_to).selectinload(Message.sender),
            )
        )
        return {
            msg.id: MessageDTO.model_validate(msg) for msg in result.scalars().all()
        }

    async def get_user_display_names(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str | None]:
        """Batch-resolve users' display names for the "Forwarded from X" label (W211).

        full_name lives on UserProfile (a lazy="noload" relationship), so a bare
        select(Message).selectinload(Message.sender) leaves MessageDTO.sender with
        full_name=None — ChatParticipantDTO maps from User, which has no full_name
        (the W207 SW5 gotcha). Forwarding needs the ORIGINAL sender's name, so
        resolve it the same way ChatQueryService does: load User.profile
        explicitly. Batched by id — a forward of N messages from K distinct senders
        costs ONE SELECT, not an N+1. Returns {user_id: profile.full_name or None};
        ids with no row / no profile yield None (the FE then shows a generic
        "Forwarded" chip without a name).
        """
        if not user_ids:
            return {}
        stmt = (
            select(User)
            .where(User.id.in_(user_ids))
            .options(selectinload(User.profile))
        )
        result = await self.db.execute(stmt)
        return {
            u.id: (u.profile.full_name if u.profile else None)
            for u in result.scalars().all()
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

    async def create_group(
        self, creator: User, name: str, member_users: list[User]
    ) -> ChatDTO:
        """Create a named group chat owned by ``creator`` (Wave 209 G1).

        chat_type="group" + created_by=creator.id set group identity; the creator
        is always a participant. Members are de-duplicated by id (the creator is
        never double-added even if also passed in member_users). Mirrors
        create_chat's Chat()/append/flush/_to_dto shape — no Redis lock, since a
        group has no DM-style find-or-create uniqueness invariant.
        """
        new_chat = Chat(chat_type="group", name=name, created_by=creator.id)
        seen: set[uuid.UUID] = set()
        for participant in (creator, *member_users):
            if participant.id in seen:
                continue
            seen.add(participant.id)
            new_chat.participants.append(participant)
        self.db.add(new_chat)
        await self.db.flush()
        return self._to_dto(new_chat)

    async def add_participant(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Add a user to a chat idempotently. Returns True iff a NEW row inserted.

        Wave 209 G1 — SELECT-then-INSERT (the existing check_participant + a plain
        Core insert), NOT pg_insert.on_conflict_do_nothing like add_reaction:
        dialect-agnostic, so the full add-participant path is real-DB-testable on
        the SQLite test DB as well as PostgreSQL. The composite (chat_id, user_id)
        PK still guarantees uniqueness; the pre-check makes a repeat add a clean
        no-op (returns False → the caller skips the broadcast) and avoids the
        IntegrityError-driven transaction abort a bare insert would cause. The
        TOCTOU window (two concurrent adds of the SAME user) is benign for this
        rare admin action and PK-backstopped.
        """
        if await self.check_participant(chat_id, user_id):
            return False
        await self.db.execute(
            insert(chat_participants).values(chat_id=chat_id, user_id=user_id)
        )
        return True

    async def remove_participant(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Remove a user from a chat. Returns affected rowcount (0 = not a member).

        Wave 209 G1 — idempotent: removing a non-member is a benign no-op (the
        caller skips the broadcast when affected == 0). Mirrors remove_reaction.
        """
        stmt = delete(chat_participants).where(
            and_(
                chat_participants.c.chat_id == chat_id,
                chat_participants.c.user_id == user_id,
            )
        )
        result = await self.db.execute(stmt)
        affected = int(getattr(result, "rowcount", 0) or 0)
        return affected if affected > 0 else 0

    async def rename_chat(self, chat_id: uuid.UUID, name: str) -> int:
        """Rename a chat (group display title). Returns affected rowcount.

        Wave 209 G1 — Core update; Chat.updated_at's onupdate=utc_now is applied
        automatically so a renamed chat re-sorts to the top of the list.
        """
        stmt = update(Chat).where(Chat.id == chat_id).values(name=name)
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def get_unread_count(
        self, chat_id: uuid.UUID, user_id: uuid.UUID, chat_type: str = "dm"
    ) -> int:
        """
        Count unread messages for a user in a chat.

        Wave 210 G2 — DMs use Message.read_status (unchanged, Option A). GROUP
        chats use the per-recipient ChatReadReceipt high-water-mark: a message is
        unread when sender_id != user AND (no receipt OR created_at >
        last_read_at). chat_type is passed by the sole caller (get_chat_details,
        which already holds chat.chat_type) — no internal Chat re-query.
        """
        # MOD-02 (audit Wave 11): set RLS user so the PostgreSQL
        # messages_participant_isolation policy applies. SET LOCAL is PG-only; the
        # SQLite test DB rejects it, so the group branch is exercised at the repo
        # level via get_chats_for_user (which has no _set_rls_user), not here.
        await self._set_rls_user(user_id)

        if chat_type == "group":
            group_query = (
                select(func.count())
                .select_from(Message)
                .outerjoin(
                    ChatReadReceipt,
                    and_(
                        ChatReadReceipt.chat_id == Message.chat_id,
                        ChatReadReceipt.user_id == user_id,
                    ),
                )
                .where(
                    Message.chat_id == chat_id,
                    Message.sender_id != user_id,
                    or_(
                        ChatReadReceipt.last_read_at.is_(None),
                        Message.created_at > ChatReadReceipt.last_read_at,
                    ),
                )
            )
            return (await self.db.execute(group_query)).scalar_one()

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
                # Wave 207 — load the replied-to message + its sender for the quote
                # preview (one extra SELECT … WHERE id IN (…) per page). The nested
                # replied_to.replied_to stays noload → no deep nesting.
                selectinload(Message.replied_to).selectinload(Message.sender),
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
        self, chat_id: uuid.UUID, user_id: uuid.UUID, chat_type: str = "dm"
    ) -> tuple[datetime, int]:
        """Mark a chat read for a user; return ``(read_at, affected)``.

        Wave 203 SW4 — stamps ``read_at`` (Python ``utc_now`` so the exact stored
        value is available to the broadcast frame) and returns
        ``(read_at, affected_count)`` so the caller broadcasts a chat-level read
        receipt only when ``affected_count > 0`` (no re-SELECT, no churn).

        Wave 210 G2 — the DM path is BYTE-IDENTICAL to W203 (bulk update of
        Message.read_status/read_at). The GROUP path uses the per-recipient
        ChatReadReceipt high-water-mark: (a) count messages from OTHER senders not
        yet covered by the mark BEFORE upserting, so the broadcast gate keeps DM
        semantics (only broadcast when something new became read); (b) upsert the
        receipt to ``read_at`` via the dialect-agnostic SELECT-then-(UPDATE|INSERT)
        pattern (the add_participant precedent — NOT pg_insert.on_conflict, which
        is PG-only and would not compile on the SQLite test DB); (c) return
        ``(read_at, affected)``. The WS frame shape is UNCHANGED
        (``{type:"read", chat_id, user_id, read_at}``).
        """
        read_at = utc_now()

        if chat_type == "group":
            old_last_read_at = (
                await self.db.execute(
                    select(ChatReadReceipt.last_read_at).where(
                        and_(
                            ChatReadReceipt.chat_id == chat_id,
                            ChatReadReceipt.user_id == user_id,
                        )
                    )
                )
            ).scalar_one_or_none()

            # (a) affected = other-sender messages not yet covered by the mark.
            count_query = (
                select(func.count())
                .select_from(Message)
                .where(
                    Message.chat_id == chat_id,
                    Message.sender_id != user_id,
                )
            )
            if old_last_read_at is not None:
                count_query = count_query.where(Message.created_at > old_last_read_at)
            affected = (await self.db.execute(count_query)).scalar_one()

            # (b) upsert the high-water-mark (check-then-INSERT|UPDATE, SQLite-safe).
            if old_last_read_at is None:
                await self.db.execute(
                    insert(ChatReadReceipt).values(
                        chat_id=chat_id, user_id=user_id, last_read_at=read_at
                    )
                )
            else:
                await self.db.execute(
                    update(ChatReadReceipt)
                    .where(
                        and_(
                            ChatReadReceipt.chat_id == chat_id,
                            ChatReadReceipt.user_id == user_id,
                        )
                    )
                    .values(last_read_at=read_at)
                )
            return read_at, int(affected)

        # DM path — byte-identical to Wave 203.
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

    async def get_reactors(self, message_id: uuid.UUID, emoji: str) -> list[User]:
        """Fetch the users who reacted to a message with a specific emoji (Wave 207).

        Powers the reactor-list "who reacted" popover. A direct JOIN of users →
        message_reactions on the FK columns (no MessageReaction.user relationship
        needed) returns the User rows in one query, oldest-reaction-first.
        selectinload(User.profile) eagerly loads the profile (full_name + avatar_url
        live on UserProfile, a lazy="noload" relationship — without this they'd be
        None) so the service reads them in one extra SELECT, never an N+1. The
        (user_id, message_id, emoji) unique constraint guarantees one reaction row
        per user for this emoji, so the result is naturally distinct.
        """
        stmt = (
            select(User)
            .join(MessageReaction, MessageReaction.user_id == User.id)
            .where(
                and_(
                    MessageReaction.message_id == message_id,
                    MessageReaction.emoji == emoji,
                )
            )
            .options(selectinload(User.profile))
            .order_by(MessageReaction.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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

    async def get_users_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        """Fetch multiple User entities by primary keys in a single query."""
        if not user_ids:
            return []
        stmt = select(User).where(User.id.in_(user_ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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

    async def get_read_receipts(
        self, chat_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, datetime]]:
        """Wave 210 G2 — all (user_id, last_read_at) read receipts for a chat.

        Powers ChatResponse.read_receipts (the per-member "seen by" map the FE
        folds together with live `read` frames). Group-only in practice — a DM
        has no receipt rows, so this returns [] (DMs keep using read_status).
        """
        stmt = select(ChatReadReceipt.user_id, ChatReadReceipt.last_read_at).where(
            ChatReadReceipt.chat_id == chat_id
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_chat_type(self, chat_id: uuid.UUID) -> str | None:
        """Wave 210 G2 — single-column chat_type lookup for the WS read handler.

        The dispatcher does not load the chat (only check_participant), so this
        cheap PK lookup lets mark_messages_read branch DM vs group without the
        heavier get_by_id selectinload.
        """
        return (
            await self.db.execute(select(Chat.chat_type).where(Chat.id == chat_id))
        ).scalar_one_or_none()

    async def get_message_by_id(self, message_id: uuid.UUID) -> MessageDTO | None:
        """Fetch a specific message by its ID, converted to DTO."""
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                # Wave 207 — replied_to for the idempotent-resend reply preview.
                selectinload(Message.replied_to).selectinload(Message.sender),
            )
        )
        result = await self.db.execute(stmt)
        msg = result.scalars().first()
        return MessageDTO.model_validate(msg) if msg else None

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
