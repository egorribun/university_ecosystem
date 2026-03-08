import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    UploadFile,
)

from app.api.deps import (
    get_chat_service,
    get_current_user,
    get_locale,
    get_read_chat_service,
)
from app.core.ratelimit import sensitive_route_limit
from app.models.models import User
from app.schemas.chat import (
    ChatCreate,
    ChatMaintenanceResult,
    ChatResponse,
    ChatsListOut,
    MessageResponse,
    MessagesListOut,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get(
    "",
    response_model=ChatsListOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def get_chats(
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_read_chat_service)],
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Number of chats to return"),
) -> ChatsListOut:
    """
    Get all chats for the current user with cursor-based pagination.

    Returns chats ordered by last message timestamp (newest first).
    Use the `next_cursor` from the response to fetch the next page.
    """
    return await chat_service.get_chats(current_user, cursor, limit)


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
async def create_chat(
    chat_in: ChatCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatResponse:
    """
    Create a new chat with a user. If a chat already exists, return it.
    """
    return await chat_service.create_chat(
        current_user, chat_in.participant_id, locale=locale
    )


@router.get(
    "/{chat_id}",
    response_model=ChatResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
async def get_chat(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_read_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatResponse:
    """
    Get details for a specific chat.
    """
    return await chat_service.get_chat_details(chat_id, current_user, locale=locale)


@router.get(
    "/{chat_id}/messages",
    response_model=MessagesListOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def get_messages(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_read_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=100, description="Number of messages to return"),
) -> MessagesListOut:
    """
    Get messages for a chat with cursor-based pagination.

    Messages are returned in ascending order (oldest first).
    Use the `next_cursor` from the response to fetch older messages.
    """
    return await chat_service.get_messages(
        chat_id, current_user, cursor=cursor, limit=limit, locale=locale
    )


@router.post(
    "/{chat_id}/messages",
    response_model=MessageResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
async def send_message(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
    content: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
        max_length=64,
        description="Client-generated idempotency key to deduplicate retried sends.",
    ),
) -> MessageResponse:
    """
    Send a message to a chat.

    The message is saved to the database and all chat participants
    are notified via WebSocket in real-time.

    Supports the ``Idempotency-Key`` header: identical requests with the same
    key return the cached response for 24 hours without creating duplicate
    messages (Stripe-style retry-safe API).
    """
    return await chat_service.send_message(
        chat_id,
        current_user,
        content,
        files,
        locale=locale,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/{chat_id}/read",
    dependencies=[Depends(sensitive_route_limit())],
)
async def mark_read(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
) -> dict[str, str]:
    """
    Mark all messages in a chat as read.
    """
    await chat_service.mark_read(chat_id, current_user, locale=locale)
    return {"status": "ok"}


@router.post(
    "/{chat_id}/clear",
    response_model=ChatMaintenanceResult,
    dependencies=[Depends(sensitive_route_limit())],
)
async def clear_chat_history(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatMaintenanceResult:
    """Remove all messages (and attachments) from a chat for its participants."""
    return await chat_service.clear_history(chat_id, current_user, locale=locale)


@router.delete(
    "/{chat_id}",
    response_model=ChatMaintenanceResult,
    dependencies=[Depends(sensitive_route_limit())],
)
async def delete_chat(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatMaintenanceResult:
    """Delete a chat entirely for all participants (messages, attachments, links)."""
    return await chat_service.delete_chat(chat_id, current_user, locale=locale)
