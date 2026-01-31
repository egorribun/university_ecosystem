from sqlalchemy.ext.asyncio import AsyncSession

from app.models import models
from app.repositories.schedule_repository import GroupRepository


class GroupService:
    def __init__(self, db: AsyncSession, repo: GroupRepository) -> None:
        self.db = db
        self.repo = repo

    async def get_groups(self) -> list[models.Group]:
        """Get all groups."""
        return await self.repo.list_groups()
