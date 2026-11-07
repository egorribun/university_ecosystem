"""Tenant scope for already owner-verified disposable seed entry points.

This does not authorize a target: callers must first pass seed_target checks.
It deliberately uses the normal application role, never RLS bypass membership.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from app.models.tenant import Tenant
from scripts.seed_identity import owned_seed_tenant_id
from scripts.seed_target import ADMIN_SMOKE_PROJECT


def validate_seed_tenant_configuration(project: str) -> None:
    """Never seed a tenant different from the explicitly configured API scope."""
    expected = owned_seed_tenant_id(project)
    configured = settings.mvp_tenant_id
    if configured is None and project == ADMIN_SMOKE_PROJECT:
        # Legacy smoke may seed while routing remains disabled. This does not
        # enable single-tenant mode or make authentication succeed implicitly.
        return
    if configured != expected:
        raise RuntimeError("MVP_TENANT_ID must match the owned seed project")


@contextmanager
def seed_tenant_context(project: str) -> Iterator[UUID]:
    """Scope all transactions and restore the caller's context even on error."""
    identity = owned_seed_tenant_id(project)
    tenant_token = tenant_id_ctx.set(str(identity))
    bypass_token = bypass_rls_ctx.set(False)
    try:
        yield identity
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


async def ensure_seed_tenant(db: AsyncSession, project: str, identity: UUID) -> None:
    """Create only the reserved tenant; reject collisions rather than adopt data."""
    name = f"Owned seed tenant: {project}"
    existing = await db.scalar(
        select(Tenant).where((Tenant.id == identity) | (Tenant.slug == project))
    )
    if existing is not None:
        if (
            existing.id != identity
            or existing.slug != project
            or existing.name != name
            or existing.domain is not None
            or not existing.is_active
        ):
            raise RuntimeError("reserved seed tenant identity is occupied or drifted")
        return
    db.add(Tenant(id=identity, name=name, slug=project, is_active=True))
    await db.flush()
