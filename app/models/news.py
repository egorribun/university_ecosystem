import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin
from app.models.mixins import UserFK, UUID7PrimaryKeyMixin

USERS_ID_FK = "users.id"


class News(Base, EventEmitterMixin, UUID7PrimaryKeyMixin):
    __tablename__ = "news"

    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    title_en = Column(String)
    content_en = Column(Text)
    image_url = Column(String)
    embedding = Column(Text().with_variant(Vector(1536), "postgresql"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    author = relationship("User")

    __table_args__ = (
        Index(
            "ix_news_embedding",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    likes = relationship(
        "NewsLike", back_populates="news", cascade="all, delete-orphan"
    )
    comments = relationship(
        "NewsComment", back_populates="news", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<News(id={self.id}, title='{self.title[:30]}...')>"


class NewsLike(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "news_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "news_id", name="uq_news_like_user_news"),
        Index("ix_news_likes_news_created", "news_id", "created_at"),
    )

    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news.id", ondelete="CASCADE"),
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    news = relationship("News", back_populates="likes")
    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<NewsLike(id={self.id}, news_id={self.news_id}, user_id={self.user_id})>"
        )


class NewsComment(Base, UUID7PrimaryKeyMixin, UserFK):
    __tablename__ = "news_comments"
    __table_args__ = (Index("ix_news_comments_news_created", "news_id", "created_at"),)

    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news.id", ondelete="CASCADE"),
        index=True,
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    news = relationship("News", back_populates="comments")
    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<NewsComment(id={self.id}, news_id={self.news_id}, "
            f"content='{self.content[:20]}...')>"
        )
