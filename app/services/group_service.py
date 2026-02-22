from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.schedule_repository import GroupRepository
from app.schemas.dtos import GroupDTO


class GroupService:
    def __init__(self, db: AsyncSession, repo: GroupRepository) -> None:
        self.db = db
        self.repo = repo

    async def get_groups(self) -> Sequence[GroupDTO]:
        """Get all groups."""
        return await self.repo.list_groups()
