from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

from app.repositories.schedule_repository import GroupRepository
from app.schemas.dtos import GroupDTO


class GroupService:
    def __init__(self, db: AsyncDatabaseSession, repo: GroupRepository) -> None:
        self.db = db
        self.repo = repo

    async def get_groups(self) -> Sequence[GroupDTO]:
        """Get all groups."""
        return await self.repo.list_groups()
