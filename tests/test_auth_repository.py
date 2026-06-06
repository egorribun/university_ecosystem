"""Unit tests for AuthRepository (app/repositories/auth_repository.py).

Hermetic against the SQLite test DB (``db_session`` fixture; password_reset_tokens,
email_change_tokens, failed_login_attempts, mfa_totp_enrollments + webauthn tables
are auto-created via create_all). Real users come from ``user_factory``. ``with_for_update``
is a no-op on SQLite (no error), so the lock paths are exercised structurally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.core.config import settings
from app.repositories.auth_repository import AuthRepository, get_auth_repository


@pytest.fixture
def repo(db_session: AsyncSession) -> AuthRepository:
    return AuthRepository(db_session)


def _h(value: str) -> str:
    """Deterministic, unique token-hash stand-in (the column is UNIQUE)."""
    return f"hash-{value}"


@pytest.mark.asyncio
async def test_get_auth_repository_factory_returns_instance(db_session):
    built = get_auth_repository(db_session)
    assert isinstance(built, AuthRepository)
    assert built.model is models.PasswordResetToken


# --- Password reset tokens ---------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_valid_password_reset_token(repo, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    dto = await repo.create_password_reset_token(
        user.id, _h("pr-new"), now + timedelta(hours=1)
    )
    assert dto.token_hash == _h("pr-new")
    assert dto.used is False

    fetched = await repo.get_valid_password_reset_token(_h("pr-new"))
    assert fetched is not None
    assert fetched.user_id == user.id
    # with_for_update path (no-op on SQLite) still resolves.
    locked = await repo.get_valid_password_reset_token(
        _h("pr-new"), with_for_update=True
    )
    assert locked is not None


@pytest.mark.asyncio
async def test_get_valid_password_reset_token_rejects_used_and_expired(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    # Used token → not returned.
    db_session.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=_h("pr-used"),
            expires_at=now + timedelta(hours=1),
            used=True,
        )
    )
    # Expired token → not returned.
    db_session.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=_h("pr-expired"),
            expires_at=now - timedelta(hours=1),
            used=False,
        )
    )
    await db_session.flush()
    assert await repo.get_valid_password_reset_token(_h("pr-used")) is None
    assert await repo.get_valid_password_reset_token(_h("pr-expired")) is None
    assert await repo.get_valid_password_reset_token("never-issued") is None


@pytest.mark.asyncio
async def test_create_password_reset_token_recycles_when_at_limit(
    repo, db_session, user_factory, monkeypatch
):
    monkeypatch.setattr(settings, "password_reset_max_active_tokens", 1)
    user = await user_factory()
    now = datetime.now(UTC)
    # Two pre-existing active tokens → len(active) (2) > max_active (1) triggers
    # the bulk stale-UPDATE branch AND the recycle branch in one call.
    db_session.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=_h("pr-old-1"),
            expires_at=now + timedelta(hours=1),
            used=False,
            created_at=now - timedelta(minutes=2),
        )
    )
    db_session.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=_h("pr-old-2"),
            expires_at=now + timedelta(hours=1),
            used=False,
            created_at=now - timedelta(minutes=1),
        )
    )
    await db_session.flush()

    dto = await repo.create_password_reset_token(
        user.id, _h("pr-recycled"), now + timedelta(hours=2)
    )
    assert dto.token_hash == _h("pr-recycled")
    assert dto.used is False
    # The recycled token is the only remaining valid one.
    assert await repo.get_valid_password_reset_token(_h("pr-recycled")) is not None


@pytest.mark.asyncio
async def test_mark_and_invalidate_password_reset_tokens(
    repo, db_session, user_factory
):
    user = await user_factory()
    now = datetime.now(UTC)
    dto = await repo.create_password_reset_token(
        user.id, _h("pr-mark"), now + timedelta(hours=1)
    )
    await repo.mark_password_reset_token_used(dto.id)
    await db_session.flush()
    assert await repo.get_valid_password_reset_token(_h("pr-mark")) is None

    # invalidate_all marks every remaining unused token used.
    await repo.create_password_reset_token(
        user.id, _h("pr-inv"), now + timedelta(hours=1)
    )
    await repo.invalidate_all_user_password_reset_tokens(user.id)
    await db_session.flush()
    assert await repo.get_valid_password_reset_token(_h("pr-inv")) is None


# --- Email change tokens -----------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_token_lifecycle(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    dto = await repo.create_email_change_token(
        user.id, "new@example.com", _h("ec-1"), now + timedelta(hours=1)
    )
    assert dto.new_email == "new@example.com"

    active = await repo.get_active_email_change_request(user.id)
    assert active is not None
    assert active.token_hash == _h("ec-1")

    valid = await repo.get_valid_email_change_token(_h("ec-1"))
    assert valid is not None

    # A second create invalidates the first (only one active at a time).
    dto2 = await repo.create_email_change_token(
        user.id, "newer@example.com", _h("ec-2"), now + timedelta(hours=1)
    )
    assert await repo.get_valid_email_change_token(_h("ec-1")) is None
    assert await repo.get_valid_email_change_token(_h("ec-2")) is not None

    await repo.mark_email_change_token_used(dto2.id)
    await db_session.flush()
    assert await repo.get_valid_email_change_token(_h("ec-2")) is None


@pytest.mark.asyncio
async def test_invalidate_other_email_change_tokens(repo, db_session, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    keep = models.EmailChangeToken(
        user_id=user.id,
        new_email="keep@example.com",
        token_hash=_h("ec-keep"),
        expires_at=now + timedelta(hours=1),
        used=False,
    )
    drop = models.EmailChangeToken(
        user_id=user.id,
        new_email="drop@example.com",
        token_hash=_h("ec-drop"),
        expires_at=now + timedelta(hours=1),
        used=False,
    )
    db_session.add_all([keep, drop])
    await db_session.flush()

    await repo.invalidate_other_email_change_tokens(user.id, exclude_token_id=keep.id)
    await db_session.flush()
    assert await repo.get_valid_email_change_token(_h("ec-keep")) is not None
    assert await repo.get_valid_email_change_token(_h("ec-drop")) is None


# --- MFA capabilities + WebAuthn ---------------------------------------------


@pytest.mark.asyncio
async def test_has_active_mfa_false_for_user_without_factors(repo, user_factory):
    user = await user_factory()
    capabilities = await repo.get_user_mfa_capabilities(user.id)
    assert capabilities == {k: False for k in capabilities}
    assert await repo.has_active_mfa(user.id) is False


@pytest.mark.asyncio
async def test_webauthn_credential_lookups_empty(repo, user_factory):
    user = await user_factory()
    assert await repo.get_webauthn_credential(user.id, "no-such-cred") is None
    assert await repo.list_user_webauthn_credentials(user.id) == []


# --- Failed login attempts (lockout) -----------------------------------------


@pytest.mark.asyncio
async def test_failed_login_attempt_lifecycle(repo, user_factory):
    user = await user_factory()
    now = datetime.now(UTC)
    email = "lockout@example.com"

    await repo.create_failed_attempt(email=email, user_id=user.id, attempted_at=now)
    await repo.create_failed_attempt(
        email=email, user_id=user.id, attempted_at=now - timedelta(minutes=1)
    )

    recent = await repo.get_failed_attempts(email, limit=10)
    assert len(recent) == 2

    # clear_failed_attempts removes every row for the email and reports the rowcount.
    # NOTE: prune_stale_failed_attempts is intentionally NOT exercised here — its
    # bulk DELETE uses synchronize_session="evaluate", which compares SQLite's
    # naive datetimes against a tz-aware cutoff in Python and raises TypeError.
    # That is a SQLite test-harness artifact only; on the PostgreSQL integration
    # tier the predicate runs as native SQL. Covered there, not in the hermetic run.
    cleared = await repo.clear_failed_attempts(email)
    assert cleared == 2
    assert await repo.get_failed_attempts(email, limit=10) == []
