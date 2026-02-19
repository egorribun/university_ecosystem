"""JWT and token signing configuration mixin."""

from __future__ import annotations

import os
from functools import cached_property

from pydantic import ValidationInfo, field_validator

from app.core.config.base import (
    _DEVELOPMENT_ENVIRONMENTS,
    _coerce_str_list,
)


class JwtSettingsMixin:
    """JWT signing key management and token lifetime configuration.

    Provides key rotation support via JWT_SIGNING_KEYS (kid:secret pairs)
    and falls back to SECRET_KEY when no explicit signing keys are configured.
    """

    secret_key: str
    jwt_signing_keys: list[str] | str = ""
    jwt_active_kid: str | None = None
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    max_sessions_per_user: int = 5

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key_entropy(cls, v: str, info: ValidationInfo) -> str:
        if not v:
            raise ValueError("SECRET_KEY must not be empty")
        env = (
            info.data.get("environment") or os.environ.get("ENVIRONMENT", "development")
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
        env = (
            info.data.get("environment") or os.environ.get("ENVIRONMENT", "development")
        ).lower()
        if env not in _DEVELOPMENT_ENVIRONMENTS:
            for entry in keys:
                if ":" in entry:
                    _, secret = entry.split(":", 1)
                    if len(secret.strip()) < 32:
                        raise ValueError(
                            "JWT_SIGNING_KEYS entries must be at least 32 characters "
                            "long in production"
                        )
        return v

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
            entries.append((fallback_kid, self.secret_key))
        return entries

    @property
    def jwt_signing_key_registry(self) -> dict[str, str]:
        registry: dict[str, str] = {}
        for kid, secret in self._build_jwt_signing_key_entries():
            registry[kid] = secret
        return registry

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
