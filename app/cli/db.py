import asyncio
import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import and_, select

from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.database import async_session
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from app.models import ActiveSession, InviteCode, User
from app.models.tenant import Tenant
from app.services.session_cleanup import revoke_sessions_matching

app = typer.Typer(help="Database management commands.")


@app.command()
def create_admin(
    email: Annotated[
        str, typer.Option(help="Admin email address.")
    ] = "admin@example.com",
    password: Annotated[
        str | None,
        typer.Option(
            help="Admin password.",
            prompt=True,
            hide_input=True,
            envvar="ADMIN_PASSWORD",
        ),
    ] = None,
    full_name: Annotated[str, typer.Option(help="Admin full name.")] = "Test Admin",
) -> None:
    """Create a test admin user if not exists."""

    async def _run() -> None:
        tenant_id = settings.mvp_tenant_id
        if not isinstance(tenant_id, UUID):
            raise ValueError("Admin creation requires a configured tenant UUID")
        # Bind before session entry: the first transaction and post-commit refresh
        # must both receive the configured owner through the RLS listener.
        tenant_token = tenant_id_ctx.set(str(tenant_id))
        bypass_token = bypass_rls_ctx.set(False)
        try:
            async with async_session() as db:
                tenant = await db.execute(
                    select(Tenant.id).where(
                        Tenant.id == tenant_id, Tenant.is_active.is_(True)
                    )
                )
                if tenant.scalar_one_or_none() != tenant_id:
                    raise ValueError("Configured tenant must exist and be active")
                result = await db.execute(
                    select(User)
                    .where(User.email == email, User.tenant_id == tenant_id)
                    .with_for_update()
                )
                existing = result.scalar_one_or_none()

                if existing:
                    if existing.tenant_id != tenant_id:
                        raise ValueError(
                            "Admin account tenant does not match configured tenant"
                        )
                    if not password:
                        typer.secho(
                            "Error: Password required for reset.", fg=typer.colors.RED
                        )
                        raise typer.Exit(1)
                    existing.hashed_password = await get_password_hash(password)
                    existing.mfa_epoch = int(existing.mfa_epoch or 0) + 1
                    revoked_sessions = await revoke_sessions_matching(
                        db=db,
                        whereclause=and_(
                            ActiveSession.user_id == existing.id,
                            ActiveSession.revoked_at.is_(None),
                        ),
                        lock_rows=True,
                    )
                    await db.commit()
                    typer.echo(
                        f"Admin user already exists with ID: {existing.id}. Password reset. "
                        f"Revoked {revoked_sessions} active session(s)."
                    )
                    return

                from app.models.users import UserProfile

                if not password:
                    typer.secho(
                        "Error: Password required for new account.", fg=typer.colors.RED
                    )
                    raise typer.Exit(1)
                # AUD-360: an operator-created account belongs to the configured MVP
                # tenant; an unowned row would be invisible to every tenant session.
                admin = User(
                    email=email,
                    tenant_id=tenant_id,
                    hashed_password=await get_password_hash(password),
                    profile=UserProfile(full_name=full_name, status="active"),
                    role="admin",
                    is_active=True,
                    mfa_required=False,
                )
                db.add(admin)
                await db.commit()
                await db.refresh(admin)
                typer.echo(f"Created admin user: {email} (ID: {admin.id})")
        finally:
            bypass_rls_ctx.reset(bypass_token)
            tenant_id_ctx.reset(tenant_token)

    asyncio.run(_run())


@app.command()
def create_invite(
    role: Annotated[str, typer.Argument(help="Role for the invite (teacher/admin).")],
) -> None:
    """Generate a new invite code."""
    if role not in ("teacher", "admin"):
        typer.secho(
            "Error: Only 'teacher' or 'admin' roles are supported.", fg=typer.colors.RED
        )
        raise typer.Exit(1)

    async def _run() -> None:
        code = secrets.token_hex(5).upper()
        async with async_session() as session:
            invite = InviteCode(
                code=code, role=role, is_active=True, created_at=datetime.now(UTC)
            )
            session.add(invite)
            await session.commit()
            typer.echo(f"Invite code for {role}: {code}")

    asyncio.run(_run())
