"""Recovery code generation, verification, and counting."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.auth.security import get_password_hash, verify_password
from app.models.models import RecoveryCode, User
from app.services.audit_service import AuditService, SecurityEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_audit = AuditService()
_MAX_RECOVERY_CODES = 10  # total codes issued per generate_recovery_codes() call


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
    """Verify a recovery code.  If valid, mark it as used.

    P2-W5-13: Iterate all available codes without early exit to avoid a timing
    oracle that would reveal which slot matched.  Argon2id is constant-time per
    call; iterating all N slots makes the total wall time independent of position.

    P2-W5-14: Emit a structured audit event on success so that recovery-code
    usage appears in the security audit trail.
    """
    stmt = (
        select(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
        .where(RecoveryCode.is_used.is_(False))
    )
    result = await db.execute(stmt)
    available_codes = result.scalars().all()

    normalized_code = code.strip().upper()

    matched_record: RecoveryCode | None = None
    for record in available_codes:
        # Always call verify_password for every slot — never break early.
        if await verify_password(normalized_code, str(record.code_hash)):
            # Record the first match; subsequent matches are cryptographically
            # impossible (unique tokens) but we still complete the loop.
            if matched_record is None:
                matched_record = record

    if matched_record is not None:
        matched_record.is_used = True
        matched_record.used_at = _utcnow()
        await db.flush()
        _audit.log(
            SecurityEvent.MFA_RECOVERY_CODE_USED,
            user_id=user.id,
            remaining=len(available_codes) - 1,
        )
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
