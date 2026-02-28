import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import SecureBaseModel


class DTOModel(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class StoryDTO(DTOModel):
    id: uuid.UUID
    title: str
    title_en: str | None
    short_text: str
    short_text_en: str | None
    cover_url: str | None
    cta_url: str | None
    published_at: datetime
    expires_at: datetime
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
