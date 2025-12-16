import asyncio
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.websocket import build_presence_map, notify_new_message
from app.services.notifications import create_notifications_for_users
from app.core.config import settings
from app.core.database import get_db
from app.localization import translate
from app.models.chat import Attachment, Chat, Message
from app.models.models import User
from app.schemas.chat import (
    ChatCreate,
    ChatMaintenanceResult,
    ChatResponse,
    ChatsListOut,
    MessageResponse,
    MessagesListOut,
    PresenceStatus,
)
from app.utils.files import delete_static_file, save_attachment

router = APIRouter(prefix="/chats", tags=["chats"])


def _encode_cursor(dt: datetime, id_val: str) -> str:
    """Encode a cursor from datetime and ID."""
    ts = int(dt.timestamp() * 1000)
    return f"{ts}:{id_val}"


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    """Decode a cursor into datetime and ID."""
    if not cursor:
        return None
    try:
        ts_str, id_val = cursor.split(":", 1)
        ts = int(ts_str) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc), id_val
    except (ValueError, TypeError):
        return None


async def _get_chat_for_user(
    session: AsyncSession,
    chat_id: str,
    current_user: User,
    *,
    load_messages: bool = False,
):
    load_options = [selectinload(Chat.participants)]
    if load_messages:
        load_options.append(
            selectinload(Chat.messages).selectinload(Message.attachments)
        )

    chat = await session.get(Chat, chat_id, options=load_options)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Not a participant")
    return chat


@router.get("", response_model=ChatsListOut)
async def get_chats(
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Number of chats to return"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Get all chats for the current user with cursor-based pagination.

    Returns chats ordered by last message timestamp (newest first).
    Use the `next_cursor` from the response to fetch the next page.
    """
    # Subquery to find latest message timestamp for ordering
    last_message_subquery = (
        select(Message.created_at)
        .where(Message.chat_id == Chat.id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )

    query = (
        select(Chat)
        .join(Chat.participants)
        .where(User.id == current_user.id)
        .options(selectinload(Chat.participants), selectinload(Chat.messages))
    )

    # Apply cursor filter if provided
    cursor_info = _decode_cursor(cursor)
    if cursor_info:
        cursor_dt, cursor_id = cursor_info
        # Filter for chats with older last message or same time but
        # lexicographically smaller ID
        query = query.where(
            or_(
                Chat.updated_at < cursor_dt,
                and_(Chat.updated_at == cursor_dt, Chat.id < cursor_id),
            )
        )

    query = query.order_by(last_message_subquery.desc().nulls_last()).limit(limit + 1)
    result = await session.execute(query)
    chats = result.scalars().all()
    participant_ids: set[int] = set()

    for chat in chats:
        for participant in chat.participants:
            participant_ids.add(participant.id)

    # Check if there are more results
    has_more = len(chats) > limit
    chats = chats[:limit]

    # Process chats to add last_message and unread_count
    chat_responses = []
    for chat in chats:
        # Sort messages to find the last one
        sorted_messages = sorted(
            chat.messages, key=lambda m: m.created_at, reverse=True
        )
        last_message = sorted_messages[0] if sorted_messages else None

        unread_count = sum(
            1
            for m in chat.messages
            if not m.read_status and m.sender_id != current_user.id
        )

        chat_responses.append(
            ChatResponse(
                id=chat.id,
                participants=chat.participants,
                last_message=last_message,
                unread_count=unread_count,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )
        )

    # Build next cursor
    next_cursor = None
    if has_more and chat_responses:
        last_chat = chats[-1]
        next_cursor = _encode_cursor(last_chat.updated_at, last_chat.id)

    presence_map = await build_presence_map(participant_ids, session=session)

    enriched_chats = []
    for chat in chat_responses:
        last_message = chat.last_message
        if isinstance(last_message, Message):
            last_message = MessageResponse(
                id=last_message.id,
                chat_id=last_message.chat_id,
                sender_id=last_message.sender_id,
                content=last_message.content,
                created_at=last_message.created_at,
                read_status=last_message.read_status,
                sender=last_message.sender,
                attachments=last_message.attachments,
                sender_presence=presence_map.get(last_message.sender_id),
            )

        participant_status = {}
        for participant in chat.participants:
            participant_status[participant.id] = presence_map.get(
                participant.id, PresenceStatus()
            )
        enriched_chats.append(
            ChatResponse(
                **chat.model_dump(exclude={"last_message", "presence"}),
                last_message=last_message,
                presence=participant_status,
            )
        )

    return ChatsListOut(
        items=enriched_chats,
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.post("", response_model=ChatResponse)
async def create_chat(
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Create a new chat with a user. If a chat already exists, return it.
    """
    if chat_in.participant_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create chat with yourself",
        )

    # Check if participant exists
    participant = await session.get(User, chat_in.participant_id)
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if chat already exists
    # Simpler to fetch user's chats and check in python for now.

    # Find chats where both users are participants
    query = (
        select(Chat)
        .join(Chat.participants)
        .where(User.id == current_user.id)
        .options(selectinload(Chat.participants))
    )
    result = await session.execute(query)
    user_chats = result.scalars().all()

    for chat in user_chats:
        participant_ids = [p.id for p in chat.participants]
        if len(participant_ids) == 2 and chat_in.participant_id in participant_ids:
            # Chat exists
            return ChatResponse(
                id=chat.id,
                participants=chat.participants,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )

    # Create new chat
    new_chat = Chat()
    new_chat.participants.append(current_user)
    new_chat.participants.append(participant)
    session.add(new_chat)
    await session.commit()
    await session.refresh(new_chat)

    presence_map = await build_presence_map(
        [p.id for p in new_chat.participants], session=session
    )

    return ChatResponse(
        id=new_chat.id,
        participants=new_chat.participants,
        created_at=new_chat.created_at,
        updated_at=new_chat.updated_at,
        presence={
            participant.id: presence_map.get(participant.id, PresenceStatus())
            for participant in new_chat.participants
        },
    )


