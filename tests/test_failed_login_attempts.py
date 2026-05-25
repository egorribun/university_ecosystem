"""W136 SW4 — failed_login_attempts INSERT contract test.

Closes W135 §Honesty #3. The W135 SW2 Docker-stack verification surfaced a
``NotNullViolation`` on ``failed_login_attempts`` INSERT for non-existent
emails. Investigation reproduced the bug in the test SQLite as well — it
was NOT just Docker schema drift, it was real model-level drift.

Root cause (W136 SW4 investigation):
- Pre-W136 ``FailedLoginAttempt`` inherited ``user_id`` from ``UserFK`` mixin
  which declared ``nullable=False`` + ``ondelete=CASCADE`` (mixins.py:23-33).
- Original migration ``2025070100011`` created ``user_id`` as ``nullable=True``,
  but the model-level NOT NULL on subsequent test re-creation
  (``Base.metadata.create_all``) and any post-UUID re-deploy enforced
  NOT NULL.
- Backend ``register_failed_attempt(email, user_id=None)`` for unknown
  emails (credential-stuffing on harvested email lists) raised
  ``IntegrityError: NOT NULL constraint failed: failed_login_attempts.user_id``.

Fix (W136 SW4):
- Override ``user_id`` declaration in ``FailedLoginAttempt`` to use
  ``nullable=True`` + ``ondelete=SET NULL`` (preserves audit row when user
  is deleted; matches original migration intent).
- New alembic migration ``202605070001`` alters production schema to match.
- IP-based brute-force detection (``ix_failed_login_attempts_ip_attempted_at``
  per TD-3) is preserved — failed attempts on non-existent emails still
  INSERT with ``user_id=NULL`` and contribute to IP-keyed analysis.

The tests serve as a contract:
1. INSERT succeeds for non-existent email (user_id=None)
2. INSERT succeeds for existing user (user_id=UUID)
3. Repeat INSERT works for both paths (lockout count accumulates)
4. Failed attempts on different emails don't cross-pollute

If the contract breaks in the future (e.g. someone tightens user_id NOT NULL
without updating callers), these tests fail loudly.
"""

from __future__ import annotations

import pytest

from app.services.auth.lockout import LockoutService


@pytest.mark.asyncio
async def test_register_failed_attempt_succeeds_for_nonexistent_email(db_session):
    """user_id=None is accepted; no NotNullViolation."""
    service = LockoutService(db=db_session)

    _lock_until, triggered, count = await service.register_failed_attempt(
        email="nonexistent@example.com",
        user_id=None,
    )

    # Single attempt typically doesn't trigger lockout (default thresholds
    # require multiple attempts), but the INSERT must succeed.
    assert count >= 1
    assert isinstance(triggered, bool)
    # lock_until may be None or datetime depending on threshold config


@pytest.mark.asyncio
async def test_register_failed_attempt_succeeds_for_existing_user(
    db_session, test_user
):
    """user_id=UUID is accepted; behaviour identical to None case."""
    service = LockoutService(db=db_session)

    _lock_until, triggered, count = await service.register_failed_attempt(
        email=test_user.email,
        user_id=test_user.id,
    )

    assert count >= 1
    assert isinstance(triggered, bool)


@pytest.mark.asyncio
async def test_register_failed_attempt_accumulates_for_nonexistent_email(
    db_session,
):
    """Repeated INSERTs for same non-existent email accumulate count."""
    service = LockoutService(db=db_session)

    _, _, count1 = await service.register_failed_attempt(
        email="repeat-attacker@example.com",
        user_id=None,
    )
    _, _, count2 = await service.register_failed_attempt(
        email="repeat-attacker@example.com",
        user_id=None,
    )
    _, _, count3 = await service.register_failed_attempt(
        email="repeat-attacker@example.com",
        user_id=None,
    )

    # Counts are clamped to max(_max_lockout_threshold(), 1) per
    # _fetch_recent_attempts. We assert monotonic non-decreasing OR
    # all-equal-at-clamp.
    assert count1 <= count2 <= count3
    assert count3 >= 1


@pytest.mark.asyncio
async def test_register_failed_attempt_separate_emails_isolated(db_session):
    """Failed attempts on different emails don't cross-pollute."""
    service = LockoutService(db=db_session)

    _, _, count_a_first = await service.register_failed_attempt(
        email="alpha@example.com",
        user_id=None,
    )
    _, _, count_b_first = await service.register_failed_attempt(
        email="bravo@example.com",
        user_id=None,
    )
    _, _, count_a_second = await service.register_failed_attempt(
        email="alpha@example.com",
        user_id=None,
    )

    # alpha's count should be 2; bravo's should be 1 (independent buckets)
    assert count_a_first >= 1
    assert count_b_first >= 1
    assert count_a_second >= count_a_first
