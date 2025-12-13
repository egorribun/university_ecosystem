import csv
import io
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.models import DataAccessLog


def _normalize_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def log_data_access(
    db: AsyncSession,
    *,
    actor_user_id: int | None,
    subject_user_id: int | None,
    resource_type: str,
    action: str,
    request: Request,
    resource_id: str | None = None,
    context: dict | None = None,
) -> DataAccessLog:
    log_entry = DataAccessLog(
        actor_user_id=actor_user_id,
        subject_user_id=subject_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        context=context or {},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)
    return log_entry


async def cleanup_access_logs(
    *, db: AsyncSession | None = None, retention_days: int = 180
) -> int:
    owns_session = db is None
    retention = max(0, int(retention_days))
    if retention <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention)
    if owns_session:
        async with async_session() as session:
            return await cleanup_access_logs(db=session, retention_days=retention)
    stmt = delete(DataAccessLog).where(DataAccessLog.created_at < cutoff)
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    await db.commit()
    return int(result.rowcount or 0)


async def export_access_logs(
    db: AsyncSession,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 10_000,
    actor_user_id: int | None = None,
    subject_user_id: int | None = None,
) -> Iterable[DataAccessLog]:
    start = _normalize_time(start_at)
    end = _normalize_time(end_at)
    stmt = select(DataAccessLog).order_by(DataAccessLog.created_at.desc()).limit(limit)
    if start is not None:
        stmt = stmt.where(DataAccessLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(DataAccessLog.created_at <= end)
    if actor_user_id is not None:
        stmt = stmt.where(DataAccessLog.actor_user_id == actor_user_id)
    if subject_user_id is not None:
        stmt = stmt.where(DataAccessLog.subject_user_id == subject_user_id)
    result = await db.execute(stmt)
    return result.scalars().all()


def serialize_access_logs_csv(entries: Iterable[DataAccessLog]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at",
            "actor_user_id",
            "subject_user_id",
            "resource_type",
            "resource_id",
            "action",
            "ip_address",
            "user_agent",
            "context",
        ]
    )
    for entry in entries:
        writer.writerow(
            [
                entry.created_at.isoformat() if entry.created_at else None,
                entry.actor_user_id,
                entry.subject_user_id,
                entry.resource_type,
                entry.resource_id,
                entry.action,
                entry.ip_address,
                entry.user_agent,
                entry.context,
            ]
        )
    return buffer.getvalue()