@router.get("/{chat_id}/messages", response_model=MessagesListOut)
async def get_messages(
    chat_id: str,
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=100, description="Number of messages to return"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Get messages for a chat with cursor-based pagination.

    Messages are returned in ascending order (oldest first).
    Use the `next_cursor` from the response to fetch older messages.
    """
    chat = await session.get(Chat, chat_id, options=[selectinload(Chat.participants)])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Not a participant")

    query = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(selectinload(Message.sender), selectinload(Message.attachments))
    )

    # Apply cursor filter if provided
    cursor_info = _decode_cursor(cursor)
    if cursor_info:
        cursor_dt, cursor_id = cursor_info
        # For ascending order, we want older messages (before cursor)
        query = query.where(
            or_(
                Message.created_at < cursor_dt,
                and_(Message.created_at == cursor_dt, Message.id < cursor_id),
            )
        )

    # Fetch one extra to check if there are more
    query = query.order_by(Message.created_at.desc()).limit(limit + 1)
    result = await session.execute(query)
    messages = list(result.scalars().all())

    # Check if there are more results
    has_more = len(messages) > limit
    messages = messages[:limit]

    # Reverse to get ascending order for display
    messages = list(reversed(messages))

    # Build next cursor (for loading older messages)
    next_cursor = None
    if has_more and messages:
        oldest_message = messages[0]  # First in ascending order = oldest
        next_cursor = _encode_cursor(oldest_message.created_at, oldest_message.id)

    presence_map = await build_presence_map(
        {msg.sender_id for msg in messages}, session=session
    )

    response_items = [
        MessageResponse(
            id=msg.id,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
            content=msg.content,
            created_at=msg.created_at,
            read_status=msg.read_status,
            sender=msg.sender,
            attachments=msg.attachments,
            sender_presence=presence_map.get(msg.sender_id),
        )
        for msg in messages
    ]

    return MessagesListOut(
        items=response_items,
        has_more=has_more,
        next_cursor=next_cursor,
    )


async def _cleanup_orphaned_files(urls: list[str]) -> None:
    tasks = [delete_static_file(url) for url in urls if url]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _collect_attachment_urls(chat: Chat) -> list[str]:
    urls: list[str] = []
    for message in chat.messages:
        for attachment in message.attachments:
            if attachment.url:
                urls.append(attachment.url)
    return urls


async def _process_chat_upload(
    upload: UploadFile, chat_id: str, *, locale: str | None
) -> dict[str, object]:
    meta = await save_attachment(
        upload,
        "chat_uploads",
        f"chat_{chat_id}",
        locale=locale,
        allowed_mime_types=settings.chat_attachment_allowed_mime_types_set,
        allowed_extensions=settings.chat_attachment_allowed_extensions_set,
        max_size_bytes=settings.chat_attachment_max_size_bytes,
        return_meta=True,
    )
    if not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store attachment",
        )
    detected_type = str(meta.get("detected_type") or meta.get("content_type") or "")
    file_type = "file"
    if detected_type.startswith("image/"):
        file_type = "image"
    elif detected_type.startswith("video/"):
        file_type = "video"

    return {
        "url": str(meta.get("url") or ""),
        "file_type": file_type,
        "filename": str(meta.get("filename") or upload.filename or "attachment"),
        "size": int(meta.get("size") or 0),
    }


@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Send a message to a chat.

    The message is saved to the database and all chat participants
    are notified via WebSocket in real-time.
    """

    chat = await session.get(Chat, chat_id, options=[selectinload(Chat.participants)])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Not a participant")

    locale = getattr(current_user, "preferred_locale", None)
    uploads = files or []
    if len(uploads) > int(settings.chat_attachment_max_files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("errors.files.too_many_attachments", locale=locale),
        )

    message = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        content=content,
    )
    session.add(message)
    await session.flush()  # Flush to get message ID

    saved_urls: list[str] = []
    try:
        for upload in uploads:
            meta = await _process_chat_upload(upload, chat_id, locale=locale)
            saved_urls.append(meta["url"])
            attachment = Attachment(
                message_id=message.id,
                url=meta["url"],
                file_type=meta["file_type"],
                filename=meta["filename"],
                size=meta["size"],
            )
            session.add(attachment)

        # Update chat updated_at
        chat.updated_at = datetime.now(timezone.utc)
        session.add(chat)

        await session.commit()
    except Exception:
        await session.rollback()
        await _cleanup_orphaned_files(saved_urls)
        raise

    await session.refresh(message)

    # Eager load sender and attachments for response
    await session.refresh(message, ["sender", "attachments"])

    # Notify other participants via WebSocket
    await notify_new_message(message, exclude_user_id=current_user.id)

    # Send persistent notifications to other participants
    other_participants = [p.id for p in chat.participants if p.id != current_user.id]
    if other_participants:
        sender_name = current_user.full_name or "User"
        # Truncate content for body if needed
        body_preview = content[:100] + "..." if len(content) > 100 else content
        
        await create_notifications_for_users(
            session,
            title=sender_name,
            body=body_preview,
            type="chat.message",
            url=f"/messenger/{chat_id}",
            tag=f"chat:{chat_id}",
            user_ids=other_participants,
            topic="chat",
            payload_data={
                "chatId": chat_id,
                "senderId": current_user.id,
                "messageId": message.id
            }
        )

    presence_map = await build_presence_map([message.sender_id], session=session)

    return MessageResponse(
        id=message.id,
        chat_id=message.chat_id,
        sender_id=message.sender_id,
        content=message.content,
        created_at=message.created_at,
        read_status=message.read_status,
        sender=message.sender,
        attachments=message.attachments,
        sender_presence=presence_map.get(message.sender_id),
    )


