from datetime import datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import Chat, Message, chat_participants
from app.models.models import User
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, chat_id: str, load_messages: bool = False) -> Chat | None:
        """
        Fetch a chat by its ID.

        Args:
            chat_id: The UUID of the chat.
            load_messages: If True, eager load messages and their attachments.

        Returns:
            The Chat object if found, otherwise None.
        """
        load_options = [selectinload(Chat.participants)]
        if load_messages:
            load_options.append(
                selectinload(Chat.messages).selectinload(Message.attachments)
            )
        return await self.session.get(Chat, chat_id, options=load_options)

    async def get_chats_for_user(
        self, user_id: int, cursor: str | None, limit: int
    ) -> tuple[list[tuple[Chat, int, str | None]], bool, str | None]:
        """
        Fetch chats for a user with pagination and metadata.

        Args:
            user_id: The ID of the user.
            cursor: Pagination cursor string.
            limit: Maximum number of chats to return.

        Returns:
            A tuple containing:
            - List of tuples (Chat, unread_count, last_message_id)
            - Boolean indicating if there are more chats
            - Next cursor string or None
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
        result = await self.session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            last_chat = rows[-1][0]
            next_cursor = encode_datetime_cursor(last_chat.updated_at, last_chat.id)

        return rows, has_more, next_cursor

    async def get_last_messages(self, message_ids: list[str]) -> dict[str, Message]:
        if not message_ids:
            return {}
        result = await self.session.execute(
            select(Message)
            .where(Message.id.in_(message_ids))
            .options(selectinload(Message.sender), selectinload(Message.attachments))
        )
        return {msg.id: msg for msg in result.scalars().all()}

    async def find_existing_dm(self, user1_id: int, user2_id: int) -> Chat | None:
        """
        Find an existing Direct Message (DM) chat between two users.

        Args:
            user1_id: ID of the first participant.
            user2_id: ID of the second participant.

        Returns:
            The existing Chat object if found, otherwise None.
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
        result = await self.session.execute(existing_chat_stmt)
        return result.scalar_one_or_none()

    async def create_chat(self, participants: list[User]) -> Chat:
        """
        Create a new chat with the given participants.

        Args:
            participants: List of User objects to include in the chat.

        Returns:
            The newly created Chat object.
        """
        new_chat = Chat()
        for p in participants:
            new_chat.participants.append(p)
        self.session.add(new_chat)
        await self.session.flush()
        return new_chat

    async def get_unread_count(self, chat_id: str, user_id: int) -> int:
        """
        Count unread messages for a user in a chat.

        Args:
            chat_id: The UUID of the chat.
            user_id: The ID of the user.

        Returns:
            The number of unread messages.
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
        return (await self.session.execute(query)).scalar_one()

    async def get_last_message(self, chat_id: str) -> Message | None:
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
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_messages(
        self, chat_id: str, cursor: str | None, limit: int
    ) -> tuple[list[Message], bool, str | None]:
        """
        Fetch messages for a specific chat with pagination.

        Args:
            chat_id: The UUID of the chat.
            cursor: Pagination cursor string.
            limit: Maximum number of messages to return.

        Returns:
            A tuple containing:
            - List of Message objects
            - Boolean indicating if there are more messages
            - Next cursor string or None
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
        result = await self.session.execute(query)
        messages = list(result.scalars().all())

        has_more = len(messages) > limit
        messages = messages[:limit]

        next_cursor = None
        if has_more and messages:
            # oldest message is the last one in the desc list
            oldest_message = messages[-1]
            next_cursor = encode_datetime_cursor(
                oldest_message.created_at, oldest_message.id
            )

        return messages, has_more, next_cursor

    async def create_message(self, message: Message) -> Message:
        """
        Persist a new message to the database.

        Args:
            message: The Message object to save.

        Returns:
            The saved Message object.
        """
        self.session.add(message)
        await self.session.flush()
        return message

    async def mark_messages_read(self, chat_id: str, user_id: int) -> None:
        """
        Mark all unread messages in a chat as read for a user.

        Args:
            chat_id: The UUID of the chat.
            user_id: The ID of the user (reader).
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
        await self.session.execute(stmt)

    async def delete_messages(self, messages: list[Message]) -> int:
        """
        Delete a list of messages.

        Args:
            messages: List of Message objects to delete.

        Returns:
            The number of messages deleted.
        """
        count = len(messages)
        for message in messages:
            await self.session.delete(message)
        return count

    async def delete_chat(self, chat: Chat) -> None:
        """
        Delete a chat and all associated data.

        Args:
            chat: The Chat object to delete.
        """
        await self.session.delete(chat)

    async def update_timestamp(self, chat: Chat, timestamp: datetime) -> None:
        """
        Update the `updated_at` timestamp of a chat.

        Args:
            chat: The Chat object to update.
            timestamp: The new timestamp.
        """
        chat.updated_at = timestamp
        self.session.add(chat)
