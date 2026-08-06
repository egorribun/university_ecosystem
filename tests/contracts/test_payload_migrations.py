"""Backward/forward contracts for payloads changed by schema migrations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.models.auth import ChallengeState
from app.schemas.schemas import MfaChallengeOut


def _legacy_payload(*, consumed_at: datetime | None = None) -> dict[str, object]:
    return {
        "id": uuid4(),
        "user_id": uuid4(),
        "session_id": None,
        "challenge_type": "totp",
        "token": "legacy-token",
        "expires_at": datetime(2026, 8, 7, tzinfo=UTC),
        "consumed_at": consumed_at,
        "created_at": datetime(2026, 8, 6, tzinfo=UTC),
        "payload": {"method": "totp"},
        "attempt_count": 1,
    }


def test_pre_enum_pending_payload_keeps_pending_state() -> None:
    result = MfaChallengeOut.model_validate(_legacy_payload())

    assert result.state is ChallengeState.PENDING


def test_pre_enum_consumed_payload_recovers_consumed_state() -> None:
    result = MfaChallengeOut.model_validate(
        _legacy_payload(consumed_at=datetime(2026, 8, 6, 12, tzinfo=UTC))
    )

    assert result.state is ChallengeState.CONSUMED


def test_current_enum_payload_round_trips_without_legacy_inference() -> None:
    payload = _legacy_payload()
    payload["state"] = ChallengeState.EXPIRED

    result = MfaChallengeOut.model_validate(payload)
    round_tripped = MfaChallengeOut.model_validate(result.model_dump())

    assert result.state is ChallengeState.EXPIRED
    assert round_tripped.state is ChallengeState.EXPIRED
