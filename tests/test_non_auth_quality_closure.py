"""Meaningful branch closure for non-auth quality-foundation services."""

from __future__ import annotations

from collections import UserDict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from app.api import cwv as cwv_api
from app.core.config import Settings
from app.core.config.notifications import NotificationSettings
from app.core.events import MfaEmailDeliveryRequested
from app.services import cwv, event_handlers
from app.services.cwv_retention import cleanup_stale_cwv_observations
from app.services.notifications import delivery
from app.tasks import cleanups

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
SECRET = "cwv-signing-secret-with-at-least-32-bytes"  # pragma: allowlist secret
INTERNAL_HMAC_SECRET = (
    "internal-hmac-secret-for-isolated-settings-tests"  # pragma: allowlist secret
)
TESTER_IDS = [f"00000000-0000-0000-0000-{index:012d}" for index in range(1, 26)]


def _binding(**overrides: object) -> cwv.CwvRumBinding:
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
    return cwv.CwvRumBinding(**values)


def _issue(**overrides: object) -> tuple[str, datetime]:
    values: dict[str, object] = {
        "origin": "https://staging.example.edu",
        "pathname": "/dashboard",
        "device_class": "desktop",
        "collector_principal_id": "collector-one",
        "gateway_session_id": "gateway-session-one",
        "now": NOW,
        "nonce_factory": lambda: "nonce_abcdefghijklmnop",
    }
    values.update(overrides)
    return cwv.issue_envelope(_binding(), **values)


@pytest.mark.parametrize(
    "origin",
    [
        "http://staging.example.edu",
        "https://user@staging.example.edu",
        "https://staging.example.edu/path",
        "https://staging.example.edu?query=yes",
        "https://staging.example.edu#fragment",
    ],
)
def test_cwv_rejects_values_that_are_not_exact_https_origins(origin: str) -> None:
    with pytest.raises(cwv.CwvOriginError, match="not allowed"):
        cwv.ensure_allowed_origin(_binding(), origin)


def test_cwv_rejects_missing_origin_and_invalid_ttl() -> None:
    with pytest.raises(cwv.CwvOriginError, match="required"):
        cwv.ensure_allowed_origin(_binding(), None)
    # The lower bound is inclusive: a one-minute envelope is the shortest
    # supported browser ceremony and must not be rejected by validation.
    cwv.ensure_allowed_origin(
        _binding(envelope_ttl_seconds=60), "https://staging.example.edu"
    )
    with pytest.raises(cwv.CwvConfigurationError) as exc_info:
        cwv.ensure_allowed_origin(
            _binding(envelope_ttl_seconds=59), "https://staging.example.edu"
        )
    assert str(exc_info.value) == "CWV envelope TTL must be between 60 and 600 seconds"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"pathname": "/login"}, ""),
        ({"device_class": "tablet"}, "device class"),
        ({"collector_principal_id": ""}, "collector identifier"),
        ({"gateway_session_id": ""}, "session identifier"),
        ({"nonce_factory": lambda: "short"}, "nonce generator"),
    ],
)
def test_cwv_issue_envelope_validates_each_browser_binding(
    overrides: dict[str, object], message: str
) -> None:
    if not message:
        token, _ = _issue(**overrides)
        assert cwv.verify_envelope(_binding(), token, now=NOW).route_group == "auth"
        return
    with pytest.raises(cwv.CwvEnvelopeError, match=message):
        _issue(**overrides)


@pytest.mark.parametrize("pathname", ["/register", "/forgot-password"])
def test_cwv_auth_route_group_is_case_sensitive_and_stable(pathname: str) -> None:
    token, _ = _issue(pathname=pathname)
    assert cwv.verify_envelope(_binding(), token, now=NOW).route_group == "auth"


def _claims() -> cwv.CwvEnvelopeClaims:
    token, _ = _issue()
    return cwv.verify_envelope(_binding(), token, now=NOW)


@pytest.mark.parametrize(
    ("claims", "now", "message"),
    [
        (
            lambda item: replace(item, issued_at=int(NOW.timestamp()) + 31),
            NOW,
            "expired",
        ),
        (lambda item: replace(item, expires_at=item.issued_at + 301), NOW, "lifetime"),
        (lambda item: replace(item, version=2), NOW, "deployment binding"),
        (lambda item: replace(item, device_class="tablet"), NOW, "claims"),
    ],
)
def test_cwv_signed_claims_still_fail_closed(
    claims: object, now: datetime, message: str
) -> None:
    modified = claims(_claims())
    token = cwv._sign_claims(_binding(), modified)
    with pytest.raises(cwv.CwvEnvelopeError, match=message):
        cwv.verify_envelope(_binding(), token, now=now)


