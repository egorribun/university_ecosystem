"""Tenant context Management for Multi-Tenancy and Row Level Security (RLS)."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id_ctx", default="")
bypass_rls_ctx: ContextVar[bool] = ContextVar("bypass_rls_ctx", default=False)


def set_current_tenant(tenant_id: str | uuid.UUID | None) -> Token[str]:
    """Set current tenant ID for the asyncio task context."""
    val = str(tenant_id) if tenant_id is not None else ""
    return tenant_id_ctx.set(val)


def get_current_tenant() -> str:
    """Get current tenant ID from the asyncio task context."""
    return tenant_id_ctx.get()


def canonical_tenant_id(value: object) -> str:
    """Validate durable tenant authority without arbitrary string coercion."""
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid tenant identity")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ValueError("Invalid tenant identity") from None


def capture_tenant_id() -> str | None:
    """Snapshot trusted scope only; RLS bypass is never transferable."""
    tenant_id = get_current_tenant()
    return None if tenant_id == "" else canonical_tenant_id(tenant_id)


def set_bypass_rls(bypass: bool) -> Token[bool]:
    """Set RLS bypass flag for super-admin or system tasks."""
    return bypass_rls_ctx.set(bypass)


def get_bypass_rls() -> bool:
    """Get RLS bypass flag from context."""
    return bypass_rls_ctx.get()
