"""Database session event listeners for Row Level Security (RLS) context."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.tenant import get_bypass_rls, get_current_tenant


def register_tenant_listeners() -> None:
    """Register SQLAlchemy session listeners for PostgreSQL RLS context."""
    if not event.contains(Session, "after_begin", set_pg_tenant_context):
        event.listen(Session, "after_begin", set_pg_tenant_context)


def set_pg_tenant_context(session: Any, transaction: Any, connection: Any) -> None:
    """Set transaction-local PostgreSQL GUC variables for Row Level Security (RLS)."""
    if connection.dialect.name != "postgresql":
        return

    if get_bypass_rls():
        connection.execute(
            text("SELECT set_config('app.bypass_rls', :bypass_rls, true);"),
            {"bypass_rls": "on"},
        )
        return

    tenant_id = get_current_tenant()
    if tenant_id:
        connection.execute(
            text("SELECT set_config('app.current_tenant', :tenant_id, true);"),
            {"tenant_id": str(tenant_id)},
        )
    else:
        connection.execute(text("SELECT set_config('app.current_tenant', '', true);"))
        connection.execute(text("SELECT set_config('app.bypass_rls', '', true);"))