def test_cwv_envelope_parser_rejects_bad_grace_version_and_shape() -> None:
    token, _ = _issue()
    with pytest.raises(cwv.CwvConfigurationError, match="grace"):
        cwv._verify_envelope(_binding(), token, now=NOW, expiration_grace_seconds=-1)
    with pytest.raises(cwv.CwvEnvelopeError, match="malformed"):
        cwv.verify_envelope(_binding(), token.replace("v1.", "v2.", 1), now=NOW)
    encoded = cwv._b64url_encode(b"{}")
    signature = cwv._b64url_encode(
        __import__("hmac").digest(cwv._derived_key(SECRET), encoded.encode(), "sha256")
    )
    with pytest.raises(cwv.CwvEnvelopeError, match="malformed"):
        cwv.verify_envelope(_binding(), f"v1.{encoded}.{signature}", now=NOW)


def test_cwv_envelope_shape_validation_is_fail_closed_for_non_mapping_json() -> None:
    token, _ = _issue()
    _version, _encoded, _signature = token.split(".")
    # ``UserDict`` implements the mapping protocol used by ``**raw`` but is
    # intentionally not a built-in dict.  A guard using ``and`` instead of
    # ``or`` would accept it because its key set is complete, bypassing the
    # required JSON-object shape check.
    claims = cwv.verify_envelope(_binding(), token, now=NOW)
    payload = cwv._b64url_encode(b"mapping-shaped-payload")
    signature = cwv._b64url_encode(
        __import__("hmac").digest(cwv._derived_key(SECRET), payload.encode(), "sha256")
    )
    with patch.object(cwv.json, "loads", return_value=UserDict(cwv.asdict(claims))):
        with pytest.raises(cwv.CwvEnvelopeError, match="malformed"):
            cwv.verify_envelope(_binding(), f"v1.{payload}.{signature}", now=NOW)


def test_cwv_renewal_rejects_changed_identity_navigation_and_nonce() -> None:
    token, _ = _issue()
    common = {
        "token": token,
        "origin": "https://staging.example.edu",
        "pathname": "/dashboard",
        "device_class": "desktop",
        "collector_principal_id": "collector-one",
        "gateway_session_id": "gateway-session-one",
        "now": NOW,
    }
    with pytest.raises(cwv.CwvEnvelopeError) as session_error:
        cwv.renew_envelope(_binding(), **{**common, "collector_principal_id": "other"})
    assert str(session_error.value) == "CWV envelope session binding is invalid"
    with pytest.raises(cwv.CwvEnvelopeError, match="navigation binding"):
        cwv.renew_envelope(_binding(), **{**common, "pathname": "/news"})
    with pytest.raises(cwv.CwvEnvelopeError, match="nonce generator"):
        cwv.renew_envelope(_binding(), **common, nonce_factory=lambda: "short")


def test_cwv_navigation_and_device_claims_are_bound_server_side() -> None:
    token, _ = _issue()
    claims = cwv.verify_envelope(_binding(), token, now=NOW)
    expected_navigation = cwv._opaque_binding_id(
        SECRET,
        "navigation",
        f"{SHA}:gateway-session-one:nonce_abcdefghijklmnop",
    )
    assert claims.navigation_id == expected_navigation
    observation = cwv.build_observation(
        _binding(),
        token=token,
        origin="https://staging.example.edu",
        collector_principal_id="collector-one",
        gateway_session_id="gateway-session-one",
        metric="LCP",
        value=100,
        now=NOW,
    )
    assert observation.device_class == "desktop"


