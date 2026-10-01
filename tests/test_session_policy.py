"""One session policy for REST, GraphQL and the Python WebSocket fallback."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.ws import auth as ws_auth
from app.services.auth.graphql_token_validator import GraphQLTokenValidator
from app.services.auth.session_policy import (
    session_epoch_is_current,
    session_is_expired,
    session_is_usable,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _session(**overrides):
    user_id = overrides.pop("user_id", uuid.uuid4())
    values = {
        "user_id": user_id,
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "revoked_at": None,
        "mfa_epoch": 3,
        "fingerprint_hash": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(session, **overrides):
    values = {"id": session.user_id, "mfa_epoch": 3, "is_active": True}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_epoch_matches_only_when_equal():
    session = _session()
    assert session_epoch_is_current(session, _user(session))
    assert not session_epoch_is_current(session, _user(session, mfa_epoch=4))


def test_missing_epochs_are_treated_as_zero():
    session = _session(mfa_epoch=None)
    assert session_epoch_is_current(session, _user(session, mfa_epoch=None))
    assert session_epoch_is_current(session, _user(session, mfa_epoch=0))


def test_expiry_handles_naive_and_aware_datetimes():
    assert session_is_expired(_session(expires_at=datetime(2026, 1, 1)), NOW)
    assert not session_is_expired(
        _session(expires_at=datetime(2027, 1, 1, tzinfo=UTC)), NOW
    )


def test_expiry_defaults_to_current_time():
    assert session_is_expired(_session(expires_at=datetime(2000, 1, 1, tzinfo=UTC)))


def test_usable_session_passes():
    session = _session()
    assert session_is_usable(session, _user(session))


@pytest.mark.parametrize(
    "mutation",
    [
        {"revoked_at": NOW},
        {"expires_at": datetime(2000, 1, 1, tzinfo=UTC)},
    ],
)
def test_revoked_or_expired_session_is_rejected(mutation):
    session = _session(**mutation)
    assert not session_is_usable(session, _user(session))


def test_foreign_session_is_rejected():
    session = _session()
    assert not session_is_usable(session, _user(session, id=uuid.uuid4()))


def test_stale_mfa_epoch_is_rejected():
    session = _session(mfa_epoch=1)
    assert not session_is_usable(session, _user(session, mfa_epoch=2))


# --- GraphQL ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_graphql_validator_rejects_stale_mfa_epoch():
    session = _session(mfa_epoch=1)
    user = _user(session, mfa_epoch=2)
    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=session)
    validator._load_user = AsyncMock(return_value=user)
    validator._check_fingerprint = AsyncMock(return_value=True)

    assert await validator.validate(str(user.id), "jti") is None
    validator._check_fingerprint.assert_not_awaited()


@pytest.mark.asyncio
async def test_graphql_validator_accepts_current_mfa_epoch():
    session = _session()
    user = _user(session)
    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=session)
    validator._load_user = AsyncMock(return_value=user)
    validator._check_fingerprint = AsyncMock(return_value=True)

    assert await validator.validate(str(user.id), "jti") is user


# --- WebSocket fallback -----------------------------------------------------


def _patched_ws_db(user, session):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    user_repo = MagicMock(get=AsyncMock(return_value=user))
    session_repo = MagicMock(get_by_jti=AsyncMock(return_value=session))
    return (
        patch.object(ws_auth, "async_session", return_value=db),
        patch.object(ws_auth, "UserRepository", return_value=user_repo),
        patch.object(ws_auth, "SessionRepository", return_value=session_repo),
        patch.object(
            ws_auth,
            "get_revocation_redis_client",
            AsyncMock(return_value=MagicMock(exists=AsyncMock(return_value=0))),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_epoch", "expected_user"),
    [(3, True), (2, False)],
)
async def test_ws_ticket_resolution_honours_mfa_epoch(session_epoch, expected_user):
    session = _session(mfa_epoch=session_epoch)
    user = _user(session)
    patches = _patched_ws_db(user, session)
    with patches[0], patches[1], patches[2], patches[3]:
        resolved, jti = await ws_auth._resolve_user_from_ids(str(user.id), "jti-1")

    assert (resolved is user) is expected_user
    assert (jti == "jti-1") is expected_user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_epoch", "expected_user"),
    [(3, True), (2, False)],
)
async def test_ws_token_resolution_honours_mfa_epoch(session_epoch, expected_user):
    session = _session(mfa_epoch=session_epoch)
    user = _user(session)
    patches = _patched_ws_db(user, session)
    payload = {"sub": str(user.id), "jti": "jti-2"}
    with (
        patch("app.auth.security.decode_token", return_value=payload),
        patches[0],
        patches[1],
        patches[2],
        patches[3],
    ):
        resolved, jti = await ws_auth.get_user_from_token("token")

    assert (resolved is user) is expected_user
    assert (jti == "jti-2") is expected_user


# --- Unknown-account login pays the same Argon2 cost -------------------------


@pytest.mark.asyncio
async def test_verify_dummy_password_runs_one_argon2_verification():
    from app.auth import security

    security._dummy_password_hash = None
    await security.verify_dummy_password("whatever")
    first_hash = security._dummy_password_hash
    assert first_hash is not None and first_hash.startswith("$argon2")

    # The throw-away hash is reused, never regenerated per request.
    await security.verify_dummy_password("another")
    assert security._dummy_password_hash == first_hash
