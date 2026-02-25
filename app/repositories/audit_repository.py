from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select

from app.core.protocols import AsyncDatabaseSession
from app.models.logs import DataAccessLog
from app.repositories.base import BaseRepository
from app.schemas.dtos.audit import DataAccessLogDTO


class AuditRepository(BaseRepository[DataAccessLog, DataAccessLogDTO, dict, dict]):
    """Repository for Audit and Data Access logs."""

    @property
    def model(self) -> type[DataAccessLog]:
        return DataAccessLog

    @property
    def dto_class(self) -> type[DataAccessLogDTO]:
        return DataAccessLogDTO

    async def get_logs_by_user(
        self, user_id: uuid.UUID | int, limit: int = 100
    ) -> Sequence[DataAccessLogDTO]:
        """Fetch audit logs involving a user."""
        stmt = (
            select(DataAccessLog)
            .where(
                (DataAccessLog.actor_user_id == user_id)
                | (DataAccessLog.subject_user_id == user_id)
            )
            .order_by(DataAccessLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [self._to_dto(row) for row in result.scalars().all()]

    async def prune_logs(self, cutoff: datetime) -> int:
        """Delete logs older than cutoff."""
        stmt = delete(DataAccessLog).where(DataAccessLog.created_at < cutoff)
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def list_logs(
        self,
        *,
        actor_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[DataAccessLogDTO]:
        """List logs with filters."""
        stmt = select(DataAccessLog)
        if actor_id:
            stmt = stmt.where(DataAccessLog.actor_user_id == actor_id)
        if subject_id:
            stmt = stmt.where(DataAccessLog.subject_user_id == subject_id)
        if resource_type:
            stmt = stmt.where(DataAccessLog.resource_type == resource_type)

        stmt = (
            stmt.order_by(DataAccessLog.created_at.desc()).offset(offset).limit(limit)
        )
        result = await self.db.execute(stmt)
        return [self._to_dto(row) for row in result.scalars().all()]

    async def batch_create(self, entries: list[dict]) -> None:
        """Batch create audit logs."""
        logs = [DataAccessLog(**e) for e in entries]
        self.db.add_all(logs)


def get_audit_repository(db: AsyncDatabaseSession) -> AuditRepository:
    return AuditRepository(db)
