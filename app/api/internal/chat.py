"""Internal endpoint: room-join authorization for the WebSocket hub.

The Go ws-hub calls this endpoint before permitting a user to join a chat
room over WebSocket.  The check is intentionally simple and read-only —
it only answers "is user X a participant of chat Y?", returning 200 or 403.
No session creation or mutation takes place here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.repositories.chat_repository import ChatRepository

router = APIRouter(prefix="/chat", tags=["internal-chat"])


@router.get(
    "/check-participant",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def check_participant(
    user_id: uuid.UUID = Query(..., description="User to authorize"),
    room_id: uuid.UUID = Query(..., description="Chat room UUID"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Return 200 if the user is a participant of the chat room, else 403.

    Called by the Go ws-hub's InternalAPIAuthClient.  Must remain lightweight:
    no authentication is verified here because the endpoint is already
    protected by InternalAccessMiddleware (allowed only from Docker-internal
    network / localhost).
    """
    repo = ChatRepository(db)
    if not await repo.check_participant(room_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "not_participant",
                "message": "User is not a chat participant",
            },
        )
    return {"participant": True}
