from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from sqlalchemy import UniqueConstraint

from app.core.config import Settings
from app.models.cwv import CwvObservation
from app.services.cwv import (
    CwvConfigurationError,
    CwvEnvelopeError,
    CwvOriginError,
    CwvRumBinding,
    GithubActionsOidcVerifier,
    build_observation,
    issue_envelope,
    renew_envelope,
    verify_envelope,
)
from app.services.cwv_retention import cleanup_stale_cwv_observations

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
SECRET = "cwv-signing-secret-with-at-least-32-bytes"  # pragma: allowlist secret
INTERNAL_HMAC_SECRET = (
    "internal-hmac-secret-for-isolated-settings-tests"  # pragma: allowlist secret
)
INVALID_SHORT_SECRET = "short"  # pragma: allowlist secret
TESTER_IDS = ",".join(f"00000000-0000-0000-0000-{index:012d}" for index in range(1, 26))
OIDC_TEST_TOKEN = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjE4OTM0NTYwMDAsImlhdCI6MTg5MzQ1NTcwMCwic3ViIjoidGVzdCJ9."
    "c2lnbmF0dXJl"
)


def _binding(**overrides: object) -> CwvRumBinding:
    values: dict[str, object] = {
        "enabled": True,
        "signing_secret": SECRET,
        "release_sha": SHA,
        "frontend_image_digest": DIGEST,
        "deployment_run_id": 123,
        "deployment_run_attempt": 2,
        "deployment_url": "https://staging.example.edu",
        "allowed_origins": ("https://staging.example.edu",),
        "envelope_ttl_seconds": 300,
    }
    values.update(overrides)
    return CwvRumBinding(**values)


def test_envelope_is_bound_to_release_navigation_and_server_derived_route() -> None:
    token, expires_at = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/news/important?ignored=no",
        device_class="mobile",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW,
        nonce_factory=lambda: "nonce_abcdefghijklmnop",
    )

    claims = verify_envelope(_binding(), token, now=NOW + timedelta(seconds=1))

    assert expires_at == NOW + timedelta(seconds=300)
    assert claims.route_group == "content"
    assert claims.device_class == "mobile"
    assert claims.session_id != "gateway-session-not-stored"
    assert len(claims.session_id) == 32
    assert claims.collector_id != "00000000-0000-0000-0000-000000000001"
    assert len(claims.collector_id) == 32
    assert claims.navigation_id != "nonce_abcdefghijklmnop"
    assert len(claims.navigation_id) == 32
    assert claims.release_sha == SHA
    assert claims.frontend_image_digest == DIGEST
    assert claims.deployment_run_id == 123
    assert claims.deployment_run_attempt == 2


@pytest.mark.parametrize(
    ("binding", "message"),
    [
        (_binding(enabled=False), "disabled"),
        (_binding(signing_secret=INVALID_SHORT_SECRET), "signing secret"),
        (_binding(release_sha="dev"), "release SHA"),
        (_binding(frontend_image_digest="latest"), "image digest"),
        (_binding(deployment_run_id=0), "deployment run"),
        (_binding(allowed_origins=()), "allowed origin"),
    ],
)
def test_binding_fails_closed_when_trust_material_is_incomplete(
    binding: CwvRumBinding, message: str
) -> None:
    with pytest.raises(CwvConfigurationError, match=message):
        issue_envelope(
            binding,
            origin="https://staging.example.edu",
            pathname="/dashboard",
            device_class="desktop",
            collector_principal_id="00000000-0000-0000-0000-000000000001",
            gateway_session_id="gateway-session-not-stored",
            now=NOW,
        )


def test_envelope_rejects_untrusted_origin_unknown_route_and_tampering() -> None:
    with pytest.raises(CwvOriginError):
        issue_envelope(
            _binding(),
            origin="https://evil.example",
            pathname="/dashboard",
            device_class="desktop",
            collector_principal_id="00000000-0000-0000-0000-000000000001",
            gateway_session_id="gateway-session-not-stored",
            now=NOW,
        )
    with pytest.raises(CwvEnvelopeError, match="route"):
        issue_envelope(
            _binding(),
            origin="https://staging.example.edu",
            pathname="/unclassified",
            device_class="desktop",
            collector_principal_id="00000000-0000-0000-0000-000000000001",
            gateway_session_id="gateway-session-not-stored",
            now=NOW,
        )

    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/dashboard",
        device_class="desktop",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW,
    )
    with pytest.raises(CwvEnvelopeError, match="signature"):
        verify_envelope(
            _binding(), token[:-1] + ("A" if token[-1] != "A" else "B"), now=NOW
        )


