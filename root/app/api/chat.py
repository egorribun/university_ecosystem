from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
import uuid
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.chat import Chat, Message, chat_participants, Attachment
from app.models.models import User
from app.schemas.chat import ChatCreate, ChatResponse, MessageCreate, MessageResponse

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("", response_model=List[ChatResponse])
async def get_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Get all chats for the current user.
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
        .order_by(last_message_subquery.desc().nulls_last())
    )
    result = await session.execute(query)
    chats = result.scalars().all()

    # Process chats to add last_message and unread_count
    chat_responses = []
    for chat in chats:
        # Sort messages to find the last one
        sorted_messages = sorted(chat.messages, key=lambda m: m.created_at, reverse=True)
        last_message = sorted_messages[0] if sorted_messages else None
        
        unread_count = sum(
            1 for m in chat.messages 
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

    return chat_responses


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
    # This is a bit complex in SQL, simpler to fetch user's chats and check in python for now
    # or use a specific query. For MVP, let's try to find a chat with exactly these 2 participants.
    
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

    return ChatResponse(
        id=new_chat.id,
        participants=new_chat.participants,
        created_at=new_chat.created_at,
        updated_at=new_chat.updated_at,
    )


@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Get messages for a chat.
    """
    chat = await session.get(Chat, chat_id, options=[selectinload(Chat.participants)])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Not a participant")

    query = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .options(selectinload(Message.sender))
    )
    result = await session.execute(query)
    messages = result.scalars().all()

    return messages


@router.post("/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    content: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Send a message to a chat.
    """
    print(f"DEBUG: send_message called. chat_id={chat_id}")
    print(f"DEBUG: content={content}")
    print(f"DEBUG: files count={len(files) if files else 0}")
    if files:
        for f in files:
            print(f"DEBUG: file={f.filename}, content_type={f.content_type}")

    chat = await session.get(Chat, chat_id, options=[selectinload(Chat.participants)])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Not a participant")

    message = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        content=content,
    )
    session.add(message)
    await session.flush()  # Flush to get message ID

    # Handle file uploads
    if files:
        import os
        import shutil

        UPLOAD_DIR = "app/static/uploads"
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        for file in files:
            # Generate unique filename
            file_ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, unique_filename)
            
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Determine file type
            file_type = 'file'
            if file.content_type.startswith('image/'):
                file_type = 'image'
            elif file.content_type.startswith('video/'):
                file_type = 'video'

            # Create attachment record
            # URL should be accessible from frontend. Assuming static files are served from /static
            url = f"http://localhost:8000/static/uploads/{unique_filename}"
            
            attachment = Attachment(
                message_id=message.id,
                url=url,
                file_type=file_type,
                filename=file.filename,
                size=file.size or 0
            )
            session.add(attachment)
    
    # Update chat updated_at
    chat.updated_at = datetime.utcnow()
    session.add(chat)

    await session.commit()
    await session.refresh(message)
    
    # Eager load sender and attachments for response
    await session.refresh(message, ["sender", "attachments"])

    return message


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
    query = (
        select(Message)
        .where(
            and_(
                Message.chat_id == chat_id,
                Message.sender_id != current_user.id,
                Message.read_status == False
            )
        )
    )
    result = await session.execute(query)
    unread_messages = result.scalars().all()

    for msg in unread_messages:
        msg.read_status = True
        session.add(msg)

    await session.commit()
    return {"status": "ok"}
