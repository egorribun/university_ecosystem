"""Backward/forward compatibility for the evolved MFA challenge payload."""

from __future__ import annotations

import json
import re
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models.auth import ChallengeState
from app.schemas.schemas import MfaChallengeOut

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
    """Keep the baseline's database enum and current runtime enum in lockstep."""
    spec = spec_from_file_location(
        "mvp_baseline_mfa_enum_contract",
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "202611020000_mvp_baseline.py",
    )
    assert spec is not None and spec.loader is not None
    baseline = module_from_spec(spec)
    spec.loader.exec_module(baseline)
    enum_statements = [
        statement
        for statement in baseline._TYPES
        if statement.startswith("CREATE TYPE public.challenge_state_enum AS ENUM (")
    ]
    assert len(enum_statements) == 1
    migration_values = re.findall(r"'([^']*)'", enum_statements[0])
    assert migration_values == ["pending", "consumed", "locked", "expired"]
    assert {state.value for state in ChallengeState} == set(migration_values)
