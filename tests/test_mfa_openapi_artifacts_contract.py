"""Fail-closed contracts for the public email-MFA API artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.main import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_ARTIFACTS = (
    REPOSITORY_ROOT / "tests/contracts/snapshots/api_openapi_v1.json",
    REPOSITORY_ROOT / "frontend/openapi.json",
)
GENERATED_TYPES = REPOSITORY_ROOT / "frontend/src/api/generated/types.gen.ts"
GENERATED_SDK = REPOSITORY_ROOT / "frontend/src/api/generated/sdk.gen.ts"
GENERATED_MSW = REPOSITORY_ROOT / "frontend/src/tests/mocks/generated/handlers.ts"


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_email_mfa_contract(schema: dict[str, Any]) -> None:
    serialized = json.dumps(schema).lower()
    assert "webauthn" not in serialized
    assert "passkey" not in serialized

    paths = schema["paths"]
    assert "/api/v1/auth/mfa/verify" in paths
    assert "/api/v1/auth/mfa/email/resend" in paths
    assert "/api/v1/auth/mfa/email/verification/start" in paths
    assert "/api/v1/auth/mfa/email/enable" in paths
    assert "/api/v1/auth/mfa/email" in paths

    components = schema["components"]["schemas"]
    method_challenge = components["MfaMethodChallengeOut"]
    assert method_challenge["properties"]["method"]["enum"] == [
        "totp",
        "email_otp",
    ]
    for field in (
        "delivery_hint",
        "resend_available_at",
        "attempt_count",
        "attempt_limit",
        "remaining_attempts",
    ):
        assert field in method_challenge["properties"]

    verify = components["MfaVerifyIn"]
    assert verify["properties"]["method"]["enum"] == [
        "totp",
        "email_otp",
        "recovery_code",
    ]
    assert components["EmailOtpResendIn"]["required"] == ["challenge_token"]


def test_live_email_mfa_openapi_contract_is_exact() -> None:
    _assert_email_mfa_contract(app.openapi())


def test_tracked_openapi_artifacts_match_live_email_mfa_contract() -> None:
    live = app.openapi()
    for artifact in OPENAPI_ARTIFACTS:
        tracked = _load_schema(artifact)
        _assert_email_mfa_contract(tracked)
        assert tracked == live, f"{artifact} is stale; regenerate it from app.openapi()"
    assert OPENAPI_ARTIFACTS[0].read_bytes() == OPENAPI_ARTIFACTS[1].read_bytes()


def test_generated_types_sdk_and_msw_have_no_retired_authenticator_surface() -> None:
    for artifact in (GENERATED_TYPES, GENERATED_SDK, GENERATED_MSW):
        generated = artifact.read_text(encoding="utf-8").lower()
        assert "webauthn" not in generated
        assert "passkey" not in generated

    generated_types = GENERATED_TYPES.read_text(encoding="utf-8")
    assert '"totp" | "email_otp"' in generated_types
    assert '"totp" | "email_otp" | "recovery_code"' in generated_types
    assert "delivery_hint" in generated_types
    assert "resend_available_at" in generated_types
    assert "EmailOtpResendIn" in generated_types

    generated_sdk = GENERATED_SDK.read_text(encoding="utf-8")
    assert "resendEmailMfaChallengeApiV1AuthMfaEmailResendPost" in generated_sdk