def test_envelope_rejects_expiry_and_deployment_binding_mismatch() -> None:
    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/settings/security",
        device_class="desktop",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW,
    )
    with pytest.raises(CwvEnvelopeError, match="expired"):
        verify_envelope(_binding(), token, now=NOW + timedelta(seconds=301))
    assert (
        verify_envelope(_binding(), token, now=NOW).route_group
        == "messenger_profile_settings_admin"
    )
    with pytest.raises(CwvEnvelopeError, match="deployment binding"):
        verify_envelope(_binding(deployment_run_attempt=3), token, now=NOW)


@pytest.mark.parametrize(
    ("metric", "value", "unit"),
    [("LCP", 2500.0, "ms"), ("INP", 200.0, "ms"), ("CLS", 0.1, "score")],
)
def test_observation_uses_only_server_derived_identity_and_time(
    metric: str, value: float, unit: str
) -> None:
    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/activity",
        device_class="mobile",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW,
        nonce_factory=lambda: "nonce_abcdefghijklmnop",
    )

    observation = build_observation(
        _binding(),
        token=token,
        origin="https://staging.example.edu",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        metric=metric,
        value=value,
        now=NOW + timedelta(seconds=2),
    )

    assert observation.metric == metric
    assert observation.unit == unit
    assert observation.observed_at == NOW + timedelta(seconds=2)
    assert (
        observation.metric_id
        == hashlib.sha256(f"nonce_abcdefghijklmnop:{metric}".encode()).hexdigest()[:32]
    )
    assert observation.automated is False
    assert observation.final is True
    assert not hasattr(observation, "ip")
    assert not hasattr(observation, "user_agent")


@pytest.mark.parametrize(
    ("metric", "value"),
    [("FCP", 1.0), ("LCP", -1.0), ("INP", 60001.0), ("CLS", 10.1)],
)
def test_observation_rejects_non_certification_metrics_and_invalid_values(
    metric: str, value: float
) -> None:
    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/dashboard",
        device_class="desktop",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW,
    )
    with pytest.raises(CwvEnvelopeError, match="metric"):
        build_observation(
            _binding(),
            token=token,
            origin="https://staging.example.edu",
            collector_principal_id="00000000-0000-0000-0000-000000000001",
            gateway_session_id="gateway-session-not-stored",
            metric=metric,
            value=value,
            now=NOW,
        )


def test_observation_rejects_an_envelope_stolen_from_another_session() -> None:
    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/dashboard",
        device_class="desktop",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="original-gateway-session",
        now=NOW,
    )

    with pytest.raises(CwvEnvelopeError) as error_info:
        build_observation(
            _binding(),
            token=token,
            origin="https://staging.example.edu",
            collector_principal_id="00000000-0000-0000-0000-000000000001",
            gateway_session_id="different-gateway-session",
            metric="LCP",
            value=1000,
            now=NOW,
        )
    assert str(error_info.value) == "CWV envelope session binding is invalid"


def test_expired_envelope_can_be_rotated_without_changing_navigation() -> None:
    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname="/news/important",
        device_class="desktop",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW,
        nonce_factory=lambda: "original_nonce_abcdef",
    )

    rotated, rotated_expiry = renew_envelope(
        _binding(),
        token=token,
        origin="https://staging.example.edu",
        pathname="/news/important",
        device_class="desktop",
        collector_principal_id="00000000-0000-0000-0000-000000000001",
        gateway_session_id="gateway-session-not-stored",
        now=NOW + timedelta(minutes=10),
        nonce_factory=lambda: "rotated_nonce_abcdefg",
    )
    original_claims = verify_envelope(_binding(), token, now=NOW)
    rotated_claims = verify_envelope(
        _binding(), rotated, now=NOW + timedelta(minutes=10)
    )

    assert rotated_expiry == NOW + timedelta(minutes=15)
    assert rotated_claims.navigation_id == original_claims.navigation_id
    assert rotated_claims.session_id == original_claims.session_id
    assert rotated_claims.route_group == original_claims.route_group
    assert rotated_claims.nonce != original_claims.nonce


