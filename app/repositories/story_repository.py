"""
Story repository for story data access operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.stories import Story
from app.repositories.base import BaseRepository
from app.schemas.dtos import StoryDTO

if TYPE_CHECKING:
    import uuid

    from app.core.protocols import AsyncDatabaseSession


class StoryRepository(BaseRepository[Story, StoryDTO, dict[str, Any], dict[str, Any]]):
    """Repository for Story model operations."""

    @property
    def model(self) -> type[Story]:
        return Story

    @property
    def dto_class(self) -> type[StoryDTO]:
        return StoryDTO

    async def get_active(self, *, skip: int = 0, limit: int = 20) -> list[StoryDTO]:
        """Get active, non-expired stories ordered by published_at descending."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Story)
            .where(
                Story.is_active.is_(True),
                Story.expires_at > now,
                Story.published_at <= now,
            )
            .order_by(Story.published_at.desc())
            .offset(skip)
            .limit(limit)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_by_user(
        self, user_id: uuid.UUID, *, skip: int = 0, limit: int = 20
    ) -> list[StoryDTO]:
        """Get stories created by a specific user."""
        result = await self.db.execute(
            select(Story)
            .where(Story.created_by == user_id)
            .order_by(Story.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def count_active(self) -> int:
        """Count active, non-expired stories."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(func.count(Story.id)).where(
                Story.is_active.is_(True),
                Story.expires_at > now,
            )
        )
        return result.scalar() or 0

    async def get_expired(self, *, limit: int = 100) -> list[StoryDTO]:
        """Get expired stories for cleanup."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Story)
            .where(Story.expires_at <= now)
            .order_by(Story.expires_at.asc())
            .limit(limit)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def deactivate(self, story_id: uuid.UUID) -> bool:
        """Deactivate a story by ID."""
        story = await self._get_orm(story_id)
        if story is None:
            return False
        story.is_active = False
        await self.db.flush()
        return True


def get_story_repository(db: AsyncDatabaseSession) -> StoryRepository:
    """Factory function for dependency injection."""
    return StoryRepository(db)


__all__ = ["StoryRepository", "get_story_repository"]