def test_cwv_oidc_maps_jwt_failure_and_rejects_wrong_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = cwv.GithubActionsOidcVerifier(
        enabled=True,
        repository="acme/university",
        workflow_ref="acme/university/.github/workflows/cwv-field-certification.yml@refs/heads/main",
        subject="repo:acme/university:environment:staging",
    )
    monkeypatch.setattr(
        verifier._jwks,
        "get_signing_key_from_jwt",
        MagicMock(side_effect=jwt.PyJWTError("bad")),
    )
    with pytest.raises(cwv.CwvEnvelopeError, match="identity is invalid"):
        verifier.verify("token", expected_sha=SHA)

    monkeypatch.setattr(
        verifier._jwks,
        "get_signing_key_from_jwt",
        MagicMock(return_value=SimpleNamespace(key=object())),
    )
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *_args, **_kwargs: {
            "repository": "acme/university",
            "ref": "refs/heads/main",
            "environment": "staging",
            "event_name": "workflow_dispatch",
            "workflow_ref": verifier.workflow_ref,
            "sha": SHA,
            "sub": "wrong",
        },
    )
    with pytest.raises(cwv.CwvEnvelopeError, match="subject"):
        verifier.verify("token", expected_sha=SHA)


@pytest.mark.asyncio
async def test_cwv_retention_validates_and_can_own_its_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="at least one day"):
        await cleanup_stale_cwv_observations(retention_days=0)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=None)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.services.cwv_retention.async_session", lambda: context)
    assert await cleanup_stale_cwv_observations(now=NOW, retention_days=7) == 0
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cwv_retention_accepts_exact_one_day_boundary() -> None:
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=2)
    assert await cleanup_stale_cwv_observations(db=db, now=NOW, retention_days=1) == 2
    db.commit.assert_awaited_once()


def _api_settings(*, deployed_at: datetime | None = NOW) -> SimpleNamespace:
    return SimpleNamespace(
        cwv_rum_enabled=True,
        cwv_rum_signing_secret=SecretStr(SECRET),
        cwv_release_sha=SHA,
        cwv_frontend_image_digest=DIGEST,
        cwv_deployment_run_id=123,
        cwv_deployment_run_attempt=2,
        cwv_deployment_url="https://staging.example.edu",
        cwv_allowed_origins=" https://staging.example.edu, ,",
        cwv_envelope_ttl_seconds=300,
        cwv_manual_tester_user_ids=SecretStr(str(uuid4())),
        cwv_retention_days=30,
        cwv_export_oidc_enabled=True,
        cwv_export_oidc_repository="acme/university",
        cwv_export_oidc_workflow_ref="workflow",
        cwv_export_oidc_subject="subject",
        cwv_deployed_at=deployed_at,
    )


def test_cwv_api_binding_principal_and_error_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _api_settings()
    first_user_id = uuid4()
    user_id = uuid4()
    settings.cwv_manual_tester_user_ids = SecretStr(f"{first_user_id},{user_id}")
    monkeypatch.setattr(cwv_api, "settings", settings)
    binding = cwv_api._binding()
    assert binding.allowed_origins == ("https://staging.example.edu",)
    assert binding.frontend_image_digest == DIGEST
    assert binding.deployment_run_id == 123
    assert binding.deployment_run_attempt == 2
    assert binding.deployment_url == "https://staging.example.edu"
    assert cwv_api._manual_tester_principal(SimpleNamespace(id=user_id)) == str(user_id)
    with pytest.raises(HTTPException) as denied:
        cwv_api._manual_tester_principal(SimpleNamespace(id=uuid4()))
    assert denied.value.status_code == 403
    assert denied.value.detail == "CWV request rejected"
    for exc, expected in [
        (cwv.CwvConfigurationError(), 503),
        (cwv.CwvOriginError(), 403),
        (cwv.CwvEnvelopeError(), 422),
    ]:
        with pytest.raises(HTTPException) as mapped:
            cwv_api._raise_contract_error(exc)
        assert mapped.value.status_code == expected


