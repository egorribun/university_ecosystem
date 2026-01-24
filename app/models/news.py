from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.events import EventEmitterMixin


class News(Base, EventEmitterMixin):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    title_en = Column(String)
    content_en = Column(Text)
    image_url = Column(String)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    likes = relationship(
        "NewsLike", back_populates="news", cascade="all, delete-orphan"
    )
    comments = relationship(
        "NewsComment", back_populates="news", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<News(id={self.id}, title='{self.title[:30]}...')>"


class NewsLike(Base):
    __tablename__ = "news_likes"

    id = Column(Integer, primary_key=True)
    news_id = Column(
        Integer, ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    news = relationship("News", back_populates="likes")
    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<NewsLike(id={self.id}, news_id={self.news_id}, user_id={self.user_id})>"
        )


class NewsComment(Base):
    __tablename__ = "news_comments"

    id = Column(Integer, primary_key=True)
    news_id = Column(
        Integer, ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    news = relationship("News", back_populates="comments")
    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<NewsComment(id={self.id}, news_id={self.news_id}, "
            f"content='{self.content[:20]}...')>"
        )
