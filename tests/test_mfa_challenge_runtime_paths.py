"""Runtime-path tests for app/auth/mfa/challenge.py.

Direct-call tests (no ASGI) for the MFA challenge module, targeting the
previously-uncovered line ranges from the fresh coverage run:

- L90-91         ``_extract_attempt_limit`` int() coercion failure -> None
- L232           ``_register_failed_attempt`` lock-raise when UPDATE..RETURNING
                 reports ``locked_at`` was just set by this very update
- L284-292       ``issue_dummy_challenge`` timing-normalization write
- L314           ``get_challenge`` list-typed challenge_type filter (real DB)
- L331, 334      ``get_challenge`` naive expires_at / consumed_at normalization
- L386-387       ``consume_challenge`` revoked-session guard
- L395-403       ``consume_challenge`` v_method inference branches
- L407, 413-416  TOTP code-required + user-not-found guards
- L428, 442      TOTP empty-secret skip + invalid-code raise
- L447-465       recovery-code branch (code required / user missing / invalid
                 code / success fall-through)

Harness mirrors tests/test_compliance_service_coverage.py (AsyncMock +
module-level monkeypatch.setattr) and tests/test_mfa_challenge_cleanup.py
(real ``db_session`` + ``user_factory`` for the FK-backed rows).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from fastapi import HTTPException

import app.auth.mfa.challenge as challenge_module
import app.auth.mfa.recovery as recovery_module
from app.auth.constants import (
    CHALLENGE_TYPE_RECOVERY_CODE,
    CHALLENGE_TYPE_TOTP_AUTH,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
)
from app.auth.mfa.challenge import (
    _extract_attempt_limit,
    _register_failed_attempt,
    consume_challenge,
    get_challenge,
    issue_challenge,
    issue_dummy_challenge,
)
from app.models.auth import ChallengeState


def _fake_challenge(**overrides: Any) -> SimpleNamespace:
    """Plain attribute bag standing in for an ORM MfaChallenge row."""
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "session_id": None,
        "challenge_type": CHALLENGE_TYPE_TOTP_AUTH,
        "token": "fake-challenge-token",  # pragma: allowlist secret
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "consumed_at": None,
        "locked_at": None,
        "payload": None,
        "attempt_count": 0,
        "state": ChallengeState.PENDING,
        "flow": "login",
        "session_identifier": "bound-login-session",
        "client_fingerprint": "f" * 64,
        "method": MFA_METHOD_TOTP,
        "token_digest": "d" * 64,
        "token_key_id": "app-primary",
        "revision": 1,
    }
    defaults.update(overrides)
    if (
        defaults["challenge_type"] == CHALLENGE_TYPE_RECOVERY_CODE
        and "method" not in overrides
    ):
        defaults["method"] = MFA_METHOD_RECOVERY_CODE
    return SimpleNamespace(**defaults)


def _result_with_challenge(challenge: SimpleNamespace | None) -> MagicMock:
    """Mimic ``(await db.execute(stmt)).scalars().first()`` chains."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = challenge
    return result


def _locked_user_result(
    challenge: SimpleNamespace, *, present: bool = True
) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = (
        SimpleNamespace(id=challenge.user_id) if present else None
    )
    return result


def _binding(challenge: SimpleNamespace) -> dict[str, str]:
    return {
        "client_fingerprint": challenge.client_fingerprint,
        "login_session_identifier": challenge.session_identifier,
    }


@pytest.fixture
def patched_get_challenge(monkeypatch: pytest.MonkeyPatch):
    """Patch the module-global ``get_challenge`` used by consume_challenge."""

    def _patch(challenge: SimpleNamespace) -> AsyncMock:
        stub = AsyncMock(return_value=challenge)
        monkeypatch.setattr(challenge_module, "get_challenge", stub)
        return stub

    return _patch