@pytest.mark.asyncio
async def test_cwv_api_create_issue_renew_and_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = uuid4()
    monkeypatch.setattr(
        cwv_api, "_manual_tester_principal", lambda _user: str(principal)
    )
    monkeypatch.setattr(cwv_api, "_binding", lambda: _binding())
    expires = NOW + timedelta(minutes=5)
    issue = MagicMock(return_value=("x" * 32, expires))
    renew = MagicMock(return_value=("y" * 32, expires))
    monkeypatch.setattr(cwv_api, "issue_envelope", issue)
    monkeypatch.setattr(cwv_api, "renew_envelope", renew)
    request = SimpleNamespace(
        headers={"origin": "https://staging.example.edu", "x-session-id": "session"}
    )
    user = SimpleNamespace(id=principal)
    issued = await cwv_api.create_cwv_envelope(
        SimpleNamespace(pathname="/", device_class="desktop", renewal_envelope=None),
        request,
        user,
    )
    renewed = await cwv_api.create_cwv_envelope(
        SimpleNamespace(
            pathname="/", device_class="desktop", renewal_envelope="z" * 32
        ),
        request,
        user,
    )
    assert issued.envelope == "x" * 32
    assert renewed.envelope == "y" * 32
    monkeypatch.setattr(
        cwv_api, "issue_envelope", MagicMock(side_effect=cwv.CwvOriginError())
    )
    with pytest.raises(HTTPException) as rejected:
        await cwv_api.create_cwv_envelope(
            SimpleNamespace(
                pathname="/", device_class="desktop", renewal_envelope=None
            ),
            request,
            user,
        )
    assert rejected.value.status_code == 403


def _trusted_observation() -> cwv.CwvTrustedObservation:
    return cwv.CwvTrustedObservation(
        metric="LCP",
        unit="ms",
        value=1000.0,
        metric_id="metric-id",
        collector_id="collector",
        navigation_id="navigation",
        session_id="session",
        device_class="desktop",
        route_group="core",
        observed_at=NOW,
        release_sha=SHA,
        frontend_image_digest=DIGEST,
        deployment_run_id=123,
        deployment_run_attempt=2,
        envelope_nonce="nonce_abcdefghijklmnop",
    )


@pytest.mark.asyncio
async def test_cwv_api_ingest_commits_and_maps_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cwv_api, "_manual_tester_principal", lambda _user: "collector")
    monkeypatch.setattr(cwv_api, "_binding", lambda: _binding())
    monkeypatch.setattr(cwv_api, "settings", _api_settings())
    monkeypatch.setattr(
        cwv_api, "build_observation", MagicMock(return_value=_trusted_observation())
    )
    request = SimpleNamespace(
        headers={"origin": "https://staging.example.edu", "x-session-id": "session"}
    )
    payload = SimpleNamespace(envelope="x" * 32, metric="LCP", value=1000.0)
    db = MagicMock(
        execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock(), add=MagicMock()
    )
    accepted = await cwv_api.ingest_cwv_observation(
        payload, request, db, SimpleNamespace()
    )
    assert accepted.metric_id == "metric-id"
    db.add.assert_called_once()
    db.commit = AsyncMock(
        side_effect=IntegrityError("insert", {}, Exception("duplicate"))
    )
    with pytest.raises(HTTPException) as duplicate:
        await cwv_api.ingest_cwv_observation(payload, request, db, SimpleNamespace())
    assert duplicate.value.status_code == 409
    db.rollback.assert_awaited_once()
    monkeypatch.setattr(
        cwv_api,
        "build_observation",
        MagicMock(side_effect=cwv.CwvEnvelopeError("invalid")),
    )
    with pytest.raises(HTTPException) as invalid:
        await cwv_api.ingest_cwv_observation(payload, request, db, SimpleNamespace())
    assert invalid.value.status_code == 422


def test_cwv_api_bearer_parser_is_strict() -> None:
    for value in (None, "x" * 8193, "Basic token", "Bearer"):
        with pytest.raises(HTTPException) as invalid:
            cwv_api._bearer(value)
        assert invalid.value.status_code == 401
    assert cwv_api._bearer("bearer token") == "token"


class _Rows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _Rows:
        return self

    def all(self) -> list[object]:
        return self._rows


