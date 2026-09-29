"""Step-up challenge issuance must fail closed when the session epoch is stale."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.localization import translate
from app.services.auth.mfa_coordinator import MfaCoordinator


@pytest.fixture
def coordinator() -> MfaCoordinator:
    return MfaCoordinator(AsyncMock(), AsyncMock())


def _user(**attributes: object) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), **attributes)


async def test_stale_session_epoch_is_rejected_in_the_request_locale(
    coordinator: MfaCoordinator, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = AsyncMock()
    monkeypatch.setattr("app.auth.mfa.start_totp_verification", issue)

    with pytest.raises(HTTPException) as exc:
        await coordinator._collect_mfa_challenges(
            _user(mfa_epoch=5),  # type: ignore[arg-type]
            "ru",
            {"totp": True},
            session=SimpleNamespace(id=uuid4(), mfa_epoch=4),  # type: ignore[arg-type]
            flow="step_up",
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == translate("errors.auth.credentials_invalid", locale="ru")
    assert exc.value.detail != translate("errors.auth.credentials_invalid", locale="en")
    issue.assert_not_awaited()


@pytest.mark.parametrize(
    ("user_attributes", "session_attributes"),
    [
        pytest.param({"mfa_epoch": 4}, {"mfa_epoch": 4}, id="matching-epochs"),
        pytest.param({"mfa_epoch": 0}, {"mfa_epoch": 0}, id="both-zero"),
        pytest.param({"mfa_epoch": None}, {"mfa_epoch": 0}, id="unset-user-epoch"),
        pytest.param({}, {"mfa_epoch": 0}, id="user-without-epoch-attribute"),
        pytest.param({"mfa_epoch": 4}, {}, id="session-without-epoch-attribute"),
    ],
)
async def test_matching_or_absent_epochs_allow_step_up_issuance(
    coordinator: MfaCoordinator,
    user_attributes: dict[str, object],
    session_attributes: dict[str, object],
) -> None:
    methods = await coordinator._collect_mfa_challenges(
        _user(**user_attributes),  # type: ignore[arg-type]
        "en",
        {},
        session=SimpleNamespace(id=uuid4(), **session_attributes),  # type: ignore[arg-type]
        flow="step_up",
    )

    assert methods == []
