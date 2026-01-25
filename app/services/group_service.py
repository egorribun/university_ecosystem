from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import models


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_groups(self) -> list[models.Group]:
        """Get all groups."""
        return await crud.get_groups(self.db)