@pytest.mark.asyncio
async def test_cwv_export_bounds_and_serializes_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cwv_api, "_binding", lambda: _binding())
    monkeypatch.setattr(cwv_api, "settings", _api_settings())
    monkeypatch.setattr(cwv_api.asyncio, "to_thread", AsyncMock(return_value={}))
    db = MagicMock(execute=AsyncMock(return_value=_Rows([])))
    common = dict(
        release_sha=SHA,
        frontend_image_digest=DIGEST,
        deployment_run_id=123,
        deployment_run_attempt=2,
        db=db,
        authorization="Bearer token",
    )
    with pytest.raises(HTTPException) as missing:
        await cwv_api.export_cwv_report(**common)
    assert missing.value.status_code == 404

    row = SimpleNamespace(
        metric="LCP",
        unit="ms",
        value=1000.0,
        metric_id="metric",
        collector_id="collector",
        navigation_id="navigation",
        session_id="session",
        device_class="desktop",
        route_group="core",
        observed_at=NOW,
        release_sha=SHA,
        frontend_image_digest=DIGEST,
    )
    db.execute = AsyncMock(return_value=_Rows([row] * 100_001))
    with pytest.raises(HTTPException) as bounded:
        await cwv_api.export_cwv_report(**common)
    assert bounded.value.status_code == 503

    later = SimpleNamespace(
        **{**row.__dict__, "metric": "CLS", "observed_at": NOW + timedelta(minutes=1)}
    )
    db.execute = AsyncMock(return_value=_Rows([row, later]))
    report = await cwv_api.export_cwv_report(**common)
    assert report["window"]["start"] == "2026-08-25T12:00:00Z"
    assert report["window"]["end"] == "2026-08-25T12:01:00Z"
    assert [item["metric"] for item in report["observations"]] == ["LCP", "CLS"]


@pytest.mark.asyncio
async def test_cwv_export_rejects_wrong_release_and_unavailable_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cwv_api, "_binding", lambda: _binding())
    with pytest.raises(HTTPException) as mismatch:
        await cwv_api.export_cwv_report(
            "c" * 40, DIGEST, 123, 2, MagicMock(), "Bearer token"
        )
    assert mismatch.value.status_code == 404
    monkeypatch.setattr(cwv_api, "settings", _api_settings(deployed_at=None))
    monkeypatch.setattr(cwv_api.asyncio, "to_thread", AsyncMock(return_value={}))
    with pytest.raises(HTTPException) as unavailable:
        await cwv_api.export_cwv_report(
            SHA, DIGEST, 123, 2, MagicMock(), "Bearer token"
        )
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (cwv.CwvConfigurationError("config"), 503),
        (cwv.CwvEnvelopeError("identity"), 401),
    ],
)
async def test_cwv_export_maps_oidc_verification_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    monkeypatch.setattr(cwv_api, "_binding", lambda: _binding())
    monkeypatch.setattr(cwv_api, "settings", _api_settings())
    monkeypatch.setattr(cwv_api.asyncio, "to_thread", AsyncMock(side_effect=error))
    with pytest.raises(HTTPException) as rejected:
        await cwv_api.export_cwv_report(
            SHA, DIGEST, 123, 2, MagicMock(), "Bearer token"
        )
    assert rejected.value.status_code == expected_status


def _settings_values() -> dict[str, object]:
    return {
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
        "cwv_manual_tester_user_ids": ",".join(TESTER_IDS),
        "cwv_retention_days": 30,
        "cwv_export_oidc_enabled": True,
        "cwv_export_oidc_repository": "acme/university",
        "cwv_export_oidc_workflow_ref": "acme/university/.github/workflows/cwv-field-certification.yml@refs/heads/main",
        "cwv_export_oidc_subject": "repo:acme/university:environment:staging",
    }


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"cwv_rum_signing_secret": "short"}, "32 bytes"),  # pragma: allowlist secret
        ({"cwv_release_sha": "dev"}, "commit SHA"),
        ({"cwv_frontend_image_digest": "latest"}, "immutable digest"),
        ({"cwv_deployment_run_id": 0}, "run binding"),
        ({"cwv_deployed_at": "2026-08-25T12:00:00"}, "timezone-aware"),
        ({"cwv_retention_days": 2}, "between 3 and 30"),
        (
            {"cwv_deployment_url": "https://staging.example.edu/path"},
            "exact HTTPS origin",
        ),
        ({"cwv_allowed_origins": " , "}, "must contain an HTTPS"),
        ({"cwv_allowed_origins": "https://other.example.edu"}, "explicitly allowed"),
        (
            {"cwv_manual_tester_user_ids": ",".join(["not-a-uuid", *TESTER_IDS[1:]])},
            "contain UUIDs",
        ),
        (
            {
                "cwv_manual_tester_user_ids": ",".join(
                    ["AAAAAAAA-0000-0000-0000-000000000001", *TESTER_IDS[1:]]
                )
            },
            "canonical",
        ),
        (
            {"cwv_manual_tester_user_ids": ",".join([*TESTER_IDS, TESTER_IDS[0]])},
            "unique UUIDs",
        ),
    ],
)
def test_settings_reject_every_partial_cwv_trust_binding(
    updates: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings(**{**_settings_values(), **updates})


def test_cwv_validator_rejects_non_staging_environment_after_other_guards() -> None:
    configured = Settings(**_settings_values())
    configured.environment = "production"
    with pytest.raises(ValueError, match="staging environment"):
        configured._validate_cwv_rum_settings()


def test_notification_topic_settings_reject_unknown_topics() -> None:
    with pytest.raises(ValueError, match="Unknown notification topic"):
        NotificationSettings._validate_notifications_allowed_push_topics(
            ["news.published", "unknown.topic"]
        )


def _session_context(db: object) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.mark.asyncio
async def test_mfa_delivery_event_requires_id_and_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="missing delivery_id"):
        await event_handlers.handle_mfa_email_delivery_requested(
            MfaEmailDeliveryRequested()
        )
    db = MagicMock(commit=AsyncMock())
    service = MagicMock(deliver=AsyncMock())
    sender = SimpleNamespace()
    sender_factory = MagicMock(return_value=sender)
    monkeypatch.setattr(event_handlers, "async_session", lambda: _session_context(db))
    monkeypatch.setattr(
        "app.auth.mfa.email_otp.build_configured_email_delivery_service",
        lambda: service,
    )
    monkeypatch.setattr("app.auth.mfa.email_otp.SmtpMfaEmailSender", sender_factory)
    delivery_id = uuid4()
    await event_handlers.handle_mfa_email_delivery_requested(
        MfaEmailDeliveryRequested(delivery_id=delivery_id)
    )
    service.deliver.assert_awaited_once()
    delivery_call = service.deliver.await_args
    assert delivery_call.args[0] is db
    assert delivery_call.kwargs["delivery_id"] == delivery_id
    assert delivery_call.kwargs["sender"] is sender
    sender_factory.assert_called_once_with()
    db.commit.assert_awaited_once()