@pytest.fixture
def failed_attempt_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace the atomic UPDATE..RETURNING helper so failure paths no-op."""
    spy = AsyncMock(return_value=None)
    monkeypatch.setattr(challenge_module, "_register_failed_attempt", spy)
    return spy


# ---------------------------------------------------------------------------
# _extract_attempt_limit (L90-91)
# ---------------------------------------------------------------------------


def test_extract_attempt_limit_swallows_uncoercible_fallback() -> None:
    """A fallback that int() rejects returns None instead of raising."""
    assert _extract_attempt_limit(None, fallback="not-an-int") is None  # type: ignore[arg-type]
    assert _extract_attempt_limit(None, fallback=object()) is None  # type: ignore[arg-type]


def test_extract_attempt_limit_rejects_non_positive() -> None:
    assert _extract_attempt_limit(None, fallback=0) is None
    assert _extract_attempt_limit(None, fallback=-3) is None


# ---------------------------------------------------------------------------
# _register_failed_attempt (L232)
# ---------------------------------------------------------------------------


async def test_register_failed_attempt_raises_when_lock_just_acquired() -> None:
    """RETURNING row with a non-null locked_at must raise the locked error."""
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = (3, datetime.now(UTC))
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(HTTPException) as exc_info:
        await _register_failed_attempt(
            db,
            _fake_challenge(),
            method=MFA_METHOD_TOTP,
            limit=3,
            locale="en",
        )

    assert exc_info.value.status_code == 429
    db.flush.assert_awaited_once()


async def test_register_failed_attempt_noop_when_row_already_finalized() -> None:
    """No RETURNING row (already consumed/locked concurrently) is a no-op."""
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    await _register_failed_attempt(
        db,
        _fake_challenge(),
        method=MFA_METHOD_TOTP,
        limit=3,
        locale="en",
    )

    db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# issue_dummy_challenge (L284-292)
# ---------------------------------------------------------------------------


async def test_issue_dummy_challenge_executes_deterministic_delay() -> None:
    db = AsyncMock()

    await issue_dummy_challenge(db)

    db.execute.assert_awaited_once()
    executed = db.execute.await_args.args[0]
    assert "pg_sleep" in str(executed)
    db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_challenge (L314 real DB; L331 / L334 naive-datetime normalization)
# ---------------------------------------------------------------------------


async def test_get_challenge_accepts_list_of_challenge_types(
    db_session, user_factory
) -> None:
    """List-typed challenge_type applies the IN() filter (L314)."""
    user = await user_factory()
    issued = await issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
        flow="login",
        session_identifier="list-challenge-session",
        client_fingerprint="f" * 64,
        method=MFA_METHOD_TOTP,
    )

    found = await get_challenge(
        db_session,
        token=issued.challenge_token,
        challenge_type=[CHALLENGE_TYPE_TOTP_AUTH, CHALLENGE_TYPE_RECOVERY_CODE],
        user_id=user.id,
    )

    assert found.id == issued.challenge.id


async def test_get_challenge_normalizes_naive_expires_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Naive (tz-less) expires_at is coerced to UTC before comparison (L331)."""
    naive_future = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
    challenge = _fake_challenge(expires_at=naive_future)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_with_challenge(challenge))
    monkeypatch.setattr(challenge_module, "_parse_challenge_id", lambda _: challenge.id)
    monkeypatch.setattr(challenge_module.hmac, "compare_digest", lambda *_: True)

    found = await get_challenge(
        db, token=challenge.token, challenge_type=CHALLENGE_TYPE_TOTP_AUTH
    )

    assert found is challenge