def test_oidc_verifier_requires_exact_github_main_staging_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signing_key = SimpleNamespace(key=object())
    get_key = Mock(return_value=signing_key)
    decode = Mock(
        return_value={
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "university-cwv-exporter",
            "sub": "repo:acme/university:environment:staging",
            "repository": "acme/university",
            "ref": "refs/heads/main",
            "environment": "staging",
            "event_name": "workflow_dispatch",
            "workflow_ref": (
                "acme/university/.github/workflows/"
                "cwv-field-certification.yml@refs/heads/main"
            ),
            "sha": SHA,
        }
    )
    verifier = GithubActionsOidcVerifier(
        enabled=True,
        repository="acme/university",
        workflow_ref=(
            "acme/university/.github/workflows/"
            "cwv-field-certification.yml@refs/heads/main"
        ),
        subject="repo:acme/university:environment:staging",
    )
    monkeypatch.setattr(verifier._jwks, "get_signing_key_from_jwt", get_key)
    monkeypatch.setattr(jwt, "decode", decode)

    claims = verifier.verify(OIDC_TEST_TOKEN, expected_sha=SHA)

    assert claims["environment"] == "staging"
    decode.assert_called_once_with(
        OIDC_TEST_TOKEN,
        signing_key.key,
        algorithms=["RS256"],
        audience="university-cwv-exporter",
        issuer="https://token.actions.githubusercontent.com",
        options={"require": ["exp", "iat", "sub", "repository", "ref", "sha"]},
    )


def test_oidc_verifier_is_disabled_until_exact_policy_is_configured() -> None:
    with pytest.raises(CwvConfigurationError, match="OIDC"):
        GithubActionsOidcVerifier(
            enabled=False, repository="", workflow_ref="", subject=""
        ).verify("token", expected_sha=SHA)


def test_oidc_verifier_rejects_a_token_from_any_other_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = GithubActionsOidcVerifier(
        enabled=True,
        repository="acme/university",
        workflow_ref=(
            "acme/university/.github/workflows/"
            "cwv-field-certification.yml@refs/heads/main"
        ),
        subject="repo:acme/university:environment:staging",
    )
    monkeypatch.setattr(
        verifier._jwks,
        "get_signing_key_from_jwt",
        Mock(return_value=SimpleNamespace(key=object())),
    )
    monkeypatch.setattr(
        jwt,
        "decode",
        Mock(
            return_value={
                "sub": "repo:acme/university:ref:refs/heads/main",
                "repository": "acme/university",
                "ref": "refs/heads/main",
                "environment": "production",
                "event_name": "workflow_dispatch",
                "workflow_ref": (
                    "acme/university/.github/workflows/"
                    "cwv-field-certification.yml@refs/heads/main"
                ),
                "sha": SHA,
            }
        ),
    )
    with pytest.raises(CwvEnvelopeError, match="claims"):
        verifier.verify(OIDC_TEST_TOKEN, expected_sha=SHA)


def test_oidc_verifier_accepts_github_immutable_staging_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = {
        "sub": "repo:acme@123/university@456:environment:staging",
        "repository": "acme/university",
        "ref": "refs/heads/main",
        "environment": "staging",
        "event_name": "workflow_dispatch",
        "workflow_ref": (
            "acme/university/.github/workflows/"
            "cwv-field-certification.yml@refs/heads/main"
        ),
        "sha": SHA,
    }
    verifier = GithubActionsOidcVerifier(
        enabled=True,
        repository="acme/university",
        workflow_ref=claims["workflow_ref"],
        subject="repo:acme@123/university@456:environment:staging",
    )
    monkeypatch.setattr(
        verifier._jwks,
        "get_signing_key_from_jwt",
        Mock(return_value=SimpleNamespace(key=object())),
    )
    monkeypatch.setattr(jwt, "decode", Mock(return_value=claims))
    assert verifier.verify(OIDC_TEST_TOKEN, expected_sha=SHA) == claims


