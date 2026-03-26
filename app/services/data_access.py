from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import AsyncIterable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select

from app.core.database import async_session
from app.core.protocols import AsyncDatabaseSession
from app.models.models import DataAccessLog
from app.repositories.audit_repository import AuditRepository
from app.schemas.dtos.audit import DataAccessLogDTO


def _normalize_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def log_data_access(
    db: AsyncDatabaseSession,
    *,
    actor_user_id: uuid.UUID | int | None,
    subject_user_id: uuid.UUID | int | None,
    resource_type: str,
    action: str,
    request: Request,
    resource_id: str | None = None,
    context: dict[str, Any] | None = None,
    commit: bool = True,
) -> DataAccessLogDTO:
    created_at = datetime.now(UTC)

    # Calculate signature
    from app.utils.audit import calculate_log_signature

    signature = calculate_log_signature(
        actor_user_id=actor_user_id,
        subject_user_id=subject_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        context=context or {},
        ip_address=request.client.host if request.client else "unknown",  # MED-W19
        user_agent=request.headers.get("user-agent"),
        created_at=created_at,
    )

    repo = AuditRepository(db)
    log_entry = await repo.create(
        {
            "actor_user_id": actor_user_id,
            "subject_user_id": subject_user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "context": context or {},
            "ip_address": request.client.host
            if request.client
            else "unknown",  # MED-W19
            "user_agent": request.headers.get("user-agent"),
            "created_at": created_at,
            "signature": signature,
        }
    )
    if commit:
        await db.commit()
    return log_entry


async def batch_log_data_access(
    db: AsyncDatabaseSession,
    *,
    entries: list[dict[str, Any]],
    request: Request,
    commit: bool = True,
) -> None:
    if not entries:
        return

    created_at = datetime.now(UTC)
    from app.utils.audit import calculate_log_signature

    log_entries = []
    ip_address = request.client.host if request.client else "unknown"  # MED-W19
    user_agent = request.headers.get("user-agent")

    for entry in entries:
        actor_user_id = entry.get("actor_user_id")
        subject_user_id = entry.get("subject_user_id")
        resource_type = entry.get("resource_type")
        resource_id = entry.get("resource_id")
        action = entry.get("action")
        context = entry.get("context", {})

        signature = calculate_log_signature(
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            resource_type=str(resource_type) if resource_type else "",
            resource_id=str(resource_id) if resource_id else None,
            action=str(action) if action else "",
            context=context,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=created_at,
        )

        log_entries.append(
            {
                "actor_user_id": actor_user_id,
                "subject_user_id": subject_user_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "context": context,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": created_at,
                "signature": signature,
            }
        )

    repo = AuditRepository(db)
    await repo.batch_create(log_entries)
    if commit:
        await db.commit()


async def cleanup_access_logs(
    *, db: AsyncDatabaseSession | None = None, retention_days: int = 180
) -> int:
    owns_session = db is None
    retention = max(0, int(retention_days))
    if retention <= 0:
        return 0
    if owns_session:
        async with async_session() as session:
            return await cleanup_access_logs(db=session, retention_days=retention)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    assert db is not None  # noqa: S101
    repo = AuditRepository(db)
    count = await repo.prune_logs(cutoff)
    return count


async def export_access_logs(
    db: AsyncDatabaseSession,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 10_000,
    actor_user_id: int | None = None,
    subject_user_id: int | None = None,
) -> Iterable[DataAccessLogDTO]:
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

    repo = AuditRepository(db)
    return [repo._to_dto(row) for row in result.scalars().all()]


def serialize_access_logs_csv(entries: Iterable[DataAccessLogDTO]) -> str:
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


async def export_access_logs_stream(
    db: AsyncDatabaseSession,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    actor_user_id: int | None = None,
    subject_user_id: int | None = None,
) -> AsyncIterable[str]:
    start = _normalize_time(start_at)
    end = _normalize_time(end_at)
    stmt = select(DataAccessLog).order_by(DataAccessLog.created_at.desc())
    if start is not None:
        stmt = stmt.where(DataAccessLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(DataAccessLog.created_at <= end)
    if actor_user_id is not None:
        stmt = stmt.where(DataAccessLog.actor_user_id == actor_user_id)
    if subject_user_id is not None:
        stmt = stmt.where(DataAccessLog.subject_user_id == subject_user_id)

    # Safety cap to prevent unbounded streaming
    stmt = stmt.limit(100_000)

    # Write header
    yield "created_at,actor_user_id,subject_user_id,resource_type,resource_id,action,ip_address,user_agent,context\n"

    repo = AuditRepository(db)

    stream = await db.stream(stmt.execution_options(yield_per=1000))
    async for row in stream.scalars():
        dto = repo._to_dto(row)

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def _sanitize_csv(val: Any) -> Any:
            if isinstance(val, str) and val.startswith(("=", "+", "-", "@")):
                return f"\t{val}"
            return val

        writer.writerow(
            [
                dto.created_at.isoformat() if dto.created_at else None,
                dto.actor_user_id,
                dto.subject_user_id,
                _sanitize_csv(dto.resource_type),
                _sanitize_csv(dto.resource_id),
                _sanitize_csv(dto.action),
                dto.ip_address,
                _sanitize_csv(dto.user_agent),
                _sanitize_csv(json.dumps(dto.context) if dto.context else ""),
            ]
        )
        yield buffer.getvalue()