def test_mfa_delivery_event_deserializes_schema_version() -> None:
    delivery_id = uuid4()
    payload = {"_schema_version": 1, "delivery_id": str(delivery_id)}
    event = MfaEmailDeliveryRequested.from_dict(payload)
    assert event.delivery_id == str(delivery_id)
    assert "_schema_version" not in payload


@pytest.mark.asyncio
async def test_privacy_cleanup_skips_cwv_when_rum_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        session_retention_days=90,
        mfa_retention_days=30,
        failed_login_retention_days=14,
        access_log_retention_days=180,
        privacy_cleanup_interval_seconds=3600,
        cwv_rum_enabled=False,
        cwv_retention_days=30,
    )
    cleanup = AsyncMock()
    cwv_cleanup = AsyncMock()
    monkeypatch.setattr(cleanups, "settings", settings)
    monkeypatch.setattr(cleanups, "cleanup_privacy_artifacts", cleanup)
    monkeypatch.setattr(cleanups, "cleanup_stale_cwv_observations", cwv_cleanup)
    await cleanups.cleanup_privacy_artifacts_task()
    cleanup.assert_awaited_once()
    cwv_cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_redelivery_early_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock(execute=AsyncMock(), flush=AsyncMock())
    with pytest.raises(ValueError, match="Unsupported"):
        await delivery.redeliver_notifications(
            db, notification_ids=[uuid4()], channel="email"
        )
    assert (
        await delivery.redeliver_notifications(db, notification_ids=[])
        == delivery.NotificationRedeliveryOutcome()
    )
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: False)
    with pytest.raises(delivery.NotificationRedeliveryError) as unavailable:
        await delivery.redeliver_notifications(db, notification_ids=[uuid4()])
    assert unavailable.value.outcome.retryable_failures == 1


@pytest.mark.asyncio
async def test_notification_redelivery_returns_when_rows_disappeared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = []
    db = MagicMock(execute=AsyncMock(return_value=rows), flush=AsyncMock())
    assert (
        await delivery.redeliver_notifications(db, notification_ids=[uuid4()])
        == delivery.NotificationRedeliveryOutcome()
    )


def _scalar_rows(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _notification(user_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title="Title",
        body="Body",
        url="/news/1",
        type="news",
        created_at=NOW,
    )


def _subscription(user_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), user_id=user_id, user=None)


