from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# Simplified User schema for chat participants (avoids lazy-loaded relationships)
class ChatParticipant(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    is_active: bool


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class AttachmentResponse(BaseModel):
    id: str
    url: str
    file_type: str
    filename: str
    size: int

    class Config:
        from_attributes = True


class MessageResponse(MessageBase):
    id: str
    chat_id: str
    sender_id: int
    created_at: datetime
    read_status: bool
    sender: Optional[ChatParticipant] = None
    attachments: List[AttachmentResponse] = []

    class Config:
        from_attributes = True


class ChatBase(BaseModel):
    pass


class ChatCreate(ChatBase):
    participant_id: int  # The ID of the user to start a chat with


class ChatResponse(ChatBase):
    id: str
    participants: List[ChatParticipant]
    last_message: Optional[MessageResponse] = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
