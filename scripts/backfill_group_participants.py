"""Backfill SpiceDB group participant relations for the configured MVP tenant.

Writes ``group:{group_id}#participant@user:{user_id}`` for every user whose
``group_id`` is set. Every update is a TOUCH, so the script is idempotent:
rerunning it converges to the same relationships.

Rows are read in ``User.id`` order, one page of ``--batch-size`` at a time, and
written through the shared ``apply_pages`` helper from
``scripts.backfill_event_relationships``. Reads run under the MVP tenant context
(``tenant_id_ctx``) so RLS stays enforced; the RLS bypass is never enabled.

Usage: ``python -m scripts.backfill_group_participants [--batch-size N]``
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from authzed.api.v1 import RelationshipUpdate
from sqlalchemy import select

from app.auth.relationships import (
    EventRelationshipWriter,
    build_group_participant_update,
)
from app.core.config import settings
from app.core.database import async_session, init_database
from app.core.spicedb import (
    acquire_shared_spicedb_channel,
    close_global_spicedb_channel,
)
from app.core.tenant import bypass_rls_ctx, require_mvp_tenant, tenant_id_ctx
from app.models import User
from scripts.backfill_event_relationships import DEFAULT_BATCH_SIZE, apply_pages


async def _fetch_group_participant_page(
    after: UUID | None, limit: int
) -> list[tuple[UUID, list[RelationshipUpdate]]]:
    stmt = select(User.id, User.group_id).where(User.group_id.is_not(None))
    if after is not None:
        stmt = stmt.where(User.id > after)
    async with async_session() as db:
        rows = (await db.execute(stmt.order_by(User.id).limit(limit))).all()
    return [
        (
            user_id,
            [
                build_group_participant_update(
                    operation="touch", group_id=group_id, user_id=user_id
                )
            ],
        )
        for user_id, group_id in rows
        if group_id is not None
    ]


async def run_group_backfill(*, batch_size: int) -> int:
    """Backfill group participants for the MVP tenant; return rows processed."""
    tenant = settings.mvp_tenant_id
    if not isinstance(tenant, UUID):
        raise RuntimeError(
            "MVP_TENANT_ID must be configured to backfill group participants"
        )
    init_database()
    tenant_token = tenant_id_ctx.set(str(tenant))
    bypass_token = bypass_rls_ctx.set(False)
    try:
        async with async_session() as db:
            # Fail closed when the configured tenant is missing or inactive.
            await require_mvp_tenant(db)
        writer = EventRelationshipWriter(await acquire_shared_spicedb_channel())
        return await apply_pages(
            _fetch_group_participant_page, writer, batch_size=batch_size
        )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await close_global_spicedb_channel()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()
    processed = asyncio.run(run_group_backfill(batch_size=args.batch_size))
    print(f"Backfilled group participant relations: {processed}")


if __name__ == "__main__":
    main()
