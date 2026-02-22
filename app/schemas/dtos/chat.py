import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    message_id: uuid.UUID
    url: str
    file_type: str
    filename: str
    size: int
    created_at: datetime


class MessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    chat_id: uuid.UUID
    sender_id: uuid.UUID
    content: str
    created_at: datetime
    read_status: bool = False
    attachments: list[AttachmentDTO] = []


class ChatParticipantDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    id: uuid.UUID
    full_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    is_active: bool = True


class ChatDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    participants: list[ChatParticipantDTO] = []
    messages: list[MessageDTO] = []
    # We'll handle messages as a separate paginated call usually,
    # but the model has a relationship.
