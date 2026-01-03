from datetime import datetime

from pydantic import BaseModel, ConfigDict


# Simplified User schema for chat participants (avoids lazy-loaded relationships)
class ChatParticipant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool


class PresenceStatus(BaseModel):
    """Represents a participant's presence state."""

    active: bool = False
    last_seen_at: datetime | None = None


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    file_type: str
    filename: str
    size: int


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    sender_id: int
    created_at: datetime
    read_status: bool
    sender: ChatParticipant | None = None
    sender_presence: PresenceStatus | None = None
    attachments: list[AttachmentResponse] = []


class ChatBase(BaseModel):
    pass


class ChatCreate(ChatBase):
    participant_id: int  # The ID of the user to start a chat with


class ChatResponse(ChatBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    participants: list[ChatParticipant]
    last_message: MessageResponse | None = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime
    presence: dict[int, PresenceStatus] | None = None


class ChatsListOut(BaseModel):
    """Paginated list of chats."""

    items: list[ChatResponse]
    has_more: bool = False
    next_cursor: str | None = None


class MessagesListOut(BaseModel):
    """Paginated list of messages."""

    items: list[MessageResponse]
    has_more: bool = False
    next_cursor: str | None = None


class ChatMaintenanceResult(BaseModel):
    """Represents the result of a maintenance operation on a chat."""

    chat_id: str
    status: str
    deleted_messages: int = 0
    deleted_attachments: int = 0
