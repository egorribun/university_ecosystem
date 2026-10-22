"""Durable quota admission and retention for rejected upload quarantine."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.core.config import settings
from app.models.quarantine import QuarantineReservation, QuarantineStorageScope
from app.services.storage import (
    QuarantineStorageBackend,
    S3Storage,
    StaticFSStorage,
    UnsafeQuarantineInventoryKey,
)
from app.utils.uuid_v7 import generate_uuid7

_MAX_BOOTSTRAP_PAGES_PER_CALL = 100
_MAX_CURSOR_LENGTH = 4096
_MAX_SWEEP_BATCH = 1000


class QuarantineError(RuntimeError):
    """Base class for fail-closed quarantine admission and cleanup outcomes."""


class QuarantineQuotaExceeded(QuarantineError):
    """The configured storage-scoped byte budget is already full."""


class QuarantineInventoryIncomplete(QuarantineError):
    """A complete bounded inventory is required before storage is admitted."""


class QuarantineStoreUnavailable(QuarantineError):
    """The durable reservation or managed object write could not be confirmed."""


def storage_scope_identifier(
    backend: QuarantineStorageBackend, explicit_scope_id: str = ""
) -> str:
    """Return an opaque stable digest for all writers sharing one storage area."""
    override = explicit_scope_id.strip()
    if override:
        material = f"override\0{override}"
    elif isinstance(backend, StaticFSStorage):
        root = os.path.normcase(str(backend.base_dir.resolve(strict=False)))
        material = f"filesystem\0{root}"
    elif isinstance(backend, S3Storage):
        endpoint = (backend._endpoint_url or "aws").rstrip("/").casefold()
        material = f"s3\0{endpoint}\0{backend.bucket}"
    else:
        raise TypeError("Unsupported quarantine storage backend")
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class QuarantineService:
    """Reserve before writing and release only after verified deletion."""

    def __init__(
        self,
        backend: QuarantineStorageBackend,
        *,
        session_factory: async_sessionmaker[AsyncSession]
        | Any = database.async_session,
        retention_days: int | None = None,
        quota_bytes: int | None = None,
        inventory_page_size: int | None = None,
        explicit_scope_id: str | None = None,
    ) -> None:
        self.backend = backend
        self.session_factory = session_factory
        self.retention = timedelta(
            days=(
                settings.storage_quarantine_retention_days
                if retention_days is None
                else retention_days
            )
        )
        self.quota_bytes = (
            settings.storage_quarantine_quota_bytes
            if quota_bytes is None
            else quota_bytes
        )
        self.inventory_page_size = (
            settings.storage_quarantine_inventory_page_size
            if inventory_page_size is None
            else inventory_page_size
        )
        configured_scope_id = (
            settings.storage_quarantine_scope_id
            if explicit_scope_id is None
            else explicit_scope_id
        )
        self.scope_id = storage_scope_identifier(backend, configured_scope_id)

    async def _ensure_scope_row(self, session: AsyncSession) -> None:
        dialect = session.get_bind().dialect.name
        values = {"scope_id": self.scope_id, "inventory_complete": False}
        if dialect == "postgresql":
            postgres_statement = postgresql_insert(QuarantineStorageScope).values(
                **values
            )
            postgres_statement = postgres_statement.on_conflict_do_nothing(
                index_elements=["scope_id"]
            )
            await session.execute(postgres_statement)
        elif dialect == "sqlite":
            sqlite_statement = sqlite_insert(QuarantineStorageScope).values(**values)
            sqlite_statement = sqlite_statement.on_conflict_do_nothing(
                index_elements=["scope_id"]
            )
            await session.execute(sqlite_statement)
        else:
            raise RuntimeError("Quarantine reservations require PostgreSQL or SQLite")

    async def _verify_backend_policy(self) -> None:
        if isinstance(self.backend, S3Storage):
            await self.backend.assert_quarantine_versioning_disabled()

    async def ensure_inventory_complete(self) -> bool:
        """Import existing objects in bounded locked pages before any writes."""
        for _ in range(_MAX_BOOTSTRAP_PAGES_PER_CALL):
            async with self.session_factory() as session:
                async with session.begin():
                    await self._ensure_scope_row(session)
                    scope = await session.scalar(
                        select(QuarantineStorageScope)
                        .where(QuarantineStorageScope.scope_id == self.scope_id)
                        .with_for_update()
                    )
                    if scope is None:
                        raise RuntimeError("Quarantine storage scope disappeared")
                    if scope.inventory_complete:
                        return True

                    await self._verify_backend_policy()
                    cursor = scope.inventory_cursor
                    try:
                        page = await self.backend.list_quarantine_page(
                            cursor, limit=self.inventory_page_size
                        )
                    except UnsafeQuarantineInventoryKey:
                        # Keep admission closed until the unmanaged key is
                        # repaired, but preserve the cursor and prior charges.
                        return False
                    if (
                        page.next_cursor is not None
                        and len(page.next_cursor) > _MAX_CURSOR_LENGTH
                    ):
                        raise RuntimeError("Quarantine cursor exceeds the ledger bound")
                    if cursor is not None and page.next_cursor == cursor:
                        raise RuntimeError(
                            "Quarantine inventory cursor did not advance"
                        )

                    now = datetime.now(UTC)
                    dialect = session.get_bind().dialect.name
                    values: list[dict[str, Any]] = []
                    for item in page.objects:
                        modified = item.last_modified
                        if modified is None:
                            modified = now
                        elif modified.tzinfo is None:
                            modified = modified.replace(tzinfo=UTC)
                        if modified > now:
                            modified = now
                        values.append(
                            {
                                "id": generate_uuid7(),
                                "scope_id": self.scope_id,
                                "object_key": item.key,
                                "size_bytes": item.size_bytes,
                                "status": "stored",
                                "created_at": modified,
                                "expires_at": modified + self.retention,
                            }
                        )
                    if dialect == "postgresql":
                        if values:
                            postgres_statement = postgresql_insert(
                                QuarantineReservation
                            ).values(values)
                            postgres_statement = (
                                postgres_statement.on_conflict_do_nothing(
                                    index_elements=["scope_id", "object_key"]
                                )
                            )
                            await session.execute(postgres_statement)
                    elif dialect == "sqlite":
                        if values:
                            sqlite_statement = sqlite_insert(
                                QuarantineReservation
                            ).values(values)
                            sqlite_statement = sqlite_statement.on_conflict_do_nothing(
                                index_elements=["scope_id", "object_key"]
                            )
                            await session.execute(sqlite_statement)
                    else:
                        raise RuntimeError(
                            "Quarantine reservations require PostgreSQL or SQLite"
                        )

                    scope.inventory_cursor = page.next_cursor
                    scope.inventory_complete = page.next_cursor is None
            if page.next_cursor is None:
                return True
        return False

    async def _reserve(self, key: str, size_bytes: int) -> Any:
        async with self.session_factory() as session:
            async with session.begin():
                scope = await session.scalar(
                    select(QuarantineStorageScope)
                    .where(QuarantineStorageScope.scope_id == self.scope_id)
                    .with_for_update()
                )
                if scope is None or not scope.inventory_complete:
                    raise QuarantineInventoryIncomplete(
                        "Quarantine storage inventory is incomplete"
                    )
                used_bytes = await session.scalar(
                    select(
                        func.coalesce(func.sum(QuarantineReservation.size_bytes), 0)
                    ).where(QuarantineReservation.scope_id == self.scope_id)
                )
                if int(used_bytes or 0) + size_bytes > self.quota_bytes:
                    raise QuarantineQuotaExceeded(
                        "Quarantine storage quota is exhausted"
                    )
                reservation = QuarantineReservation(
                    scope_id=self.scope_id,
                    object_key=key,
                    size_bytes=size_bytes,
                    status="pending",
                )
                session.add(reservation)
                await session.flush()
                return reservation.id

    async def _mark_stored(self, reservation_id: Any) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                reservation = await session.scalar(
                    select(QuarantineReservation)
                    .where(
                        QuarantineReservation.id == reservation_id,
                        QuarantineReservation.status == "pending",
                    )
                    .with_for_update()
                )
                if reservation is None:
                    raise RuntimeError("Pending quarantine reservation disappeared")
                reservation.status = "stored"
                reservation.expires_at = datetime.now(UTC) + self.retention

    @staticmethod
    def _validate_object_key(key: str) -> None:
        if (
            not isinstance(key, str)
            or key != key.strip()
            or not key.startswith("quarantine/")
            or "\\" in key
            or any(ord(char) < 32 or ord(char) == 127 for char in key)
            or any(part in {"", ".", ".."} for part in key.split("/"))
        ):
            raise ValueError("Quarantine object key is invalid")

    async def store(self, key: str, data: bytes) -> str:
        """Persist a rejected payload after durable capacity admission."""
        self._validate_object_key(key)
        try:
            await self._verify_backend_policy()
            if not await self.ensure_inventory_complete():
                raise QuarantineInventoryIncomplete(
                    "Quarantine storage inventory is incomplete"
                )
            reservation_id = await self._reserve(key, len(data))
            result = await self.backend.save_file(
                key,
                data,
                content_type="application/octet-stream",
                cache_control="private, no-store",
            )
            await self._mark_stored(reservation_id)
            return result
        except QuarantineError:
            raise
        except Exception as exc:  # RZ-22-01-JUSTIFIED: preserve fail-closed rejection when quarantine persistence fails
            raise QuarantineStoreUnavailable(
                "Rejected payload could not be durably quarantined"
            ) from exc

    async def _mark_deleting_batch(
        self, limit: int, now: datetime
    ) -> list[tuple[Any, str]]:
        if isinstance(limit, bool) or not 1 <= limit <= _MAX_SWEEP_BATCH:
            raise ValueError("Quarantine cleanup limit is outside its bound")
        # Inventory incompleteness blocks new reservations, but should not
        # starve cleanup of records already represented in the ledger.
        await self.ensure_inventory_complete()
        async with self.session_factory() as session:
            async with session.begin():
                rows = (
                    await session.scalars(
                        select(QuarantineReservation)
                        .where(
                            QuarantineReservation.scope_id == self.scope_id,
                            or_(
                                QuarantineReservation.status == "deleting",
                                (
                                    (QuarantineReservation.status == "stored")
                                    & (QuarantineReservation.expires_at <= now)
                                ),
                            ),
                        )
                        .order_by(QuarantineReservation.expires_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                selected: list[tuple[Any, str]] = []
                for row in rows:
                    row.status = "deleting"
                    selected.append((row.id, row.object_key))
                return selected

    async def _release_verified_absence(self, reservation_id: Any) -> bool:
        async with self.session_factory() as session:
            async with session.begin():
                reservation = await session.scalar(
                    select(QuarantineReservation)
                    .where(
                        QuarantineReservation.id == reservation_id,
                        QuarantineReservation.status == "deleting",
                    )
                    .with_for_update()
                )
                if reservation is None:
                    return False
                await session.delete(reservation)
                return True

    async def sweep_once(self, *, limit: int = 100) -> int:
        """Delete a bounded batch and release only verified absent objects."""
        now = datetime.now(UTC)
        selected = await self._mark_deleting_batch(limit, now)
        released = 0
        for reservation_id, key in selected:
            await self._verify_backend_policy()
            if await self.backend.delete_quarantine_key(key):
                if await self._release_verified_absence(reservation_id):
                    released += 1
        return released
