"""News article, comment and interaction schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    ConfigDict,
    Field,
)

from app.schemas.common import BaseModel, OrmModel
from app.schemas.validators import SafeRichText, SanitizedInput, SanitizedStr


class NewsCommentOut(BaseModel):
    id: uuid.UUID
    content: str
    user_id: uuid.UUID
    user_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NewsCommentCreate(BaseModel):
    content: SafeRichText = Field(..., min_length=1, max_length=1000)


class NewsCommentUpdate(BaseModel):
    content: SafeRichText = Field(..., min_length=1, max_length=1000)


class NewsInteractionsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    likes_count: int
    is_liked: bool
    comments: list[NewsCommentOut]
    comments_count: int


class NewsCreate(BaseModel):
    title: SanitizedStr
    content: SafeRichText
    title_en: SanitizedInput = None
    content_en: SafeRichText | None = None
    image_url: str | None = None


class NewsUpdate(BaseModel):
    title: SanitizedStr | None = None
    content: SafeRichText | None = None
    title_en: SanitizedInput = None
    content_en: SafeRichText | None = None
    image_url: str | None = None


class NewsOut(OrmModel, NewsCreate):
    id: uuid.UUID
    created_at: datetime
    likes_count: int = 0
    comments_count: int = 0
    is_liked: bool = False

    image_url_optimized: str | None = None


class PaginatedNews(BaseModel):
    """Paginated news response with cursor-based pagination."""

    items: list[NewsOut]
    has_more: bool
    next_cursor: str | None = None
