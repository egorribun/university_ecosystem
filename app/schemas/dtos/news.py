import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DTOModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

class NewsDTO(DTOModel):
    id: uuid.UUID
    title: str
    content: str
    author_id: uuid.UUID | None
    title_en: str | None
    content_en: str | None
    image_url: str | None
    created_at: datetime

class NewsLikeDTO(DTOModel):
    id: uuid.UUID
    news_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime

class NewsCommentDTO(DTOModel):
    id: uuid.UUID
    news_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    created_at: datetime

class NewsListingDTO(DTOModel):
    news: NewsDTO
    likes_count: int
    comments_count: int
    is_liked: bool

class NewsCommentListingDTO(DTOModel):
    id: uuid.UUID
    content: str
    user_id: uuid.UUID
    user_name: str
    created_at: datetime

class NewsInteractionsDTO(DTOModel):
    likes_count: int
    is_liked: bool
    comments: list[NewsCommentListingDTO]
    comments_count: int