@pytest.mark.asyncio
async def test_notification_redelivery_handles_users_without_subscriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[_scalar_rows([_notification(user_id)]), _scalar_rows([])]
        ),
        flush=AsyncMock(),
    )
    assert (
        await delivery.redeliver_notifications(db, notification_ids=[uuid4()])
        == delivery.NotificationRedeliveryOutcome()
    )
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_notification_redelivery_skips_null_journal_and_unsupported_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    notification = _notification(user_id)
    subscription = _subscription(user_id)
    subscription.endpoint = "https://push.example.test/subscription"
    null_delivery = SimpleNamespace(subscription_id=None)
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _scalar_rows([notification]),
                _scalar_rows([subscription]),
                _scalar_rows([null_delivery]),
            ]
        ),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: False)
    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )
    journal_query = db.execute.await_args_list[2].args[0]
    assert "notification_deliveries.notification_id IN" in str(
        journal_query.whereclause
    )
    assert [notification.id] in journal_query.compile().params.values()
    assert outcome.terminal_failures == 1


@pytest.mark.asyncio
async def test_notification_redelivery_applies_user_quiet_hours_to_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    notification = _notification(user_id)
    subscription = _subscription(user_id)
    subscription.endpoint = "https://push.example.test/subscription"
    subscription.user = SimpleNamespace(
        preferences=SimpleNamespace(dnd_enabled=True, dnd_start=None, dnd_end=None)
    )
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _scalar_rows([notification]),
                _scalar_rows([subscription]),
                _scalar_rows([]),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    send = AsyncMock(
        return_value=delivery.WebPushResult(
            subscription_id=subscription.id,
            endpoint=subscription.endpoint,
            user_id=user_id,
            status="sent",
        )
    )
    monkeypatch.setattr(delivery.webpush_module, "_send_push_async", send)

    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )

    assert outcome.sent == 1
    payload = send.await_args.args[1]
    assert payload["silent"] is True
    assert payload["vibrate"] == []
    assert payload["renotify"] is False
    assert payload["requireInteraction"] is False
    assert payload["data"]["dnd_suppressed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("with_prior", "notification_type"),
    [(False, "news"), (True, "news"), (False, None)],
)
async def test_notification_redelivery_records_provider_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    with_prior: bool,
    notification_type: str | None,
) -> None:
    user_id = uuid4()
    notification = _notification(user_id)
    notification.type = notification_type
    subscription = _subscription(user_id)
    prior = SimpleNamespace(
        notification_id=notification.id,
        subscription_id=subscription.id,
        status="error",
        delivered_at=NOW,
        status_code=503,
        detail="old",
    )
    journal = [prior] if with_prior else []
    db = MagicMock(
        execute=AsyncMock(
            side_effect=[
                _scalar_rows([notification]),
                _scalar_rows([subscription]),
                _scalar_rows(journal),
                MagicMock(),
            ]
        ),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(delivery, "subscription_supports_topic", lambda *_args: True)
    monkeypatch.setattr(delivery, "normalize_topic", lambda _topic: None)
    monkeypatch.setattr(
        delivery.webpush_module,
        "_send_push_async",
        AsyncMock(side_effect=RuntimeError("provider failed")),
    )
    build_row = MagicMock(side_effect=delivery._build_delivery_row)
    monkeypatch.setattr(delivery, "_build_delivery_row", build_row)
    record_failed = MagicMock()
    monkeypatch.setattr(delivery.metrics, "record_notification_failed", record_failed)
    outcome = await delivery.redeliver_notifications(
        db, notification_ids=[notification.id]
    )
    assert outcome.retryable_failures == 1
    record_failed.assert_called_once_with(
        notification_type=notification_type or "unknown",
        reason="exception",
    )
    if with_prior:
        assert prior.status == "error"
        assert prior.delivered_at is None
        assert prior.status_code is None
        assert prior.detail == "exception:provider failed"
    else:
        assert build_row.call_args is not None
        assert build_row.call_args.kwargs["status"] == "error"
        assert build_row.call_args.kwargs["detail"] == "exception:provider failed"


@pytest.mark.asyncio
async def test_notification_creation_stops_after_topic_preference_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: True)
    monkeypatch.setattr(
        delivery, "filter_user_ids_by_topic", AsyncMock(return_value=[])
    )
    db = MagicMock(execute=AsyncMock(), flush=AsyncMock())
    assert (
        await delivery.create_notifications_for_users(
            db,
            title="Filtered",
            user_ids=[uuid4()],
            topic="news.published",
        )
        == 0
    )
