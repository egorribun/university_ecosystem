"""Contract tests for the challenge that ``start_totp_verification`` issues."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.auth.constants import CHALLENGE_TYPE_TOTP_VERIFY, MFA_METHOD_TOTP
from app.auth.mfa import totp as totp_module


@pytest.fixture
def issue(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    issued = AsyncMock(return_value=SimpleNamespace(challenge_token="issued"))
    monkeypatch.setattr(totp_module, "issue_challenge", issued)
    monkeypatch.setattr(totp_module.settings, "mfa_totp_attempt_limit", 7)
    return issued


async def test_challenge_is_bound_to_session_epoch_locale_and_attempt_limit(
    issue: AsyncMock,
) -> None:
    db = object()
    session = SimpleNamespace(id=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=4)
    caller_payload = {"trust_device": True}

    result = await totp_module.start_totp_verification(
        db,  # type: ignore[arg-type]
        user=user,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        locale="ru",
        payload=caller_payload,
        flow="step_up",
        session_identifier="session-identifier",
        client_fingerprint="f" * 64,
    )

    assert result is issue.return_value
    issue.assert_awaited_once_with(
        db,
        user_id=user.id,
        session_id=session.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        locale="ru",
        payload={"trust_device": True, "mfa_epoch": 4},
        attempt_limit=7,
        flow="step_up",
        session_identifier="session-identifier",
        client_fingerprint="f" * 64,
        method=MFA_METHOD_TOTP,
    )
    assert caller_payload == {"trust_device": True}


@pytest.mark.parametrize("epoch", [0, None])
async def test_zero_or_unset_epoch_is_recorded_as_zero_without_a_session(
    issue: AsyncMock, epoch: int | None
) -> None:
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=epoch)

    await totp_module.start_totp_verification(
        object(),  # type: ignore[arg-type]
        user=user,  # type: ignore[arg-type]
        flow="login",
        session_identifier="preauth",
        client_fingerprint="a" * 64,
    )

    kwargs = issue.await_args.kwargs
    assert kwargs["payload"] == {"mfa_epoch": 0}
    assert kwargs["session_id"] is None
    assert kwargs["locale"] is None


async def test_user_without_epoch_attribute_is_recorded_as_zero(
    issue: AsyncMock,
) -> None:
    user = SimpleNamespace(id=uuid.uuid4())

    await totp_module.start_totp_verification(
        object(),  # type: ignore[arg-type]
        user=user,  # type: ignore[arg-type]
        flow="login",
        session_identifier="preauth",
        client_fingerprint="a" * 64,
    )

    assert issue.await_args.kwargs["payload"] == {"mfa_epoch": 0}
