import uuid
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.models.chat import Chat, Message, chat_participants
from app.models.models import User
from app.repositories.base import BaseRepository
from app.schemas.dtos.chat import ChatDTO, MessageDTO
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor


class ChatRepository(BaseRepository[Chat, ChatDTO, dict, dict]):
    @property
    def model(self) -> type[Chat]:
        return Chat

    @property
    def dto_class(self) -> type[ChatDTO]:
        return ChatDTO

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
        """
        # Subquery: last message timestamp per chat (for ordering)
        last_message_subquery = (
            select(Message.created_at)
            .where(Message.chat_id == Chat.id)
            .order_by(Message.created_at.desc())
            .limit(1)
            .correlate(Chat)
            .scalar_subquery()
        )

        # Subquery: unread count per chat
        unread_count_subquery = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.chat_id == Chat.id,
                Message.read_status == False,  # noqa: E712
                Message.sender_id != user_id,
            )
            .correlate(Chat)
            .scalar_subquery()
        )

        # Subquery: last message ID per chat
        last_message_id_subquery = (
            select(Message.id)
            .where(Message.chat_id == Chat.id)
            .order_by(Message.created_at.desc())
            .limit(1)
            .correlate(Chat)
            .scalar_subquery()
        )

        query = (
            select(
                Chat,
                unread_count_subquery.label("unread_count"),
                last_message_id_subquery.label("last_message_id"),
            )
            .join(Chat.participants)
            .where(User.id == user_id)
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

        query = query.order_by(last_message_subquery.desc().nulls_last()).limit(
            limit + 1
        )
        result = await self.db.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        chat_items = [tuple(row) for row in rows[:limit]]

        next_cursor = None
        if has_more and chat_items:
            last_chat = chat_items[-1][0]
            next_cursor = encode_datetime_cursor(last_chat.updated_at, last_chat.id)

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
        self, chat_id: uuid.UUID, cursor: str | None, limit: int
    ) -> tuple[list[MessageDTO], bool, str | None]:
        """
        Fetch messages for a specific chat with pagination.
        """
        query = (
            select(Message)
            .where(Message.chat_id == chat_id)
            .options(selectinload(Message.sender), selectinload(Message.attachments))
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
                oldest_message.created_at, oldest_message.id
            )

        return [MessageDTO.model_validate(m) for m in rows], has_more, next_cursor

    async def create_message(self, message: Message) -> MessageDTO:
        """
        Persist a new message to the database.
        """
        self.db.add(message)
        await self.db.flush()
        return MessageDTO.model_validate(message)

    async def mark_messages_read(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """
        Mark all unread messages in a chat as read for a user.
        """
        stmt = (
            update(Message)
            .where(
                and_(
                    Message.chat_id == chat_id,
                    Message.sender_id != user_id,
                    Message.read_status.is_(False),
                )
            )
            .values(read_status=True)
        )
        await self.db.execute(stmt)

    async def delete_messages(self, message_ids: list[uuid.UUID]) -> int:
        """
        Delete multiple messages by their IDs.
        """
        if not message_ids:
            return 0
        count = len(message_ids)
        stmt = delete(Message).where(Message.id.in_(message_ids))
        await self.db.execute(stmt)
        return count

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

    # ------------------------------------------------------------------ #
    # Transaction proxies — callers should never access session directly.  #
    # ------------------------------------------------------------------ #

    async def commit(self) -> None:
        """Commit the current unit of work."""
        await self.db.commit()

    async def rollback(self) -> None:
        """Roll back the current unit of work."""
        await self.db.rollback()

    async def refresh(self, obj: object) -> None:
        """Refresh *obj* from the database."""
        await self.db.refresh(obj)

    def add(self, obj: object) -> None:
        """Stage *obj* for insertion/update."""
        self.db.add(obj)

    async def delete_obj(self, obj: object) -> None:
        """Delete *obj* from the database."""
        await self.db.delete(obj)

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        """Fetch a User by primary key — used by ChatService to resolve participants."""
        return await self.db.get(User, user_id)

    async def check_participant(
        self, chat_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Return True iff user_id is a participant of chat_id.

        Uses a direct EXISTS query on the association table — avoids loading
        Chat or User ORM objects and stays O(1) regardless of chat size.
        """
        stmt = select(
            chat_participants.c.user_id
        ).where(
            chat_participants.c.chat_id == chat_id,
            chat_participants.c.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.first() is not None
