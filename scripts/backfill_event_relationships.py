"""Backfill SpiceDB event relations for the configured MVP tenant.

Writes ``event#creator`` for every event that has ``created_by`` and
``event#attendee`` for every attendance row. Every update is a TOUCH, so the
script is idempotent: rerunning it, or running it while the outbox is still
delivering creators, converges to the same relationships.

Rows are read in primary-key order, one page of ``--batch-size`` at a time.
Each page is written in chunks of at most ``WRITE_CHUNK_SIZE`` updates. Reads
run under the MVP tenant context (``tenant_id_ctx``) so RLS stays enforced; the
RLS bypass is never enabled.

Usage: ``python -m scripts.backfill_event_relationships [--batch-size N]``
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Final
from uuid import UUID

from authzed.api.v1 import RelationshipUpdate
from sqlalchemy import select

from app.auth.relationships import (
    ATTENDEE_RELATION,
    CREATOR_RELATION,
    EventRelationshipWriter,
    build_event_relationship_update,
)
from app.core.config import settings
from app.core.database import async_session, init_database
from app.core.spicedb import (
    acquire_shared_spicedb_channel,
    close_global_spicedb_channel,
)
from app.core.tenant import bypass_rls_ctx, require_mvp_tenant, tenant_id_ctx
from app.models import Event, EventAttendance

DEFAULT_BATCH_SIZE: Final = 500
# SpiceDB caps the number of updates per WriteRelationships request; keep well below.
WRITE_CHUNK_SIZE: Final = 100

# A page yields (row primary key, updates for that row) pairs in key order.
PageFetcher = Callable[
    [UUID | None, int],
    Awaitable[list[tuple[UUID, list[RelationshipUpdate]]]],
]


async def _fetch_creator_page(
    after: UUID | None, limit: int
) -> list[tuple[UUID, list[RelationshipUpdate]]]:
    stmt = select(Event.id, Event.created_by).where(Event.created_by.is_not(None))
    if after is not None:
        stmt = stmt.where(Event.id > after)
    async with async_session() as db:
        rows = (await db.execute(stmt.order_by(Event.id).limit(limit))).all()
    return [
        (
            event_id,
            [
                build_event_relationship_update(
                    operation="touch",
                    relation=CREATOR_RELATION,
                    event_id=event_id,
                    user_id=created_by,
                )
            ],
        )
        for event_id, created_by in rows
        if created_by is not None
    ]


async def _fetch_attendee_page(
    after: UUID | None, limit: int
) -> list[tuple[UUID, list[RelationshipUpdate]]]:
    stmt = select(EventAttendance.id, EventAttendance.event_id, EventAttendance.user_id)
    if after is not None:
        stmt = stmt.where(EventAttendance.id > after)
    async with async_session() as db:
        rows = (await db.execute(stmt.order_by(EventAttendance.id).limit(limit))).all()
    return [
        (
            attendance_id,
            [
                build_event_relationship_update(
                    operation="touch",
                    relation=ATTENDEE_RELATION,
                    event_id=event_id,
                    user_id=user_id,
                )
            ],
        )
        for attendance_id, event_id, user_id in rows
    ]


async def _write_chunks(
    writer: EventRelationshipWriter, updates: Sequence[RelationshipUpdate]
) -> None:
    for start in range(0, len(updates), WRITE_CHUNK_SIZE):
        await writer.write(updates[start : start + WRITE_CHUNK_SIZE])


async def apply_pages(
    fetch_page: PageFetcher,
    writer: EventRelationshipWriter,
    *,
    batch_size: int,
) -> int:
    """Walk every page in key order and TOUCH its relations; return rows processed."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    processed = 0
    after: UUID | None = None
    while True:
        page = await fetch_page(after, batch_size)
        if not page:
            return processed
        updates = [update for _, row_updates in page for update in row_updates]
        await _write_chunks(writer, updates)
        processed += len(page)
        after = page[-1][0]
        if len(page) < batch_size:
            return processed


async def run_backfill(*, batch_size: int) -> tuple[int, int]:
    """Backfill creators and attendees for the MVP tenant; return (creators, attendees)."""
    tenant = settings.mvp_tenant_id
    if not isinstance(tenant, UUID):
        raise RuntimeError(
            "MVP_TENANT_ID must be configured to backfill event relations"
        )
    init_database()
    tenant_token = tenant_id_ctx.set(str(tenant))
    bypass_token = bypass_rls_ctx.set(False)
    try:
        async with async_session() as db:
            # Fail closed when the configured tenant is missing or inactive.
            await require_mvp_tenant(db)
        writer = EventRelationshipWriter(await acquire_shared_spicedb_channel())
        creators = await apply_pages(_fetch_creator_page, writer, batch_size=batch_size)
        attendees = await apply_pages(
            _fetch_attendee_page, writer, batch_size=batch_size
        )
        return creators, attendees
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await close_global_spicedb_channel()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()
    creators, attendees = asyncio.run(run_backfill(batch_size=args.batch_size))
    print(f"Backfilled event creator relations: {creators}")
    print(f"Backfilled event attendee relations: {attendees}")


if __name__ == "__main__":
    main()
