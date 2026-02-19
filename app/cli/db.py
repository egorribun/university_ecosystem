import asyncio
import secrets
from datetime import UTC, datetime
from typing import Annotated

import typer
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.database import async_session, engine
from app.models.models import Base, InviteCode, User

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
):
    """Create a test admin user if not exists."""

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session() as db:
            result = await db.execute(select(User).where(User.email == email))
            existing = result.scalar_one_or_none()

            if existing:
                existing.hashed_password = await get_password_hash(password)
                await db.commit()
                typer.echo(
                    f"Admin user already exists with ID: {existing.id}. Password reset."
                )
                return

            admin = User(
                email=email,
                hashed_password=await get_password_hash(password),
                full_name=full_name,
                role="admin",
                is_active=True,
                mfa_required=False,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            typer.echo(f"Created admin user: {email} (ID: {admin.id})")

    asyncio.run(_run())


@app.command()
def create_invite(
    role: Annotated[str, typer.Argument(help="Role for the invite (teacher/admin).")],
):
    """Generate a new invite code."""
    if role not in ("teacher", "admin"):
        typer.secho(
            "Error: Only 'teacher' or 'admin' roles are supported.", fg=typer.colors.RED
        )
        raise typer.Exit(1)

    async def _run():
        code = secrets.token_hex(5).upper()
        async with async_session() as session:
            invite = InviteCode(
                code=code, role=role, is_active=True, created_at=datetime.now(UTC)
            )
            session.add(invite)
            await session.commit()
            typer.echo(f"Invite code for {role}: {code}")

    asyncio.run(_run())