@router.post("/{chat_id}/read")
async def mark_read(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Mark all messages in a chat as read.
    """
    chat = await session.get(Chat, chat_id, options=[selectinload(Chat.participants)])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Not a participant")

    # Update unread messages sent by others
    query = select(Message).where(
        and_(
            Message.chat_id == chat_id,
            Message.sender_id != current_user.id,
            Message.read_status.is_(False),
        )
    )
    result = await session.execute(query)
    unread_messages = result.scalars().all()

    for msg in unread_messages:
        msg.read_status = True
        session.add(msg)

    await session.commit()
    return {"status": "ok"}


@router.post("/{chat_id}/clear", response_model=ChatMaintenanceResult)
async def clear_chat_history(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Remove all messages (and attachments) from a chat for its participants."""

    chat = await _get_chat_for_user(session, chat_id, current_user, load_messages=True)

    attachment_urls = _collect_attachment_urls(chat)
    message_count = len(chat.messages)
    attachment_count = len(attachment_urls)

    try:
        for message in list(chat.messages):
            await session.delete(message)
        chat.updated_at = datetime.now(timezone.utc)
        session.add(chat)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await _cleanup_orphaned_files(attachment_urls)

    return ChatMaintenanceResult(
        chat_id=chat.id,
        status="cleared",
        deleted_messages=message_count,
        deleted_attachments=attachment_count,
    )


@router.delete("/{chat_id}", response_model=ChatMaintenanceResult)
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete a chat entirely for all participants (messages, attachments, links)."""

    chat = await _get_chat_for_user(session, chat_id, current_user, load_messages=True)

    attachment_urls = _collect_attachment_urls(chat)
    message_count = len(chat.messages)
    attachment_count = len(attachment_urls)

    try:
        await session.delete(chat)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await _cleanup_orphaned_files(attachment_urls)

    return ChatMaintenanceResult(
        chat_id=chat_id,
        status="deleted",
        deleted_messages=message_count,
        deleted_attachments=attachment_count,
    )
