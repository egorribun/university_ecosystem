from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from app.schemas.base import SecureBaseModel


# Simplified User schema for chat participants (avoids lazy-loaded relationships)
class ChatParticipant(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool


class PresenceStatus(SecureBaseModel):
    """Represents a participant's presence state."""

    active: bool = False
    last_seen_at: datetime | None = None


class MessageBase(SecureBaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class AttachmentResponse(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    file_type: str
    filename: str
    size: int
    created_at: datetime | None = None
    message_id: UUID | None = None


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    sender_id: UUID
    created_at: datetime
    read_status: bool
    sender: ChatParticipant | None = None
    sender_presence: PresenceStatus | None = None
    attachments: list[AttachmentResponse] = []


class ChatBase(SecureBaseModel):
    pass


class ChatCreate(ChatBase):
    participant_id: UUID  # The ID of the user to start a chat with


class ChatResponse(ChatBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participants: list[ChatParticipant]
    last_message: MessageResponse | None = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime
    presence: dict[UUID, PresenceStatus] | None = None


class ChatsListOut(SecureBaseModel):
    """Paginated list of chats."""

    items: list[ChatResponse]
    has_more: bool = False
    next_cursor: str | None = None


class MessagesListOut(SecureBaseModel):
    """Paginated list of messages."""

    items: list[MessageResponse]
    has_more: bool = False
    next_cursor: str | None = None


class ChatMaintenanceResult(SecureBaseModel):
    """Represents the result of a maintenance operation on a chat."""

    chat_id: UUID
    status: str
    deleted_messages: int = 0
    deleted_attachments: int = 0
