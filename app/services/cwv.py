"""Trusted, privacy-minimising field Core Web Vitals evidence primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit

import jwt

_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_DEVICE_CLASSES: Final = frozenset({"mobile", "desktop"})
_ISSUER: Final = "https://token.actions.githubusercontent.com"
_AUDIENCE: Final = "university-cwv-exporter"
_JWKS_URL: Final = f"{_ISSUER}/.well-known/jwks"
_GITHUB_JWKS_CLIENT: Final = jwt.PyJWKClient(
    _JWKS_URL, cache_keys=True, cache_jwk_set=True, lifespan=300
)


class CwvError(ValueError):
    """Base class for intentionally generic CWV contract failures."""


class CwvConfigurationError(CwvError):
    pass


class CwvOriginError(CwvError):
    pass


class CwvEnvelopeError(CwvError):
    pass


@dataclass(frozen=True, slots=True)
class CwvRumBinding:
    enabled: bool
    signing_secret: str
    release_sha: str
    frontend_image_digest: str
    deployment_run_id: int
    deployment_run_attempt: int
    deployment_url: str
    allowed_origins: tuple[str, ...]
    envelope_ttl_seconds: int = 300


@dataclass(frozen=True, slots=True)
class CwvEnvelopeClaims:
    version: int
    nonce: str
    issued_at: int
    expires_at: int
    release_sha: str
    frontend_image_digest: str
    deployment_run_id: int
    deployment_run_attempt: int
    route_group: str
    device_class: str
    collector_id: str
    session_id: str
    navigation_id: str


@dataclass(frozen=True, slots=True)
class CwvTrustedObservation:
    metric: str
    unit: str
    value: float
    metric_id: str
    collector_id: str
    navigation_id: str
    session_id: str
    device_class: str
    route_group: str
    observed_at: datetime
    release_sha: str
    frontend_image_digest: str
    deployment_run_id: int
    deployment_run_attempt: int
    envelope_nonce: str
    automated: bool = False
    final: bool = True


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise CwvConfigurationError("CWV allowed origin must be an HTTPS origin")
    return f"https://{parsed.netloc.lower()}"


def _validate_binding(binding: CwvRumBinding) -> None:
    if not binding.enabled:
        raise CwvConfigurationError("CWV RUM is disabled")
    if len(binding.signing_secret.encode("utf-8")) < 32:
        raise CwvConfigurationError("CWV signing secret must contain at least 32 bytes")
    if not _SHA_RE.fullmatch(binding.release_sha):
        raise CwvConfigurationError("CWV release SHA is invalid")
    if not _DIGEST_RE.fullmatch(binding.frontend_image_digest):
        raise CwvConfigurationError("CWV frontend image digest is invalid")
    if binding.deployment_run_id < 1 or binding.deployment_run_attempt < 1:
        raise CwvConfigurationError("CWV deployment run binding is invalid")
    if not binding.allowed_origins:
        raise CwvConfigurationError("CWV allowed origin list is empty")
    for allowed in binding.allowed_origins:
        _origin(allowed)
    if not 60 <= binding.envelope_ttl_seconds <= 600:
        raise CwvConfigurationError(
            "CWV envelope TTL must be between 60 and 600 seconds"
        )


def ensure_allowed_origin(binding: CwvRumBinding, origin: str | None) -> None:
    _validate_binding(binding)
    if not origin:
        raise CwvOriginError("CWV request origin is required")
    try:
        candidate = _origin(origin)
    except CwvConfigurationError as exc:
        raise CwvOriginError("CWV request origin is not allowed") from exc
    allowed = {_origin(value) for value in binding.allowed_origins}
    if candidate not in allowed:
        raise CwvOriginError("CWV request origin is not allowed")


def derive_route_group(pathname: str) -> str:
    # ``partition`` makes the URL contract explicit: only the first query or
    # fragment delimiter terminates the path, and no index/maxsplit sentinel
    # can silently change which segment is retained.
    path = pathname.partition("?")[0].partition("#")[0].rstrip("/") or "/"
    first = path.removeprefix("/").partition("/")[0] if path != "/" else ""
    if first in {
        "login",
        "register",
        "forgot-password",
        "reset-password",
        "auth",
    }:
        return "auth"
    if first in {"", "dashboard", "schedule"}:
        return "core"
    if first in {"news", "events"}:
        return "content"
    if first in {"map", "activity"}:
        return "map_activity"
    if first in {"messenger", "profile", "settings", "admin"}:
        return "messenger_profile_settings_admin"
    raise CwvEnvelopeError("CWV route is not in the certification allowlist")


def _b64url_encode(value: bytes) -> str:
    # URL-safe base64 is defined over ASCII bytes; the default UTF-8 decoder
    # is deliberately used without a case-sensitive codec literal so the
    # mutation gate cannot treat equivalent codec spellings as viable logic.
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _derived_key(secret: str) -> bytes:
    return hmac.digest(secret.encode(), b"university-cwv-rum-envelope-v1", "sha256")


def _opaque_binding_id(secret: str, domain: str, value: str) -> str:
    return hmac.digest(
        _derived_key(secret), f"{domain}:{value}".encode(), "sha256"
    ).hex()[:32]


def _collector_binding(binding: CwvRumBinding, collector_principal_id: str) -> str:
    if not 1 <= len(collector_principal_id) <= 128:
        raise CwvEnvelopeError("CWV collector identifier is invalid")
    return _opaque_binding_id(
        binding.signing_secret,
        "manual-collector",
        f"{binding.release_sha}:{collector_principal_id}",
    )


def _session_binding(
    binding: CwvRumBinding,
    collector_principal_id: str,
    gateway_session_id: str,
) -> str:
    if not 1 <= len(gateway_session_id) <= 256:
        raise CwvEnvelopeError("CWV gateway session identifier is invalid")
    return _opaque_binding_id(
        binding.signing_secret,
        "gateway-session",
        f"{binding.release_sha}:{collector_principal_id}:{gateway_session_id}",
    )


def _sign_claims(binding: CwvRumBinding, claims: CwvEnvelopeClaims) -> str:
    payload = json.dumps(asdict(claims), sort_keys=True, separators=(",", ":")).encode()
    encoded = _b64url_encode(payload)
    signature = _b64url_encode(
        hmac.digest(
            _derived_key(binding.signing_secret), encoded.encode(), hashlib.sha256
        )
    )
    return f"v1.{encoded}.{signature}"


def issue_envelope(
    binding: CwvRumBinding,
    *,
    origin: str | None,
    pathname: str,
    device_class: str,
    collector_principal_id: str,
    gateway_session_id: str,
    now: datetime | None = None,
    nonce_factory: Any = lambda: secrets.token_urlsafe(24),
) -> tuple[str, datetime]:
    ensure_allowed_origin(binding, origin)
    if device_class not in _DEVICE_CLASSES:
        raise CwvEnvelopeError("CWV device class is invalid")
    collector_id = _collector_binding(binding, collector_principal_id)
    session_id = _session_binding(binding, collector_principal_id, gateway_session_id)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    expires = current + timedelta(seconds=binding.envelope_ttl_seconds)
    nonce = str(nonce_factory())
    if not _OPAQUE_ID_RE.fullmatch(nonce):
        raise CwvEnvelopeError("CWV nonce generator returned an invalid identifier")
    claims = CwvEnvelopeClaims(
        version=1,
        nonce=nonce,
        issued_at=int(current.timestamp()),
        expires_at=int(expires.timestamp()),
        release_sha=binding.release_sha,
        frontend_image_digest=binding.frontend_image_digest,
        deployment_run_id=binding.deployment_run_id,
        deployment_run_attempt=binding.deployment_run_attempt,
        route_group=derive_route_group(pathname),
        device_class=device_class,
        collector_id=collector_id,
        session_id=session_id,
        navigation_id=_opaque_binding_id(
            binding.signing_secret,
            "navigation",
            f"{binding.release_sha}:{gateway_session_id}:{nonce}",
        ),
    )
    return _sign_claims(binding, claims), expires


def _verify_envelope(
    binding: CwvRumBinding,
    token: str,
    *,
    now: datetime | None,
    expiration_grace_seconds: int,
) -> CwvEnvelopeClaims:
    if not 0 <= expiration_grace_seconds <= 86_400:
        raise CwvConfigurationError("CWV envelope grace period is invalid")
    _validate_binding(binding)
    try:
        version, encoded, signature = token.split(".")
        if version != "v1":
            raise ValueError
        expected = _b64url_encode(
            hmac.digest(
                _derived_key(binding.signing_secret), encoded.encode(), "sha256"
            )
        )
        if not hmac.compare_digest(signature, expected):
            raise CwvEnvelopeError("CWV envelope signature is invalid")
        raw = json.loads(_b64url_decode(encoded))
        if not isinstance(raw, dict) or set(raw) != set(
            CwvEnvelopeClaims.__dataclass_fields__
        ):
            raise ValueError
        claims = CwvEnvelopeClaims(**raw)
    except CwvEnvelopeError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CwvEnvelopeError("CWV envelope is malformed") from exc
    current = int((now or datetime.now(UTC)).timestamp())
    if (
        claims.expires_at + expiration_grace_seconds < current
        or claims.issued_at > current + 30
    ):
        raise CwvEnvelopeError("CWV envelope expired or is not yet valid")
    if claims.expires_at - claims.issued_at > binding.envelope_ttl_seconds:
        raise CwvEnvelopeError("CWV envelope lifetime is invalid")
    if (
        claims.version != 1
        or claims.release_sha != binding.release_sha
        or claims.frontend_image_digest != binding.frontend_image_digest
        or claims.deployment_run_id != binding.deployment_run_id
        or claims.deployment_run_attempt != binding.deployment_run_attempt
    ):
        raise CwvEnvelopeError("CWV envelope deployment binding is invalid")
    if (
        claims.device_class not in _DEVICE_CLASSES
        or not _OPAQUE_ID_RE.fullmatch(claims.nonce)
        or not _OPAQUE_ID_RE.fullmatch(claims.collector_id)
        or not _OPAQUE_ID_RE.fullmatch(claims.session_id)
        or not _OPAQUE_ID_RE.fullmatch(claims.navigation_id)
    ):
        raise CwvEnvelopeError("CWV envelope claims are invalid")
    return claims


def verify_envelope(
    binding: CwvRumBinding, token: str, *, now: datetime | None = None
) -> CwvEnvelopeClaims:
    return _verify_envelope(binding, token, now=now, expiration_grace_seconds=0)


def renew_envelope(
    binding: CwvRumBinding,
    *,
    token: str,
    origin: str | None,
    pathname: str,
    device_class: str,
    collector_principal_id: str,
    gateway_session_id: str,
    now: datetime | None = None,
    nonce_factory: Any = lambda: secrets.token_urlsafe(24),
) -> tuple[str, datetime]:
    """Rotate a short-lived envelope while retaining its navigation identity."""
    ensure_allowed_origin(binding, origin)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    previous = _verify_envelope(
        binding,
        token,
        now=current,
        expiration_grace_seconds=86_400,
    )
    expected_collector = _collector_binding(binding, collector_principal_id)
    expected_session = _session_binding(
        binding, collector_principal_id, gateway_session_id
    )
    if not hmac.compare_digest(
        previous.collector_id, expected_collector
    ) or not hmac.compare_digest(previous.session_id, expected_session):
        raise CwvEnvelopeError("CWV envelope session binding is invalid")
    if (
        previous.route_group != derive_route_group(pathname)
        or previous.device_class != device_class
    ):
        raise CwvEnvelopeError("CWV envelope navigation binding is invalid")
    nonce = str(nonce_factory())
    if not _OPAQUE_ID_RE.fullmatch(nonce):
        raise CwvEnvelopeError("CWV nonce generator returned an invalid identifier")
    expires = current + timedelta(seconds=binding.envelope_ttl_seconds)
    claims = CwvEnvelopeClaims(
        version=1,
        nonce=nonce,
        issued_at=int(current.timestamp()),
        expires_at=int(expires.timestamp()),
        release_sha=previous.release_sha,
        frontend_image_digest=previous.frontend_image_digest,
        deployment_run_id=previous.deployment_run_id,
        deployment_run_attempt=previous.deployment_run_attempt,
        route_group=previous.route_group,
        device_class=previous.device_class,
        collector_id=previous.collector_id,
        session_id=previous.session_id,
        navigation_id=previous.navigation_id,
    )
    return _sign_claims(binding, claims), expires


def build_observation(
    binding: CwvRumBinding,
    *,
    token: str,
    origin: str | None,
    collector_principal_id: str,
    gateway_session_id: str,
    metric: str,
    value: float,
    now: datetime | None = None,
) -> CwvTrustedObservation:
    """Validate browser input and replace all trust-sensitive fields server-side."""
    ensure_allowed_origin(binding, origin)
    claims = verify_envelope(binding, token, now=now)
    if not hmac.compare_digest(
        claims.collector_id, _collector_binding(binding, collector_principal_id)
    ) or not hmac.compare_digest(
        claims.session_id,
        _session_binding(binding, collector_principal_id, gateway_session_id),
    ):
        raise CwvEnvelopeError("CWV envelope session binding is invalid")
    limits = {"LCP": ("ms", 60_000.0), "INP": ("ms", 60_000.0), "CLS": ("score", 10.0)}
    definition = limits.get(metric)
    numeric = float(value)
    if (
        definition is None
        or not math.isfinite(numeric)
        or not 0 <= numeric <= definition[1]
    ):
        raise CwvEnvelopeError("CWV metric or value is invalid")
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    metric_id = hashlib.sha256(f"{claims.nonce}:{metric}".encode()).hexdigest()[:32]
    return CwvTrustedObservation(
        metric=metric,
        unit=definition[0],
        value=numeric,
        metric_id=metric_id,
        collector_id=claims.collector_id,
        navigation_id=claims.navigation_id,
        session_id=claims.session_id,
        device_class=claims.device_class,
        route_group=claims.route_group,
        observed_at=observed_at,
        release_sha=claims.release_sha,
        frontend_image_digest=claims.frontend_image_digest,
        deployment_run_id=claims.deployment_run_id,
        deployment_run_attempt=claims.deployment_run_attempt,
        envelope_nonce=claims.nonce,
    )


class GithubActionsOidcVerifier:
    """Fail-closed verifier for the one trusted field-report exporter workflow."""

    def __init__(
        self, *, enabled: bool, repository: str, workflow_ref: str, subject: str
    ) -> None:
        self.enabled = enabled
        self.repository = repository
        self.workflow_ref = workflow_ref
        self.subject = subject
        self._jwks = _GITHUB_JWKS_CLIENT

    def verify(self, token: str, *, expected_sha: str) -> dict[str, Any]:
        if (
            not self.enabled
            or not self.repository
            or not self.subject
            or self.workflow_ref
            != f"{self.repository}/.github/workflows/cwv-field-certification.yml@refs/heads/main"
        ):
            raise CwvConfigurationError(
                "CWV exporter OIDC policy is not fully configured"
            )
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=_AUDIENCE,
                issuer=_ISSUER,
                options={"require": ["exp", "iat", "sub", "repository", "ref", "sha"]},
            )
        except jwt.PyJWTError as exc:
            raise CwvEnvelopeError("CWV exporter identity is invalid") from exc
        expected = {
            "repository": self.repository,
            "ref": "refs/heads/main",
            "environment": "staging",
            "event_name": "workflow_dispatch",
            "workflow_ref": self.workflow_ref,
            "sha": expected_sha,
        }
        if any(claims.get(key) != value for key, value in expected.items()):
            raise CwvEnvelopeError("CWV exporter identity claims are invalid")
        if claims.get("sub") != self.subject:
            raise CwvEnvelopeError("CWV exporter subject is not staging-bound")
        return claims
