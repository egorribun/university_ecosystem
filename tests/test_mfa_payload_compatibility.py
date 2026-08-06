"""Backward/forward compatibility for the evolved MFA challenge payload."""

from __future__ import annotations

import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models.auth import ChallengeState
from app.schemas.schemas import MfaChallengeOut

_MIGRATION_SPEC = spec_from_file_location(
    "mfa_challenge_state_migration",
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "202603130001_add_mfa_challenge_state_enum.py",
)
if _MIGRATION_SPEC is None or _MIGRATION_SPEC.loader is None:
    raise RuntimeError("Could not load MFA challenge state migration")
_MFA_MIGRATION = module_from_spec(_MIGRATION_SPEC)
sys.modules[_MIGRATION_SPEC.name] = _MFA_MIGRATION
_MIGRATION_SPEC.loader.exec_module(_MFA_MIGRATION)


_BASE_PAYLOAD = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "550e8400-e29b-41d4-a716-446655440001",
    "session_id": None,
    "challenge_type": "totp",
    "token": "challenge-token",
    "expires_at": "2026-07-23T12:00:00Z",
    "consumed_at": None,
    "created_at": "2026-07-23T11:00:00Z",
    "payload": {"method": "totp"},
    "attempt_count": 0,
}


def test_pre_state_payload_deserializes_with_compatibility_default() -> None:
    """Payloads persisted before TD-W5-01 remain readable after the migration."""
    old_shape = json.loads(json.dumps(_BASE_PAYLOAD))

    parsed = MfaChallengeOut.model_validate(old_shape)

    assert parsed.state is ChallengeState.PENDING
    assert parsed.challenge_type == "totp"
    assert parsed.model_dump(mode="json")["state"] == "pending"


def test_current_payload_round_trips_every_historic_enum_value() -> None:
    """The current DTO accepts every value declared by the enum migration."""
    for state in ChallengeState:
        payload = {**_BASE_PAYLOAD, "state": state.value}

        parsed = MfaChallengeOut.model_validate(payload)
        round_tripped = json.loads(parsed.model_dump_json())

        assert parsed.state is state
        assert round_tripped["state"] == state.value


def test_migration_enum_and_runtime_enum_stay_in_lockstep() -> None:
    """Prevent a future enum migration value from being omitted in Python."""
    migration_values = set(_MFA_MIGRATION._ENUM_VALUES)

    assert {state.value for state in ChallengeState} == migration_values
