"""Chat REST API endpoints.

TD-W9-01/05 (audit 2026-03-16): The dead ChatService wrapper is removed.
Each endpoint now injects the narrowest service it needs:
  - POST /chats           → ChatCreationService
  - GET  /chats*          → ChatQueryService   (read replica)
  - POST /chats/{id}/messages, /{id}/read, /{id}/clear, DELETE /{id}
                          → ChatCommandService (write DB)
"""

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
    get_chat_creation_service,
    get_chat_maintenance_service,
    get_chat_message_dispatcher,
    get_current_user,
    get_locale,
    get_read_chat_query_service,
)
from app.core.ratelimit import sensitive_route_limit
from app.models import User
from app.schemas.chat import (
    ChatCreate,
    ChatMaintenanceResult,
    ChatResponse,
    ChatsListOut,
    MessageResponse,
    MessagesListOut,
    ReactorOut,
)
from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
)
from app.services.chat.creation_service import ChatCreationService
from app.services.chat.query_service import ChatQueryService

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get(
    "",
    response_model=ChatsListOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def get_chats(
    current_user: Annotated[User, Depends(get_current_user)],
    query_service: Annotated[ChatQueryService, Depends(get_read_chat_query_service)],
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Number of chats to return"),
) -> ChatsListOut:
    """Get all chats for the current user with cursor-based pagination."""
    return await query_service.get_chats(current_user, cursor, limit)


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[Depends(sensitive_route_limit())],
)
async def create_chat(
    chat_in: ChatCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    creation_service: Annotated[
        ChatCreationService, Depends(get_chat_creation_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatResponse:
    """Create a new chat with a user.  If a DM chat already exists, return it."""
    return await creation_service.create_chat(
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
    query_service: Annotated[ChatQueryService, Depends(get_read_chat_query_service)],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatResponse:
    """Get details for a specific chat."""
    return await query_service.get_chat_details(chat_id, current_user, locale=locale)


@router.get(
    "/{chat_id}/messages",
    response_model=MessagesListOut,
    dependencies=[Depends(sensitive_route_limit())],
)
async def get_messages(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    query_service: Annotated[ChatQueryService, Depends(get_read_chat_query_service)],
    locale: Annotated[str, Depends(get_locale)],
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=100, description="Number of messages to return"),
) -> MessagesListOut:
    """Get messages for a chat with cursor-based pagination (oldest first)."""
    return await query_service.get_messages(
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
    dispatcher: Annotated[ChatMessageDispatcher, Depends(get_chat_message_dispatcher)],
    locale: Annotated[str, Depends(get_locale)],
    content: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    reply_to_message_id: uuid.UUID | None = Form(
        None,
        description="ID of the message being replied to, if this is a reply.",
    ),
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
        max_length=64,
        description="Client-generated idempotency key to deduplicate retried sends.",
    ),
) -> MessageResponse:
    """Send a message to a chat.  Supports ``Idempotency-Key`` header for retry-safe sends."""
    return await dispatcher.send_message(
        chat_id,
        current_user,
        content,
        files,
        locale=locale,
        idempotency_key=idempotency_key,
        reply_to_message_id=reply_to_message_id,
    )


@router.post(
    "/{chat_id}/read",
    dependencies=[Depends(sensitive_route_limit())],
)
async def mark_read(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
) -> dict[str, str]:
    """Mark all messages in a chat as read."""
    await maintenance.mark_read(chat_id, current_user, locale=locale)
    return {"status": "ok"}


@router.patch(
    "/{chat_id}/messages/{message_id}",
    dependencies=[Depends(sensitive_route_limit())],
)
async def edit_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
    content: str = Form(..., min_length=1, max_length=32768),
) -> dict[str, str]:
    """Edit a message's content (author-only).  W174 auto-cookie covers PATCH CSRF."""
    await maintenance.edit_message(
        chat_id, message_id, current_user, content, locale=locale
    )
    return {"status": "ok"}


@router.delete(
    "/{chat_id}/messages/{message_id}",
    dependencies=[Depends(sensitive_route_limit())],
)
async def delete_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
) -> dict[str, str]:
    """Soft-delete a message (author-only).  W174 auto-cookie covers DELETE CSRF."""
    await maintenance.soft_delete_message(
        chat_id, message_id, current_user, locale=locale
    )
    return {"status": "ok"}