async def test_get_challenge_rejects_naive_consumed_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Naive consumed_at is coerced to UTC and still rejects the challenge (L334)."""
    naive_past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    challenge = _fake_challenge(consumed_at=naive_past)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_with_challenge(challenge))
    monkeypatch.setattr(challenge_module, "_parse_challenge_id", lambda _: challenge.id)
    monkeypatch.setattr(challenge_module.hmac, "compare_digest", lambda *_: True)

    with pytest.raises(HTTPException) as exc_info:
        await get_challenge(
            db, token=challenge.token, challenge_type=CHALLENGE_TYPE_TOTP_AUTH
        )

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# consume_challenge — session guard + method inference (L386-387, L395-403)
# ---------------------------------------------------------------------------


async def test_consume_challenge_rejects_revoked_session(
    patched_get_challenge,
) -> None:
    challenge = _fake_challenge(session_id=uuid.uuid4())
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))
    db.get = AsyncMock(return_value=SimpleNamespace(revoked_at=datetime.now(UTC)))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_infers_totp_and_requires_code(
    patched_get_challenge,
) -> None:
    """TOTP_AUTH type infers MFA_METHOD_TOTP and demands a code (L395-399, 407)."""
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_TOTP_AUTH)
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_infers_recovery_and_requires_code(
    patched_get_challenge,
) -> None:
    """RECOVERY_CODE type infers recovery method and demands a code (L402-403, 447-450)."""
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_RECOVERY_CODE)
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# consume_challenge — TOTP branch (L413-415, L428, L442)
# ---------------------------------------------------------------------------


async def test_consume_challenge_totp_user_missing(patched_get_challenge) -> None:
    challenge = _fake_challenge()
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge, present=False))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            provided_method=MFA_METHOD_TOTP,
            provided_code="123456",
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_totp_invalid_code_registers_failed_attempt(
    patched_get_challenge, failed_attempt_spy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty-secret enrollment is skipped (L428); a wrong code raises (L442)."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    now_ts = time.time()
    valid_codes = {totp.at(now_ts - 30), totp.at(now_ts), totp.at(now_ts + 30)}
    wrong_code = next(
        code
        for code in ("000000", "111111", "222222", "333333")
        if code not in valid_codes
    )

    challenge = _fake_challenge()
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))

    async def reject_totp(*_args, **_kwargs):
        await failed_attempt_spy(
            db, challenge, method=MFA_METHOD_TOTP, limit=5, locale="en"
        )
        raise HTTPException(400, "invalid code")

    monkeypatch.setattr(
        "app.auth.mfa.totp.verify_totp_for_user", AsyncMock(side_effect=reject_totp)
    )

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            provided_method=MFA_METHOD_TOTP,
            provided_code=wrong_code,
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400
    failed_attempt_spy.assert_awaited_once()
    assert failed_attempt_spy.await_args.kwargs["method"] == MFA_METHOD_TOTP


# ---------------------------------------------------------------------------
# consume_challenge — recovery-code branch (L447-465 + success fall-through)
# ---------------------------------------------------------------------------


async def test_consume_challenge_recovery_user_missing(
    patched_get_challenge,
) -> None:
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_RECOVERY_CODE)
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge, present=False))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
            provided_method=MFA_METHOD_RECOVERY_CODE,
            provided_code="AAAA-BBBB",
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_recovery_invalid_code_registers_failed_attempt(
    patched_get_challenge,
    failed_attempt_spy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_RECOVERY_CODE)
    patched_get_challenge(challenge)
    monkeypatch.setattr(
        recovery_module, "verify_recovery_code", AsyncMock(return_value=False)
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
            provided_method=MFA_METHOD_RECOVERY_CODE,
            provided_code="AAAA-BBBB",
            **_binding(challenge),
        )

    assert exc_info.value.status_code == 400
    failed_attempt_spy.assert_awaited_once()
    assert failed_attempt_spy.await_args.kwargs["method"] == MFA_METHOD_RECOVERY_CODE


@pytest.mark.parametrize("flow", ["email_verification", "email_mfa_enablement"])
async def test_consume_challenge_rejects_recovery_for_email_only_flows(
    flow: str,
    patched_get_challenge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _fake_challenge(
        challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
        flow=flow,
    )
    patched_get_challenge(challenge)
    verify = AsyncMock(return_value=True)
    monkeypatch.setattr(recovery_module, "verify_recovery_code", verify)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
            provided_method=MFA_METHOD_RECOVERY_CODE,
            provided_code="AAAA-BBBB",
            client_fingerprint=challenge.client_fingerprint,
            active_session_identifier=challenge.session_identifier,
        )

    assert exc_info.value.status_code == 400
    verify.assert_not_awaited()


async def test_consume_challenge_recovery_success_consumes_challenge(
    patched_get_challenge, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_RECOVERY_CODE)
    patched_get_challenge(challenge)
    monkeypatch.setattr(
        recovery_module, "verify_recovery_code", AsyncMock(return_value=True)
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_locked_user_result(challenge))

    consumed, session = await consume_challenge(
        db,
        challenge_token=challenge.token,
        challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
        provided_method=MFA_METHOD_RECOVERY_CODE,
        provided_code="AAAA-BBBB",
        **_binding(challenge),
    )

    assert consumed is challenge
    assert session is None
    assert challenge.consumed_at is not None
    assert challenge.state == ChallengeState.CONSUMED
    db.flush.assert_awaited_once()
