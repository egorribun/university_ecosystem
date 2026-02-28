"""Recovery code generation, verification, and counting."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.auth.security import get_password_hash, verify_password
from app.models.models import RecoveryCode, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def generate_recovery_codes(db: AsyncSession, *, user: User) -> list[str]:
    """Generate a new set of recovery codes for the user.

    Existing codes are invalidated.  All 10 Argon2id hashes are computed
    concurrently in the thread pool (``asyncio.gather``) to avoid ~3 s of
    sequential blocking.
    """
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))

    plain_codes: list[str] = []
    for _ in range(10):
        raw_code = secrets.token_hex(5)
        formatted = f"{raw_code[:5]}-{raw_code[5:]}".upper()
        plain_codes.append(formatted)

    hashed_codes: list[str] = await asyncio.gather(
        *[get_password_hash(code, validate_policy=False) for code in plain_codes]
    )

    for code, hashed in zip(plain_codes, hashed_codes, strict=False):
        db.add(
            RecoveryCode(
                user_id=user.id,
                code_hash=hashed,
                is_used=False,
            )
        )

    await db.flush()
    return plain_codes


async def verify_recovery_code(db: AsyncSession, *, user: User, code: str) -> bool:
    """Verify a recovery code.  If valid, mark it as used."""
    stmt = (
        select(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
        .where(RecoveryCode.is_used.is_(False))
    )
    result = await db.execute(stmt)
    available_codes = result.scalars().all()

    normalized_code = code.strip().upper()

    for record in available_codes:
        if await verify_password(normalized_code, str(record.code_hash)):
            record.is_used = True
            record.used_at = _utcnow()
            await db.flush()
            return True

    return False


async def count_remaining_recovery_codes(db: AsyncSession, *, user: User) -> int:
    stmt = (
        select(func.count())
        .select_from(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
        .where(RecoveryCode.is_used.is_(False))
    )
    return (await db.scalar(stmt)) or 0
