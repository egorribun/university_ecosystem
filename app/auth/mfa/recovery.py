"""Recovery code generation, verification, and counting."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.auth.security import get_password_hash, verify_password
from app.models import RecoveryCode, User
from app.services.audit_service import AuditService, SecurityEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_audit = AuditService()
_MAX_RECOVERY_CODES = 10  # total codes issued per generate_recovery_codes() call


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def generate_recovery_codes(
    db: AsyncSession,
    *,
    user: User,
    fresh_mfa_verified_at: datetime | None = None,
) -> list[str]:
    """Generate a new set of recovery codes for the user.

    Existing codes are invalidated.  All 10 Argon2id hashes are computed
    sequentially to avoid starving the Argon2 semaphore (PERF-W8-01).
    Each code uses 8 bytes of entropy (64 bits, MOD-W8-02).
    """
    # Freshness is session-bound.  The denormalized user timestamp may have
    # been written by a different browser and must never authorize regeneration.
    verified_at = fresh_mfa_verified_at
    now = _utcnow()
    if verified_at is None:
        raise PermissionError("fresh MFA verification required")
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    if verified_at < now - timedelta(minutes=5):
        raise PermissionError("fresh MFA verification required")

    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))

    plain_codes: list[str] = []
    for _ in range(_MAX_RECOVERY_CODES):
        # MOD-W8-02: 8 bytes = 16 hex chars = 64-bit entropy (up from 40-bit / 5 bytes).
        # NIST SP 800-63B recommends ≥ 64 bits for backup authentication codes.
        # Format as 4 groups of 4 for readability: "A3F8-B9C2-1E47-D06A".
        raw_code = secrets.token_hex(8)
        parts = [raw_code[i : i + 4].upper() for i in range(0, 16, 4)]
        formatted = "-".join(parts)
        plain_codes.append(formatted)

    # PERF-W8-01: Hash sequentially instead of with asyncio.gather.
    # On a 2-CPU container the Argon2 semaphore has concurrency=1, so all 10
    # gather tasks would stall on the semaphore anyway — same wall-clock time,
    # but 9 blocked tasks starve concurrent login requests for ~3 seconds.
    # Sequential hashing releases the event loop between each hash operation.
    #
    # RZ-33-01: Hash the NORMALIZED (dash-free, uppercase) form so that
    # verify_recovery_code() can strip dashes before comparing.  The user
    # sees the formatted "A3F8-B9C2-1E47-D06A" form, but the DB stores
    # hash(A3F8B9C21E47D06A).  Both inputs — with or without dashes — are
    # normalized to the same canonical form before verify_password().
    hashed_codes: list[str] = []
    for code in plain_codes:
        canonical = code.replace("-", "")
        hashed_codes.append(await get_password_hash(canonical, validate_policy=False))

    # LOW-W19: strict=True catches any length mismatch between plain_codes and
    # hashed_codes early rather than silently producing fewer DB rows.
    for code, hashed in zip(plain_codes, hashed_codes, strict=True):
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
        .with_for_update(nowait=False)
    )
    result = await db.execute(stmt)
    available_codes = result.scalars().all()

    # LOW-W19: remove dashes so users can paste formatted codes (e.g.
    # "A3F8-B9C2-1E47-D06A") or unformatted codes interchangeably.
    normalized_code = code.strip().upper().replace("-", "")

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
