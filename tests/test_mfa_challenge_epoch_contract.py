"""MFA challenges issued before an account epoch rotation must be rejected."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth.constants import CHALLENGE_TYPE_TOTP_VERIFY, MFA_METHOD_TOTP
from app.auth.mfa.challenge import (
    _challenge_epoch_matches_user,
    consume_challenge,
    issue_challenge,
)
from app.core.localization import translate
from app.models import ChallengeState


@pytest.mark.parametrize(
    ("payload", "user_attributes", "expected"),
    [
        pytest.param({"mfa_epoch": 3}, {"mfa_epoch": 3}, True, id="matching"),
        pytest.param({"mfa_epoch": 3}, {"mfa_epoch": 4}, False, id="stale"),
        pytest.param({"mfa_epoch": 0}, {"mfa_epoch": 0}, True, id="both-zero"),
        pytest.param({"mfa_epoch": 0}, {"mfa_epoch": None}, True, id="unset-epoch"),
        pytest.param({"mfa_epoch": 0}, {}, True, id="user-without-epoch-attribute"),
        pytest.param({"mfa_epoch": 1}, {}, False, id="stale-against-missing-epoch"),
        pytest.param({"mfa_epoch": "abc"}, {"mfa_epoch": 0}, False, id="malformed"),
        pytest.param({}, {"mfa_epoch": 9}, True, id="legacy-challenge-without-marker"),
    ],
)
def test_epoch_marker_is_compared_with_the_current_account_epoch(
    payload: dict[str, object], user_attributes: dict[str, object], expected: bool
) -> None:
    challenge = SimpleNamespace(payload=payload)
    user = SimpleNamespace(**user_attributes)

    assert _challenge_epoch_matches_user(challenge, user) is expected  # type: ignore[arg-type]


async def test_consume_reports_a_stale_challenge_in_the_request_locale(
    db_session, user_factory
) -> None:
    user = await user_factory(email="stale-epoch-locale@example.com", mfa_epoch=2)
    issued = await issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        flow="login",
        session_identifier="stale-epoch-locale",
        client_fingerprint="e" * 64,
        method=MFA_METHOD_TOTP,
        payload={"mfa_epoch": 1},
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await consume_challenge(
            db_session,
            challenge_token=issued.challenge_token,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
            user_id=user.id,
            provided_code="000000",
            provided_method=MFA_METHOD_TOTP,
            client_fingerprint="e" * 64,
            login_session_identifier="stale-epoch-locale",
            locale="ru",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == translate("errors.mfa.invalid_challenge", locale="ru")
    assert exc.value.detail != translate("errors.mfa.invalid_challenge", locale="en")
    await db_session.refresh(issued.challenge)
    assert issued.challenge.state == ChallengeState.PENDING
    assert issued.challenge.attempt_count == 0
