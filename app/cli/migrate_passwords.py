"""Batch bcrypt → Argon2id password migration tooling.

TD-W14-02 / TD-W15-04 (audit 2026-03-23 Wave 15):
Deadline 2026-09-01 — all bcrypt hashes must be migrated before that date.

Background
----------
Bcrypt hashes cannot be re-hashed to Argon2id without the user's plaintext password.
The on-login migration in ``app/auth/security.py:verify_password()`` handles users
who log in — their hash is transparently upgraded on first successful login.

This CLI handles the remaining population: users with bcrypt hashes who have NOT
logged in since the Argon2id migration was deployed.  It has two modes:

1. ``report``  — count and list accounts still on bcrypt (dry-run, no writes)
2. ``force-reset`` — mark bcrypt-hash accounts as "password reset required" so
   users are forced to set a new password on next login (which produces an Argon2id
   hash).  This is the safest path: no plaintext exposure, no data loss.

Usage
-----
    # Dry run — see what would be migrated
    python -m app.cli migrate-passwords report

    # Batch mark accounts for forced reset (500 at a time)
    python -m app.cli migrate-passwords force-reset --batch-size 500

    # Full run without confirmation prompts (for K8s Job use)
    python -m app.cli migrate-passwords force-reset --batch-size 500 --yes
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from sqlalchemy import select, update

from app.core.database import async_session
from app.core.logging import get_logger
from app.models.users import User  # type: ignore[attr-defined]

logger = get_logger(__name__)

app = typer.Typer(
    help="Bcrypt → Argon2id password migration commands.",
    no_args_is_help=True,
)

# Bcrypt hashes start with one of these cost prefixes.
_BCRYPT_PREFIXES = ("$2b$", "$2a$", "$2y$")


def _is_bcrypt(hashed_password: str) -> bool:
    return hashed_password.startswith(_BCRYPT_PREFIXES)


async def _count_bcrypt_users() -> int:
    """Return the number of active users still using a bcrypt hash."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()
        return sum(1 for u in users if _is_bcrypt(u.hashed_password))


async def _report_bcrypt_users(limit: int = 50) -> list[dict[str, str]]:
    """Return up to *limit* active users still using a bcrypt hash."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()
        bcrypt_users = [
            {"id": str(u.id), "email": u.email}
            for u in users
            if _is_bcrypt(u.hashed_password)
        ]
        return bcrypt_users[:limit]


async def _force_reset_batch(batch_size: int) -> tuple[int, int]:
    """Mark up to *batch_size* bcrypt-hash users as requiring password reset.

    Returns (processed, remaining) counts.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.is_active.is_(True)).limit(batch_size)
        )
        users = result.scalars().all()
        bcrypt_batch = [u for u in users if _is_bcrypt(u.hashed_password)]

        if not bcrypt_batch:
            return 0, 0

        user_ids = [u.id for u in bcrypt_batch]
        await session.execute(
            update(User).where(User.id.in_(user_ids)).values(must_reset_password=True)  # type: ignore[arg-type]
        )
        await session.commit()

        processed = len(bcrypt_batch)

    remaining = await _count_bcrypt_users()
    return processed, remaining


@app.command()
def report(
    limit: Annotated[int, typer.Option(help="Max accounts to list.")] = 20,
) -> None:
    """Show accounts still using legacy bcrypt hashes (no writes)."""

    async def _run() -> None:
        count = await _count_bcrypt_users()
        typer.echo(f"Bcrypt accounts remaining: {count}")

        if count == 0:
            typer.echo("Migration complete — all active accounts use Argon2id.")
            return

        sample = await _report_bcrypt_users(limit=limit)
        typer.echo(f"\nSample (first {limit}):")
        for entry in sample:
            typer.echo(f"  {entry['id']}  {entry['email']}")

        if count > limit:
            typer.echo(f"  ... and {count - limit} more")

        typer.echo(
            "\nTo migrate: python -m app.cli migrate-passwords force-reset --batch-size 500"
        )

    asyncio.run(_run())


@app.command(name="force-reset")
def force_reset(
    batch_size: Annotated[
        int, typer.Option(help="Accounts processed per batch.")
    ] = 500,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")
    ] = False,
) -> None:
    """Mark bcrypt-hash accounts as requiring a password reset on next login.

    Safe alternative to re-hashing: users must set a new password, which
    will be hashed with Argon2id automatically.
    """

    async def _run() -> None:
        count = await _count_bcrypt_users()
        if count == 0:
            typer.echo("No bcrypt accounts found — migration already complete.")
            raise typer.Exit(0)

        typer.echo(f"Found {count} active account(s) with bcrypt hashes.")
        if not yes:
            typer.confirm(
                f"Mark up to {batch_size} account(s) as 'must reset password'?",
                abort=True,
            )

        total_processed = 0
        while True:
            processed, remaining = await _force_reset_batch(batch_size)
            if processed == 0:
                break
            total_processed += processed
            typer.echo(
                f"  Batch done: {processed} marked for reset. Remaining: {remaining}"
            )
            if remaining == 0:
                break

        typer.echo(
            f"\nDone. {total_processed} account(s) marked for forced password reset."
        )
        typer.echo(
            "Users will be prompted to set a new (Argon2id) password on next login."
        )

        # Update Prometheus gauge so runbook dashboards reflect new state.
        try:
            from app.core.metrics import record_legacy_bcrypt_user_count

            record_legacy_bcrypt_user_count(0)
        except Exception:  # nosec B110  # noqa: S110  # RZ-22-01-JUSTIFIED: metrics guard — best-effort in CLI context (reviewed TD-27-04)
            pass

    asyncio.run(_run())
