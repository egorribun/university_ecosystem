"""Read-only preflight tooling for legacy bcrypt password hashes.

Bcrypt hashes cannot be converted to Argon2id without the user's plaintext
password.  Authentication deliberately rejects bcrypt (the sole supported
algorithm is Argon2id), so this command only inventories the remaining legacy
rows and provides a fail-closed assertion for deployment gates.  It never
mutates user records, fabricates a reset flag, or prints account PII.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import typer
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.tenant import bypass_rls_ctx, set_bypass_rls
from app.models.users import User

app = typer.Typer(
    help="Read-only bcrypt inventory and migration-completion assertions.",
    no_args_is_help=True,
)

# Bcrypt hashes start with one of these cost prefixes.  Keep this tuple as the
# single source for both the SQL predicate and the small Python unit helper.
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_INVENTORY_DENIED_MESSAGE = "Legacy inventory authority could not be verified."


class InventoryAccessError(RuntimeError):
    """Global inventory authority could not be established safely."""


def _is_bcrypt(hashed_password: str) -> bool:
    """Return whether a stored hash uses one of the legacy bcrypt prefixes."""

    return hashed_password.startswith(_BCRYPT_PREFIXES)


def _bcrypt_predicate() -> Any:
    """Build the dialect-portable SQL predicate for active bcrypt rows."""

    return and_(
        User.is_active.is_(True),
        or_(*(User.hashed_password.like(f"{prefix}%") for prefix in _BCRYPT_PREFIXES)),
    )


def _is_postgresql(session: AsyncSession) -> bool:
    try:
        return session.get_bind().dialect.name == "postgresql"
    except (SQLAlchemyError, OSError):
        raise InventoryAccessError(_INVENTORY_DENIED_MESSAGE) from None


def _inventory_authority() -> Any:
    """Match the migrated policy's role authority in the inventory statement."""

    return func.coalesce(
        func.pg_catalog.pg_has_role(
            func.current_user(),
            func.pg_catalog.to_regrole("ue_rls_bypass"),
            "MEMBER",
        ),
        False,
    )


@asynccontextmanager
async def _privileged_session() -> AsyncIterator[Any]:
    """Scope the existing tenant listener for a global inventory query.

    The flag suppresses inherited tenant-context propagation; it is not
    database authority. PostgreSQL verifies role membership in the same SQL
    statement as each count or sample. Reset context even on setup failures.
    """

    bypass_token = set_bypass_rls(True)
    try:
        async with async_session() as session:
            yield session
    finally:
        bypass_rls_ctx.reset(bypass_token)


async def _count_bcrypt_users() -> int:
    """Return the number of active users still using a bcrypt hash."""

    async with _privileged_session() as session:
        if _is_postgresql(session):
            try:
                result = await session.execute(
                    select(_inventory_authority(), func.count()).where(
                        _bcrypt_predicate()
                    )
                )
                authorized, count = result.one()
            except (SQLAlchemyError, OSError):
                raise InventoryAccessError(_INVENTORY_DENIED_MESSAGE) from None
            if authorized is not True:
                raise InventoryAccessError(_INVENTORY_DENIED_MESSAGE)
            return int(count)

        result = await session.execute(select(func.count()).where(_bcrypt_predicate()))
        return int(result.scalar_one())


async def _report_bcrypt_users(
    limit: int = 50, *, show_ids: bool = False
) -> list[dict[str, str]]:
    """Return an optional, bounded sample of opaque IDs.

    The default is deliberately count-only.  ``show_ids`` is an explicit
    operator opt-in and selects only UUIDs (never email addresses or hashes).
    """

    if limit < 0:
        raise ValueError("limit must be zero or positive")
    if limit == 0 or not show_ids:
        return []

    async with _privileged_session() as session:
        if _is_postgresql(session):
            authority = select(_inventory_authority().label("authorized")).subquery()
            sample = (
                select(User.id.label("user_id"))
                .where(_bcrypt_predicate())
                .order_by(User.id)
                .limit(limit)
                .subquery()
            )
            try:
                result = await session.execute(
                    select(authority.c.authorized, sample.c.user_id)
                    .select_from(authority.outerjoin(sample, true()))
                    .order_by(sample.c.user_id)
                )
                rows = result.all()
            except (SQLAlchemyError, OSError):
                raise InventoryAccessError(_INVENTORY_DENIED_MESSAGE) from None
            if not rows or any(authorized is not True for authorized, _ in rows):
                raise InventoryAccessError(_INVENTORY_DENIED_MESSAGE)
            return [{"id": str(user_id)} for _, user_id in rows if user_id is not None]

        result = await session.execute(
            select(User.id).where(_bcrypt_predicate()).order_by(User.id).limit(limit)
        )
        return [{"id": str(user_id)} for user_id in result.scalars().all()]


@app.command()
def report(
    limit: Annotated[int, typer.Option(help="Max opaque IDs to list.")] = 20,
    show_ids: Annotated[
        bool,
        typer.Option(
            "--show-ids",
            help="Explicitly print a bounded sample of opaque user IDs.",
        ),
    ] = False,
) -> None:
    """Show the active legacy bcrypt count without mutating the database."""

    if limit < 0:
        raise typer.BadParameter("must be zero or positive", param_hint="--limit")

    async def _run() -> None:
        count = await _count_bcrypt_users()
        typer.echo(f"Legacy bcrypt accounts remaining: {count}")

        if count == 0:
            typer.echo(
                "No active legacy bcrypt accounts are currently reported; "
                "no records were changed."
            )
            return

        if show_ids and limit > 0:
            sample = await _report_bcrypt_users(limit=limit, show_ids=True)
            typer.echo(f"\nOpaque ID sample (first {limit}):")
            for entry in sample:
                typer.echo(f"  {entry['id']}")
        typer.echo(
            "\nNo records were changed. Resolve legacy accounts through the "
            "public password reset flow before asserting completion."
        )

    import asyncio

    try:
        asyncio.run(_run())
    except InventoryAccessError:
        typer.echo(_INVENTORY_DENIED_MESSAGE)
        raise typer.Exit(2) from None


@app.command(name="assert-none")
def assert_none() -> None:
    """Exit 1 while any active legacy bcrypt account remains."""

    async def _run() -> None:
        count = await _count_bcrypt_users()
        if count:
            typer.echo(f"Legacy bcrypt accounts remain: {count}")
            raise typer.Exit(1)
        typer.echo("No active legacy bcrypt accounts found.")

    import asyncio

    try:
        asyncio.run(_run())
    except InventoryAccessError:
        typer.echo(_INVENTORY_DENIED_MESSAGE)
        raise typer.Exit(2) from None