@router.post(
    "/{chat_id}/messages/{message_id}/reactions",
    dependencies=[Depends(sensitive_route_limit())],
)
async def add_reaction(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
    emoji: str = Form(..., min_length=1, max_length=16),
) -> dict[str, str]:
    """Add an emoji reaction to a message (idempotent, any participant).

    W174 auto-cookie covers POST CSRF.
    """
    await maintenance.add_reaction(
        chat_id, message_id, current_user, emoji, locale=locale
    )
    return {"status": "ok"}


@router.delete(
    "/{chat_id}/messages/{message_id}/reactions",
    dependencies=[Depends(sensitive_route_limit())],
)
async def remove_reaction(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
    emoji: str = Query(..., min_length=1, max_length=16),
) -> dict[str, str]:
    """Remove an emoji reaction from a message (idempotent).

    W206 SW7 — emoji is a QUERY param, NOT a URL-path segment. Query params decode
    unambiguously (parse_qs); that is the robust shape for an arbitrary
    multi-codepoint emoji used as a sub-resource selector, whereas multi-byte
    content in a URL path segment is a known fragility class. Verified LIVE
    end-to-end (two-browser cross-user add + remove of a real 👍, W206 SW7).

    Honest re-attribution: the mid-wave switch from the SW4 path route was first
    blamed on a Caddy path mis-decode, but live verification showed the earlier
    "failed remove" was a CORRUPT stored value — curl on Windows Git-Bash mangles a
    literal multi-byte emoji in a request BODY to "??", so the curl-added reaction
    was stored as "??" and no remove could match the correctly-encoded 👍. The
    query param is retained as the more robust design (the path route was never
    verified for a real emoji). W174 auto-cookie covers DELETE CSRF.
    """
    await maintenance.remove_reaction(
        chat_id, message_id, current_user, emoji, locale=locale
    )
    return {"status": "ok"}


@router.get(
    "/{chat_id}/messages/{message_id}/reactions",
    response_model=list[ReactorOut],
    dependencies=[Depends(sensitive_route_limit())],
)
async def get_reactors(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    query_service: Annotated[ChatQueryService, Depends(get_read_chat_query_service)],
    locale: Annotated[str, Depends(get_locale)],
    emoji: str = Query(..., min_length=1, max_length=16),
) -> list[ReactorOut]:
    """List the users who reacted to a message with a specific emoji (Wave 207).

    Powers the reactor-list "who reacted" popover — reactor identities are loaded
    on-demand, NOT bundled into GET /messages. Participant-authz'd + message-in-chat
    guarded (a participant of one chat can't enumerate reactors of a message in
    another by guessing its id). emoji is a QUERY param (same robust shape as the
    DELETE route, W206 SW7). Coexists with POST + DELETE at this path (FastAPI
    routes by method).
    """
    return await query_service.get_reactors(
        chat_id, message_id, emoji, current_user, locale=locale
    )


@router.post(
    "/{chat_id}/typing",
    dependencies=[
        Depends(sensitive_route_limit(limit=180, window_sec=60, key_prefix="typing"))
    ],
)
async def typing_indicator(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
) -> dict[str, str]:
    """Broadcast a 'typing' indicator to the other chat participants (Wave 207).

    The frontend WS connects to ws-hub, which drops "typing" frames at its parse
    boundary — so typing can't relay peer-to-peer over the socket. This REST endpoint
    does the participant authz + broadcast (W204 bridge → ws-hub chat.* fan-out → the
    other participants' live TypingIndicator). A permissive 180/60 limiter (vs the
    strict 5/60 default) gives headroom over the client's 500ms (~2/sec) throttle while
    capping broadcast-spam abuse. W174 auto-cookie covers POST CSRF.
    """
    await maintenance.broadcast_typing(chat_id, current_user, locale=locale)
    return {"status": "ok"}


@router.post(
    "/{chat_id}/clear",
    response_model=ChatMaintenanceResult,
    dependencies=[Depends(sensitive_route_limit())],
)
async def clear_chat_history(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatMaintenanceResult:
    """Remove all messages (and attachments) from a chat for its participants."""
    return await maintenance.clear_history(chat_id, current_user, locale=locale)


@router.delete(
    "/{chat_id}",
    response_model=ChatMaintenanceResult,
    dependencies=[Depends(sensitive_route_limit())],
)
async def delete_chat(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    maintenance: Annotated[
        ChatMaintenanceService, Depends(get_chat_maintenance_service)
    ],
    locale: Annotated[str, Depends(get_locale)],
) -> ChatMaintenanceResult:
    """Delete a chat entirely for all participants (messages, attachments, links)."""
    return await maintenance.delete_chat(chat_id, current_user, locale=locale)
