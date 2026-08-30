"""Deterministic, mutation-sensitive contracts for field-CWV evidence."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock, patch

import jwt
import pytest

import app.services.cwv as cwv
from app.services.cwv import (
    CwvConfigurationError,
    CwvEnvelopeClaims,
    CwvEnvelopeError,
    CwvOriginError,
    CwvRumBinding,
    GithubActionsOidcVerifier,
    _b64url_decode,
    _b64url_encode,
    _derived_key,
    _opaque_binding_id,
    _origin,
    _session_binding,
    _sign_claims,
    _validate_binding,
    _verify_envelope,
    build_observation,
    derive_route_group,
    ensure_allowed_origin,
    issue_envelope,
    renew_envelope,
    verify_envelope,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
SECRET = "cwv-signing-secret-with-at-least-32-bytes"  # pragma: allowlist secret
COLLECTOR = "00000000-0000-0000-0000-000000000001"
GATEWAY_SESSION = "gateway-session-not-stored"
WORKFLOW = (
    "acme/university/.github/workflows/cwv-field-certification.yml@refs/heads/main"
)
SUBJECT = "repo:acme/university:environment:staging"


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


def _issued(
    *, pathname: str = "/dashboard", nonce: str = "nonce_abcdefghijklmnop"
) -> str:
    token, _ = issue_envelope(
        _binding(),
        origin="https://staging.example.edu",
        pathname=pathname,
        device_class="desktop",
        collector_principal_id=COLLECTOR,
        gateway_session_id=GATEWAY_SESSION,
        now=NOW,
        nonce_factory=lambda: nonce,
    )
    return token


@pytest.mark.parametrize("length", range(0, 10))
def test_base64url_encoding_and_decoding_matches_rfc4648_without_padding(
    length: int,
) -> None:
    raw = bytes(range(length))
    expected = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    encoded = _b64url_encode(raw)
    assert encoded == expected
    assert "=" not in encoded
    assert _b64url_decode(encoded) == raw


def test_derived_and_opaque_bindings_use_canonical_sha256_and_utf8_contract() -> None:
    expected_key = hmac.new(
        SECRET.encode("utf-8"),
        b"university-cwv-rum-envelope-v1",
        hashlib.sha256,
    ).digest()
    assert _derived_key(SECRET) == expected_key
    expected_opaque = hmac.new(
        expected_key,
        b"manual-collector:collector-one",
        hashlib.sha256,
    ).hexdigest()[:32]
    assert (
        _opaque_binding_id(SECRET, "manual-collector", "collector-one")
        == expected_opaque
    )

    # The digest API accepts case-insensitive algorithm spellings, but the
    # wire contract deliberately uses the canonical lowercase spelling.
    real_digest = cwv.hmac.digest
    with patch.object(cwv.hmac, "digest", side_effect=real_digest) as digest:
        _derived_key(SECRET)
    assert digest.call_args.args[2] == "sha256"
    with patch.object(cwv.hmac, "digest", side_effect=real_digest) as digest:
        _opaque_binding_id(SECRET, "manual-collector", "collector-one")
    # `_opaque_binding_id` performs the derived-key call first and the
    # domain-specific digest second; both must use the canonical spelling.
    assert [call.args[2] for call in digest.call_args_list] == ["sha256", "sha256"]


def test_session_binding_has_inclusive_identifier_bounds_and_stable_domain() -> None:
    binding = _binding()
    assert len(_session_binding(binding, "collector-one", "x")) == 32
    assert len(_session_binding(binding, "collector-one", "x" * 256)) == 32
    with pytest.raises(
        CwvEnvelopeError, match=r"^CWV gateway session identifier is invalid$"
    ):
        _session_binding(binding, "collector-one", "x" * 257)

    derived_key = _derived_key(SECRET)
    expected = hmac.new(
        derived_key,
        f"gateway-session:{SHA}:collector-one:gateway-one".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]
    assert _session_binding(binding, "collector-one", "gateway-one") == expected


def test_allowed_origin_normalizes_hostnames_to_lowercase() -> None:
    """Origin canonicalization is case-insensitive only for the host name."""

    assert _origin("https://STAGING.Example.EDU/") == "https://staging.example.edu"


@pytest.mark.parametrize(
    ("pathname", "expected"),
    [
        ("/", "core"),
        ("/dashboard/", "core"),
        ("/schedule", "core"),
        ("/login", "auth"),
        ("/register/details", "auth"),
        ("/forgot-password", "auth"),
        ("/reset-password/token", "auth"),
        ("/auth/callback", "auth"),
        ("/news/article", "content"),
        ("/events/calendar", "content"),
        ("/map/campus", "map_activity"),
        ("/activity/period", "map_activity"),
        ("/messenger/chat", "messenger_profile_settings_admin"),
        ("/profile/me", "messenger_profile_settings_admin"),
        ("/settings/security", "messenger_profile_settings_admin"),
        ("/admin/users", "messenger_profile_settings_admin"),
        ("/news?filter=all#section", "content"),
    ],
)
def test_route_group_allowlist_is_complete_and_normalizes_url_delimiters(
    pathname: str, expected: str
) -> None:
    assert derive_route_group(pathname) == expected


def test_route_group_rejects_unknown_paths_with_exact_error() -> None:
    with pytest.raises(
        CwvEnvelopeError,
        match=r"^CWV route is not in the certification allowlist$",
    ):
        derive_route_group("/unknown")


@pytest.mark.parametrize("pathname", ["//news", "//login", "//settings"])
def test_route_group_preserves_empty_leading_segment_as_core(pathname: str) -> None:
    """Duplicate leading slashes must not reclassify the route group.

    The route parser intentionally removes only one leading slash before
    selecting the first segment.  Keeping the empty segment produced by a
    malformed double-slash path preserves the fail-closed legacy contract:
    these paths remain in the root/core bucket instead of being interpreted as
    an authenticated, content, or settings route.
    """

    assert derive_route_group(pathname) == "core"


@pytest.mark.parametrize(
    "value",
    [
        "http://staging.example.edu",
        "https:///missing-host",
        "https://",
        "https://user@staging.example.edu",
        "https://:password@staging.example.edu",
        "https://staging.example.edu/path",
        "https://staging.example.edu/?query=1",
        "https://staging.example.edu/#fragment",
    ],
)
def test_origin_parser_rejects_credentials_paths_and_non_https_exactly(
    value: str,
) -> None:
    with pytest.raises(
        CwvConfigurationError,
        match=r"^CWV allowed origin must be an HTTPS origin$",
    ):
        _origin(value)


def test_allowed_origin_has_distinct_required_and_not_allowed_errors() -> None:
    binding = _binding()
    with pytest.raises(CwvOriginError, match=r"^CWV request origin is required$"):
        ensure_allowed_origin(binding, None)
    with pytest.raises(CwvOriginError, match=r"^CWV request origin is not allowed$"):
        ensure_allowed_origin(binding, "http://staging.example.edu")
    with pytest.raises(CwvOriginError, match=r"^CWV request origin is not allowed$"):
        ensure_allowed_origin(binding, "https://evil.example.edu")
    # Host names are normalized case-insensitively, while path/query are not
    # accepted as origins.
    ensure_allowed_origin(binding, "https://STAGING.EXAMPLE.EDU")


@pytest.mark.parametrize(
    ("overrides", "accepted"),
    [
        ({"signing_secret": "s" * 32}, True),
        ({"deployment_run_id": 1, "deployment_run_attempt": 1}, True),
        ({"envelope_ttl_seconds": 60}, True),
        ({"envelope_ttl_seconds": 600}, True),
    ],
)
def test_binding_accepts_inclusive_security_boundaries(
    overrides: dict[str, object], accepted: bool
) -> None:
    del accepted
    _validate_binding(_binding(**overrides))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"enabled": False}, "CWV RUM is disabled"),
        (
            {"signing_secret": "s" * 31},
            "CWV signing secret must contain at least 32 bytes",
        ),
        ({"deployment_run_id": 0}, "CWV deployment run binding is invalid"),
        ({"deployment_run_attempt": 0}, "CWV deployment run binding is invalid"),
        (
            {"envelope_ttl_seconds": 601},
            "CWV envelope TTL must be between 60 and 600 seconds",
        ),
    ],
)
def test_binding_rejects_invalid_security_boundaries_with_exact_messages(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(CwvConfigurationError, match=rf"^{message}$"):
        _validate_binding(_binding(**overrides))


def test_sign_claims_is_deterministic_and_canonical() -> None:
    claims = CwvEnvelopeClaims(
        version=1,
        nonce="nonce_abcdefghijklmnop",
        issued_at=1_700_000_000,
        expires_at=1_700_000_300,
        release_sha=SHA,
        frontend_image_digest=DIGEST,
        deployment_run_id=123,
        deployment_run_attempt=2,
        route_group="content",
        device_class="desktop",
        collector_id="c" * 32,
        session_id="s" * 32,
        navigation_id="n" * 32,
    )
    token = _sign_claims(_binding(), claims)
    encoded = token.split(".")[1]
    payload = _b64url_decode(encoded)
    assert payload == (
        b'{"collector_id":"cccccccccccccccccccccccccccccccc",'
        b'"deployment_run_attempt":2,"deployment_run_id":123,'
        b'"device_class":"desktop","expires_at":1700000300,'
        b'"frontend_image_digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
        b'"issued_at":1700000000,"navigation_id":"nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn",'
        b'"nonce":"nonce_abcdefghijklmnop","release_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"route_group":"content","session_id":"ssssssssssssssssssssssssssssssss","version":1}'
    )
    assert token == (
        "v1."
        + encoded
        + "."
        + _b64url_encode(
            hmac.digest(_derived_key(SECRET), encoded.encode(), hashlib.sha256)
        )
    )


@pytest.mark.parametrize(
    "field", ["nonce", "collector_id", "session_id", "navigation_id"]
)
def test_envelope_rejects_each_opaque_claim_independently(field: str) -> None:
    claims = verify_envelope(_binding(), _issued(), now=NOW)
    invalid = replace(claims, **{field: ""})
    token = _sign_claims(_binding(), invalid)
    with pytest.raises(CwvEnvelopeError, match=r"^CWV envelope claims are invalid$"):
        verify_envelope(_binding(), token, now=NOW)


@pytest.mark.parametrize("token", ["not-a-cwv-token", "v1.only-two-parts"])
def test_envelope_malformed_tokens_use_the_stable_error_message(token: str) -> None:
    with pytest.raises(CwvEnvelopeError, match=r"^CWV envelope is malformed$"):
        verify_envelope(_binding(), token, now=NOW)


def test_envelope_verification_uses_canonical_lowercase_sha256_name() -> None:
    token = _issued()
    original_digest = cwv.hmac.digest
    digest_names: list[object] = []

    def record_digest(key: bytes, msg: bytes, digest: object) -> bytes:
        digest_names.append(digest)
        return original_digest(key, msg, digest)

    with patch.object(cwv.hmac, "digest", side_effect=record_digest):
        _verify_envelope(_binding(), token, now=NOW, expiration_grace_seconds=0)

    assert digest_names == ["sha256", "sha256"]


def test_envelope_grace_period_has_exact_inclusive_limit_and_message() -> None:
    token = _issued()
    _verify_envelope(_binding(), token, now=NOW, expiration_grace_seconds=86_400)
    with pytest.raises(
        CwvConfigurationError,
        match=r"^CWV envelope grace period is invalid$",
    ):
        _verify_envelope(_binding(), token, now=NOW, expiration_grace_seconds=86_401)


def test_issue_and_renew_reject_invalid_device_nonce_and_navigation_exactly() -> None:
    with pytest.raises(CwvEnvelopeError, match=r"^CWV device class is invalid$"):
        issue_envelope(
            _binding(),
            origin="https://staging.example.edu",
            pathname="/dashboard",
            device_class="tablet",
            collector_principal_id=COLLECTOR,
            gateway_session_id=GATEWAY_SESSION,
            now=NOW,
        )
    with pytest.raises(
        CwvEnvelopeError,
        match=r"^CWV nonce generator returned an invalid identifier$",
    ):
        issue_envelope(
            _binding(),
            origin="https://staging.example.edu",
            pathname="/dashboard",
            device_class="desktop",
            collector_principal_id=COLLECTOR,
            gateway_session_id=GATEWAY_SESSION,
            now=NOW,
            nonce_factory=lambda: "short",
        )

    token = _issued(pathname="/news")
    with pytest.raises(
        CwvEnvelopeError,
        match=r"^CWV envelope navigation binding is invalid$",
    ):
        renew_envelope(
            _binding(),
            token=token,
            origin="https://staging.example.edu",
            pathname="/dashboard",
            device_class="desktop",
            collector_principal_id=COLLECTOR,
            gateway_session_id=GATEWAY_SESSION,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(
        CwvEnvelopeError,
        match=r"^CWV nonce generator returned an invalid identifier$",
    ):
        renew_envelope(
            _binding(),
            token=token,
            origin="https://staging.example.edu",
            pathname="/news",
            device_class="desktop",
            collector_principal_id=COLLECTOR,
            gateway_session_id=GATEWAY_SESSION,
            now=NOW + timedelta(seconds=1),
            nonce_factory=lambda: "short",
        )


def test_renew_envelope_uses_utc_for_an_implicit_clock() -> None:
    token = _issued(pathname="/news")

    class TrackingDateTime(datetime):
        seen_timezones: ClassVar[list[object]] = []

        @classmethod
        def now(cls, tz: object = None) -> datetime:
            cls.seen_timezones.append(tz)
            return NOW + timedelta(seconds=1)

    with patch.object(cwv, "datetime", TrackingDateTime):
        renewed, expiry = renew_envelope(
            _binding(),
            token=token,
            origin="https://staging.example.edu",
            pathname="/news",
            device_class="desktop",
            collector_principal_id=COLLECTOR,
            gateway_session_id=GATEWAY_SESSION,
            nonce_factory=lambda: "renewed_nonce_abcdef",
        )

    assert renewed
    assert expiry == NOW + timedelta(seconds=301)
    assert TrackingDateTime.seen_timezones == [UTC]


@pytest.mark.parametrize(
    ("metric", "value", "valid"),
    [
        ("LCP", 0, True),
        ("LCP", 60_000, True),
        ("LCP", 60_001, False),
        ("INP", 0, True),
        ("INP", 60_000, True),
        ("INP", 60_001, False),
        ("CLS", 0, True),
        ("CLS", 10, True),
        ("CLS", 10.1, False),
    ],
)
def test_observation_metric_limits_are_inclusive_and_identity_is_server_derived(
    metric: str, value: float, valid: bool
) -> None:
    token = _issued(pathname="/activity")
    if not valid:
        with pytest.raises(CwvEnvelopeError, match=r"^CWV metric or value is invalid$"):
            build_observation(
                _binding(),
                token=token,
                origin="https://staging.example.edu",
                collector_principal_id=COLLECTOR,
                gateway_session_id=GATEWAY_SESSION,
                metric=metric,
                value=value,
                now=NOW,
            )
        return
    observation = build_observation(
        _binding(),
        token=token,
        origin="https://staging.example.edu",
        collector_principal_id=COLLECTOR,
        gateway_session_id=GATEWAY_SESSION,
        metric=metric,
        value=value,
        now=NOW,
    )
    claims = verify_envelope(_binding(), token, now=NOW)
    assert observation.navigation_id == claims.navigation_id
    assert observation.session_id == claims.session_id
    assert observation.envelope_nonce == claims.nonce
    assert observation.value == float(value)


def _oidc_verifier() -> GithubActionsOidcVerifier:
    return GithubActionsOidcVerifier(
        enabled=True,
        repository="acme/university",
        workflow_ref=WORKFLOW,
        subject=SUBJECT,
    )


def _oidc_claims() -> dict[str, str]:
    return {
        "sub": SUBJECT,
        "repository": "acme/university",
        "ref": "refs/heads/main",
        "environment": "staging",
        "event_name": "workflow_dispatch",
        "workflow_ref": WORKFLOW,
        "sha": SHA,
    }


def test_oidc_policy_rejects_missing_subject_or_workflow_with_exact_message() -> None:
    with pytest.raises(
        CwvConfigurationError,
        match=r"^CWV exporter OIDC policy is not fully configured$",
    ):
        GithubActionsOidcVerifier(
            enabled=True,
            repository="acme/university",
            workflow_ref=WORKFLOW,
            subject="",
        ).verify("token", expected_sha=SHA)
    with pytest.raises(
        CwvConfigurationError,
        match=r"^CWV exporter OIDC policy is not fully configured$",
    ):
        GithubActionsOidcVerifier(
            enabled=True, repository="acme/university", workflow_ref="", subject=SUBJECT
        ).verify("token", expected_sha=SHA)


def test_oidc_verifier_has_distinct_exact_identity_claim_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _oidc_verifier()
    monkeypatch.setattr(
        verifier._jwks,
        "get_signing_key_from_jwt",
        Mock(return_value=SimpleNamespace(key=object())),
    )
    valid_claims = _oidc_claims()
    monkeypatch.setattr(jwt, "decode", Mock(return_value=valid_claims))
    assert verifier.verify("token", expected_sha=SHA) == valid_claims

    malformed = Mock(side_effect=jwt.PyJWTError("bad token"))
    monkeypatch.setattr(jwt, "decode", malformed)
    with pytest.raises(CwvEnvelopeError, match=r"^CWV exporter identity is invalid$"):
        verifier.verify("token", expected_sha=SHA)

    bad_claims = {**valid_claims, "environment": "production"}
    monkeypatch.setattr(jwt, "decode", Mock(return_value=bad_claims))
    with pytest.raises(
        CwvEnvelopeError, match=r"^CWV exporter identity claims are invalid$"
    ):
        verifier.verify("token", expected_sha=SHA)

    bad_subject = {**valid_claims, "sub": "repo:acme/university:environment:production"}
    monkeypatch.setattr(jwt, "decode", Mock(return_value=bad_subject))
    with pytest.raises(
        CwvEnvelopeError,
        match=r"^CWV exporter subject is not staging-bound$",
    ):
        verifier.verify("token", expected_sha=SHA)
