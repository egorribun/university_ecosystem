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
- L473, 480-483  WebAuthn response-required + user-not-found guards
- L490, 493, 496, 502-510  WebAuthn payload type-confusion guards routed
                 through the failed-attempt wrap

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
    CHALLENGE_TYPE_WEBAUTHN_AUTH,
    MFA_METHOD_RECOVERY_CODE,
    MFA_METHOD_TOTP,
    MFA_METHOD_WEBAUTHN,
)
from app.auth.mfa.challenge import (
    _extract_attempt_limit,
    _register_failed_attempt,
    consume_challenge,
    get_challenge,
    issue_dummy_challenge,
)
from app.models import MfaChallenge
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
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _result_with_challenge(challenge: SimpleNamespace | None) -> MagicMock:
    """Mimic ``(await db.execute(stmt)).scalars().first()`` chains."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = challenge
    return result


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
    db.commit.assert_awaited_once()


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

    db.commit.assert_awaited_once()


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
    challenge = MfaChallenge(
        user_id=user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
        token=f"s10-list-{uuid.uuid4().hex}",  # pragma: allowlist secret
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db_session.add(challenge)
    await db_session.flush()

    found = await get_challenge(
        db_session,
        token=challenge.token,
        challenge_type=[CHALLENGE_TYPE_TOTP_AUTH, CHALLENGE_TYPE_WEBAUTHN_AUTH],
        user_id=user.id,
    )

    assert found.id == challenge.id


async def test_get_challenge_normalizes_naive_expires_at() -> None:
    """Naive (tz-less) expires_at is coerced to UTC before comparison (L331)."""
    naive_future = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
    challenge = _fake_challenge(expires_at=naive_future)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_with_challenge(challenge))

    found = await get_challenge(
        db, token=challenge.token, challenge_type=CHALLENGE_TYPE_TOTP_AUTH
    )

    assert found is challenge


async def test_get_challenge_rejects_naive_consumed_at() -> None:
    """Naive consumed_at is coerced to UTC and still rejects the challenge (L334)."""
    naive_past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    challenge = _fake_challenge(consumed_at=naive_past)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_with_challenge(challenge))

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
    db.get = AsyncMock(return_value=SimpleNamespace(revoked_at=datetime.now(UTC)))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_infers_totp_and_requires_code(
    patched_get_challenge,
) -> None:
    """TOTP_AUTH type infers MFA_METHOD_TOTP and demands a code (L395-399, 407)."""
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_TOTP_AUTH)
    patched_get_challenge(challenge)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            AsyncMock(),
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_infers_webauthn_and_requires_response(
    patched_get_challenge,
) -> None:
    """WEBAUTHN_AUTH type infers webauthn and demands a response (L400-401, 473)."""
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_WEBAUTHN_AUTH)
    patched_get_challenge(challenge)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            AsyncMock(),
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_WEBAUTHN_AUTH,
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_infers_recovery_and_requires_code(
    patched_get_challenge,
) -> None:
    """RECOVERY_CODE type infers recovery method and demands a code (L402-403, 447-450)."""
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_RECOVERY_CODE)
    patched_get_challenge(challenge)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            AsyncMock(),
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
        )

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# consume_challenge — TOTP branch (L413-415, L428, L442)
# ---------------------------------------------------------------------------


async def test_consume_challenge_totp_user_missing(patched_get_challenge) -> None:
    challenge = _fake_challenge()
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            provided_method=MFA_METHOD_TOTP,
            provided_code="123456",
        )

    assert exc_info.value.status_code == 400


async def test_consume_challenge_totp_invalid_code_registers_failed_attempt(
    patched_get_challenge, failed_attempt_spy
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
    db.get = AsyncMock(return_value=SimpleNamespace(id=challenge.user_id))
    enrollments = MagicMock()
    enrollments.scalars.return_value.all.return_value = [
        SimpleNamespace(secret=""),  # skipped via `continue`
        SimpleNamespace(secret=secret),
    ]
    db.execute = AsyncMock(return_value=enrollments)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_TOTP_AUTH,
            provided_method=MFA_METHOD_TOTP,
            provided_code=wrong_code,
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
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
            provided_method=MFA_METHOD_RECOVERY_CODE,
            provided_code="AAAA-BBBB",
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
    db.get = AsyncMock(return_value=SimpleNamespace(id=challenge.user_id))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
            provided_method=MFA_METHOD_RECOVERY_CODE,
            provided_code="AAAA-BBBB",
        )

    assert exc_info.value.status_code == 400
    failed_attempt_spy.assert_awaited_once()
    assert failed_attempt_spy.await_args.kwargs["method"] == MFA_METHOD_RECOVERY_CODE


async def test_consume_challenge_recovery_success_consumes_challenge(
    patched_get_challenge, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_RECOVERY_CODE)
    patched_get_challenge(challenge)
    monkeypatch.setattr(
        recovery_module, "verify_recovery_code", AsyncMock(return_value=True)
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=challenge.user_id))

    consumed, session = await consume_challenge(
        db,
        challenge_token=challenge.token,
        challenge_type=CHALLENGE_TYPE_RECOVERY_CODE,
        provided_method=MFA_METHOD_RECOVERY_CODE,
        provided_code="AAAA-BBBB",
    )

    assert consumed is challenge
    assert session is None
    assert challenge.consumed_at is not None
    assert challenge.state == ChallengeState.CONSUMED
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# consume_challenge — WebAuthn branch (L480-483, L490, L493, L496, L502-510)
# ---------------------------------------------------------------------------


async def test_consume_challenge_webauthn_user_missing(
    patched_get_challenge,
) -> None:
    challenge = _fake_challenge(challenge_type=CHALLENGE_TYPE_WEBAUTHN_AUTH)
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_WEBAUTHN_AUTH,
            provided_method=MFA_METHOD_WEBAUTHN,
            provided_webauthn_response={"id": "credential"},
        )

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="payload-not-dict"),
        pytest.param({"options": "not-a-dict"}, id="options-not-dict"),
        pytest.param({"options": {"challenge": 123}}, id="challenge-not-string"),
    ],
)
async def test_consume_challenge_webauthn_payload_type_confusion(
    patched_get_challenge,
    failed_attempt_spy,
    payload: dict[str, Any] | None,
) -> None:
    """Each malformed payload shape raises TypeError, lands in the except wrap
    (L502-510) and surfaces as invalid_code after recording a failed attempt."""
    challenge = _fake_challenge(
        challenge_type=CHALLENGE_TYPE_WEBAUTHN_AUTH, payload=payload
    )
    patched_get_challenge(challenge)
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=challenge.user_id))

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db,
            challenge_token=challenge.token,
            challenge_type=CHALLENGE_TYPE_WEBAUTHN_AUTH,
            provided_method=MFA_METHOD_WEBAUTHN,
            provided_webauthn_response={"id": "credential"},
        )

    assert exc_info.value.status_code == 400
    failed_attempt_spy.assert_awaited_once()
    assert failed_attempt_spy.await_args.kwargs["method"] == MFA_METHOD_WEBAUTHN