def test_evidence_model_is_pii_free_and_database_deduplicated() -> None:
    columns = set(CwvObservation.__table__.columns.keys())
    assert {"user_id", "email", "ip", "ip_address", "user_agent"}.isdisjoint(columns)
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in CwvObservation.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("metric_id",) in unique_sets
    assert ("navigation_id", "metric") in unique_sets
    assert ("envelope_nonce", "metric") in unique_sets
    assert (
        "release_sha",
        "deployment_run_id",
        "deployment_run_attempt",
        "collector_id",
        "route_group",
        "metric",
        "sampling_bucket",
    ) in unique_sets


@pytest.mark.asyncio
async def test_cwv_retention_cleanup_deletes_and_commits_expired_rows() -> None:
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=3)

    deleted = await cleanup_stale_cwv_observations(
        db=db,
        now=NOW,
        retention_days=30,
    )

    assert deleted == 3
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_staging_settings_redact_secret_and_reject_partial_oidc_policy() -> None:
    values = {
        "_allow_missing": True,
        "environment": "staging",
        "database_url": "sqlite+aiosqlite:///:memory:",
        "algorithm": "RS256",
        "internal_hmac_secret": INTERNAL_HMAC_SECRET,
        "cwv_rum_enabled": True,
        "cwv_rum_signing_secret": SECRET,
        "cwv_release_sha": SHA,
        "cwv_frontend_image_digest": DIGEST,
        "cwv_deployment_run_id": 123,
        "cwv_deployment_run_attempt": 2,
        "cwv_deployment_url": "https://staging.example.edu",
        "cwv_deployed_at": "2026-08-25T12:00:00Z",
        "cwv_allowed_origins": "https://staging.example.edu",
        "cwv_manual_tester_user_ids": TESTER_IDS,
        "cwv_export_oidc_enabled": True,
        "cwv_export_oidc_repository": "acme/university",
        "cwv_export_oidc_workflow_ref": (
            "acme/university/.github/workflows/"
            "cwv-field-certification.yml@refs/heads/main"
        ),
        "cwv_export_oidc_subject": "repo:acme/university:environment:staging",
    }
    configured = Settings(**values)
    assert SECRET not in repr(configured)
    values["cwv_export_oidc_workflow_ref"] = ""
    with pytest.raises(ValueError, match="OIDC"):
        Settings(**values)


def test_staging_settings_reject_invalid_ttl_origin_and_tester_cohort() -> None:
    base = {
        "_allow_missing": True,
        "environment": "staging",
        "database_url": "sqlite+aiosqlite:///:memory:",
        "algorithm": "RS256",
        "internal_hmac_secret": INTERNAL_HMAC_SECRET,
        "cwv_rum_enabled": True,
        "cwv_rum_signing_secret": SECRET,
        "cwv_release_sha": SHA,
        "cwv_frontend_image_digest": DIGEST,
        "cwv_deployment_run_id": 123,
        "cwv_deployment_run_attempt": 2,
        "cwv_deployment_url": "https://staging.example.edu",
        "cwv_deployed_at": "2026-08-25T12:00:00Z",
        "cwv_allowed_origins": "https://staging.example.edu",
        "cwv_manual_tester_user_ids": TESTER_IDS,
        "cwv_export_oidc_enabled": True,
        "cwv_export_oidc_repository": "acme/university",
        "cwv_export_oidc_workflow_ref": (
            "acme/university/.github/workflows/"
            "cwv-field-certification.yml@refs/heads/main"
        ),
        "cwv_export_oidc_subject": "repo:acme/university:environment:staging",
    }
    with pytest.raises(ValueError, match="TTL"):
        Settings(**{**base, "cwv_envelope_ttl_seconds": 601})
    with pytest.raises(ValueError, match="exact HTTPS origin"):
        Settings(**{**base, "cwv_allowed_origins": "https://staging.example.edu/path"})
    with pytest.raises(ValueError, match="25 to 50"):
        Settings(
            **{
                **base,
                "cwv_manual_tester_user_ids": ("00000000-0000-0000-0000-000000000001"),
            }
        )
