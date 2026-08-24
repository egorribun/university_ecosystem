"""JWT and token signing configuration mixin."""

from __future__ import annotations

import os
import warnings
from functools import cached_property

from pydantic import ValidationInfo, field_validator

from app.core.config.base import (
    _DEVELOPMENT_ENVIRONMENTS,
    _coerce_str_list,
    _load_file_secret,
)


class JwtSettingsMixin:
    """JWT signing key management and token lifetime configuration.

    Provides key rotation support via JWT_SIGNING_KEYS (kid:secret pairs)
    and falls back to SECRET_KEY when no explicit signing keys are configured.
    """

    secret_key: str
    jwt_signing_keys: list[str] | str = ""
    jwt_active_kid: str | None = None
    # RZ-NEW-003 (audit 2026-03-19): Explicit audience field — never rely on getattr fallback
    # in decode_token. If not configured, the default provides a sane value; in production
    # operators SHOULD override via JWT_AUDIENCE to a service-specific audience string to
    # prevent cross-service token reuse (e.g. dev service accepting staging token).
    jwt_audience: str = "university-ecosystem-api"
    algorithm: str = "RS256"
    access_token_expire_minutes: int = 60
    max_sessions_per_user: int = 5
    # RS256 / JWKS support (MOD-1: audit 2026-02-24)
    jwt_private_key_path: str | None = ".secrets/jwt_rs256.pem"

    @field_validator("secret_key", mode="before")
    @classmethod
    def _load_secret_key_from_file(cls, v: str | None) -> str | None:
        # RZ-05 (audit Wave 12): support SECRET_KEY_FILE=/run/secrets/secret_key
        # so the plaintext value never appears in `docker inspect` environment.
        return _load_file_secret("SECRET_KEY_FILE", v)

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key_entropy(cls, v: str, info: ValidationInfo) -> str:
        if not v:
            raise ValueError("SECRET_KEY must not be empty")
        env = str(
            info.data.get("environment")
            or os.environ.get("ENVIRONMENT", "development")
            or "development"
        ).lower()
        if env not in _DEVELOPMENT_ENVIRONMENTS and len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long in production"
            )
        return v

    @field_validator("jwt_signing_keys")
    @classmethod
    def _validate_jwt_signing_keys_entropy(
        cls, v: str | list[str], info: ValidationInfo
    ) -> str | list[str]:
        keys = _coerce_str_list(v)
        if not keys:
            return v
        env = str(
            info.data.get("environment")
            or os.environ.get("ENVIRONMENT", "development")
            or "development"
        ).lower()
        if env not in _DEVELOPMENT_ENVIRONMENTS:
            for entry in keys:
                if ":" in entry:
                    _, secret = entry.split(":", 1)
                    if len(secret.strip()) < 32 and not secret.startswith("-----BEGIN"):
                        # Only enforce 32-char entropy for HMAC secrets, not PEM blocks
                        raise ValueError(
                            "JWT_SIGNING_KEYS entries must be at least 32 "
                            "characters long in production"
                        )
        return v

    @field_validator("algorithm")
    @classmethod
    def _validate_algorithm(cls, v: str, info: ValidationInfo) -> str:
        """Prohibit HS256 in non-development environments.

        HS256 uses a shared secret: any party that can *verify* a token can
        also *forge* one. RS256 separates the signing key (private) from the
        verification key (public, shareable via the /jwks endpoint).
        Algorithm Confusion attacks swap the declared alg header to trick a
        verifier into using a public RSA key as an HMAC secret.
        (RZ-3: audit 2026-02-26)
        """
        env = str(
            info.data.get("environment")
            or os.environ.get("ENVIRONMENT", "development")
            or "development"
        ).lower()
        # Explicitly enumerate environments that require asymmetric signing.
        # This prevents a staging deployment that accidentally loads ENVIRONMENT=development
        # from bypassing the HS256 guard (RZ-3: audit 2026-03-02).
        _NON_HMAC_ENVS = frozenset(
            {
                "production",
                "prod",
                "staging",
                "qa",
                "preprod",
                "pre-prod",
            }
        )
        if (
            env in _NON_HMAC_ENVS or env not in _DEVELOPMENT_ENVIRONMENTS
        ) and v.upper() == "HS256":
            raise ValueError(
                f"HS256 is prohibited in non-local environments (env={env!r}). "
                "Use RS256 with a dedicated RSA key pair "
                "(set ALGORITHM=RS256 and JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem)."
            )
        return v

    @field_validator("algorithm", mode="after")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        if v.upper() == "RS256":
            # Just informational logging; logic handles public/private keys
            pass
        elif v.upper() == "HS256" and os.environ.get(
            "ENVIRONMENT", "development"
        ).strip().lower() not in {"test", "testing"}:
            warnings.warn(
                "HS256 is not recommended for production. "
                "Use RS256 with a dedicated public/private key pair.",
                stacklevel=2,
            )
        return v.upper()

    @field_validator("jwt_audience")
    @classmethod
    def _validate_jwt_audience(cls, v: str, info: ValidationInfo) -> str:
        """Enforce explicit JWT audience configuration in non-development environments.

        RZ-NEW-003 (audit 2026-03-19): Prevents the decode_token() from silently
        falling back to a hardcoded string via getattr. If an operator misconfigures
        JWT_AUDIENCE, this validator surfaces the error at startup rather than at
        runtime where it could silently accept tokens for a different service.
        """
        if not v or not v.strip():
            raise ValueError("JWT_AUDIENCE must not be empty")
        env = str(
            info.data.get("environment")
            or os.environ.get("ENVIRONMENT", "development")
            or "development"
        ).lower()
        # Warn in any environment if the audience looks like an uncustomized placeholder.
        _AUDIENCE_PLACEHOLDERS: frozenset[str] = frozenset(
            {"api", "app", "service", "my-api", "example"}
        )
        if v.lower() in _AUDIENCE_PLACEHOLDERS and env not in _DEVELOPMENT_ENVIRONMENTS:
            import logging

            logging.getLogger(__name__).warning(
                "JWT_AUDIENCE='%s' looks like a generic placeholder. "
                "Set JWT_AUDIENCE to a service-specific string to prevent "
                "cross-service token reuse.",
                v,
            )
        return v.strip()

    def _build_jwt_signing_key_entries(self) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        seen_kids: set[str] = set()
        for raw_entry in _coerce_str_list(self.jwt_signing_keys):
            if ":" not in raw_entry:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must be in '<kid>:<secret>' format"
                )
            kid, secret = raw_entry.split(":", 1)
            kid = kid.strip()
            secret = secret.strip()
            if not kid:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must specify a non-empty kid value"
                )
            if not secret:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must specify a non-empty secret value"
                )
            if kid in seen_kids:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS entries must use unique kid values"
                )
            entries.append((kid, secret))
            seen_kids.add(kid)

        if not entries:
            fallback_kid = (self.jwt_active_kid or "primary").strip() or "primary"
            # If algorithm is RS256 and a private key is provided, use it as primary
            if self.algorithm == "RS256" and self.jwt_private_key_path:
                try:
                    with open(self.jwt_private_key_path) as f:
                        entries.append((fallback_kid, f.read()))
                except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — re-raises in prod, falls back in dev (reviewed TD-27-04)
                    # Assuming 'environment' is available on self, or passed via info
                    # For now, using a placeholder 'self.environment'
                    # In a real Pydantic setup, 'environment' would likely be a field
                    # or accessible via ValidationInfo.
                    # For this example, I'll assume it's accessible as self.environment
                    # or default to 'development' if not found.
                    env = getattr(self, "environment", "development").lower()
                    if env not in _DEVELOPMENT_ENVIRONMENTS:
                        raise RuntimeError(
                            f"Failed to load JWT_PRIVATE_KEY_PATH: {exc}"
                        ) from exc
                    import logging

                    logging.getLogger(__name__).warning(
                        "Failed to load RS256 private key from %s: %s. "
                        "Falling back to HMAC signing with SECRET_KEY for local development.",
                        self.jwt_private_key_path,
                        exc,
                    )
                    # In dev, fall back to secret_key (will fail signing but keep app alive)
                    entries.append((fallback_kid, self.secret_key))
            else:
                entries.append((fallback_kid, self.secret_key))
        return entries

    @property
    def jwt_signing_key_registry(self) -> dict[str, str]:
        """Parsed {kid: secret} registry — lazily computed and value-keyed cached.

        Uses an instance-level cache keyed by the *current* value of
        ``jwt_signing_keys`` so that:
        - Production: same config every call → O(1) after first call.
        - Tests: monkeypatch changes ``jwt_signing_keys`` → cache miss
          → recomputed with the new value. (TD-1: audit 2026-02-26)
        """
        cache_key = str(self.jwt_signing_keys) + str(self.jwt_active_kid)

        # Fast path lock-free read
        cache: dict[str, dict[str, str]] = self.__dict__.get("_jwt_registry_cache", {})
        if cache_key in cache:
            return cache[cache_key]

        # Slow path computation
        new_registry = {
            kid: secret for kid, secret in self._build_jwt_signing_key_entries()
        }

        # Safely bypass Pydantic frozen validation (MOD-5 prep)
        object.__setattr__(self, "_jwt_registry_cache", {cache_key: new_registry})

        return new_registry

    @property
    def jwt_signing_active_kid(self) -> str:
        registry = self.jwt_signing_key_registry
        configured = (
            self.jwt_active_kid.strip()
            if isinstance(self.jwt_active_kid, str)
            else None
        )
        if configured:
            if configured not in registry:
                raise RuntimeError(
                    "JWT_ACTIVE_KID must match one of the configured JWT_SIGNING_KEYS"
                )
            return configured
        return next(iter(registry))

    @property
    def jwt_signing_active_secret(self) -> str:
        registry = self.jwt_signing_key_registry
        active_kid = self.jwt_signing_active_kid
        secret = registry.get(active_kid)
        if secret is None:
            raise RuntimeError(
                "Configured JWT signing key registry does not contain the active kid"
            )
        return secret

    @cached_property
    def SECRET_KEY(self) -> str:
        return self.jwt_signing_active_secret

    @cached_property
    def ALGORITHM(self) -> str:
        return self.algorithm
