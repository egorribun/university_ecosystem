from __future__ import annotations

import os

from pydantic import Field, field_validator, model_validator

from .base import _DEVELOPMENT_ENVIRONMENTS, BaseAppSettings, _load_file_secret


class IntegrationSettings(BaseAppSettings):
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_token_secret: str = ""
    # RZ-002 (audit 2026-03-04): dedicated secret for short-lived OAuth2 state
    # JWTs.  Must NOT be the main JWT signing key — state tokens are externally
    # supplied by the Spotify callback and a confused-deputy attack could allow
    # crafting a valid access token if both use the same key.
    # Default falls back to spotify_token_secret for backward-compat during
    # rollout.  Set SPOTIFY_OAUTH_STATE_SECRET in production .env.
    spotify_oauth_state_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/spotify/callback"
    spotify_scopes: str = "user-read-currently-playing user-read-playback-state"
    rust_optimizer_url: str = "http://rust-optimizer:8080"
    spicedb_endpoint: str = "spicedb:50051"
    spicedb_preshared_key: str = "development-preshared-key"
    flagd_host: str = "localhost"
    flagd_port: int = Field(default=8013, ge=1, le=65535)

    # Elasticsearch — requires xpack.security (ELASTIC_PASSWORD must be set in production)
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_user: str = "elastic"
    elasticsearch_password: str = ""

    # ws-hub internal API (TD-NEW-07: cache invalidation on participant removal)
    ws_hub_internal_url: str = "http://ws-hub:8081"
    ws_hub_internal_secret: str = (
        ""  # Must match WS_HUB_INTERNAL_SECRET in ws-hub config
    )

    # RZ-W10-11: HMAC secret for idempotency key generation.
    # Signs (chat_id:user_id:client_key) so that idempotency keys cannot be
    # enumerated by an observer who can read the Idempotency-Key request header.
    # Default empty string falls back to plain BLAKE2b for backward-compat.
    # Must be set in production via IDEMPOTENCY_HMAC_SECRET env var.
    idempotency_hmac_secret: str = ""

    # RZ-20-02 (audit 2026-03-24): Support Docker Secrets / Kubernetes Secrets
    # via the *_FILE convention.  This keeps plaintext secrets out of environment
    # variables (visible in `docker inspect` and `/proc/*/environ`).
    @field_validator("spotify_client_secret", mode="before")
    @classmethod
    def _load_spotify_secret(cls, v: str | None) -> str | None:
        return _load_file_secret("SPOTIFY_CLIENT_SECRET_FILE", v)

    @field_validator("spicedb_preshared_key", mode="before")
    @classmethod
    def _load_spicedb_key(cls, v: str | None) -> str | None:
        return _load_file_secret("SPICEDB_PRESHARED_KEY_FILE", v)

    @field_validator("elasticsearch_password", mode="before")
    @classmethod
    def _load_es_password(cls, v: str | None) -> str | None:
        return _load_file_secret("ELASTICSEARCH_PASSWORD_FILE", v)

    @field_validator("ws_hub_internal_secret", mode="before")
    @classmethod
    def _load_ws_hub_secret(cls, v: str | None) -> str | None:
        return _load_file_secret("WS_HUB_INTERNAL_SECRET_FILE", v)

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> IntegrationSettings:
        """Fail-fast on startup if critical secrets are missing in production.

        R-01 (audit 2026-03-08): Guards against operators deploying with empty or
        default-value secrets — services would start silently in an insecure state.
        Uses os.environ directly (not self.environment) to avoid depending on
        field ordering in pydantic-settings' multi-inheritance resolution.
        CI environments are also exempted to avoid breaking CI pipelines.
        """
        env_name = os.environ.get("ENVIRONMENT", "development").lower()
        is_ci = (
            os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
        )

        errors: list[str] = []

        # RZ-W9-05: Enforce Elasticsearch authentication in production.
        # An empty password means unauthenticated ES access regardless of env.
        # Network-level isolation (docker-compose removing port 9200 from the
        # public network) is defence-in-depth, not a substitute for auth.
        # Developers running ES locally (outside Docker) with no password expose
        # all indexed data on localhost:9200 without any access control.
        # CI and dev/testing environments are exempted (no real ES instance).
        if (
            not self.elasticsearch_password
            and not is_ci
            and env_name not in _DEVELOPMENT_ENVIRONMENTS
        ):
            errors.append(
                "ELASTICSEARCH_PASSWORD is required in all environments. "
                "An empty password allows unauthenticated Elasticsearch access. "
                "Set ELASTICSEARCH_PASSWORD in your .env or docker-compose override."
            )

        if env_name in _DEVELOPMENT_ENVIRONMENTS or is_ci:
            # Remaining checks are production-only.
            return self

        if self.spicedb_preshared_key == "development-preshared-key":
            errors.append(
                "SPICEDB_PRESHARED_KEY must not use the default development value. "
                "Authorization decisions would be trivially bypassable."
            )

        # CONFIG-01 corollary: empty oauth state secret falls back to token secret —
        # a confused-deputy attack could allow crafting a valid access token from
        # a state token, since both are externally-supplied and user-controlled.
        if self.spotify_client_id and not self.spotify_oauth_state_secret:
            errors.append(
                "SPOTIFY_OAUTH_STATE_SECRET must be set when Spotify is enabled. "
                "Sharing the state secret with spotify_token_secret enables "
                "confused-deputy attacks (state token → access token forgery)."
            )

        # RZ-W8-04: ws-hub cache invalidation endpoint is protected by this secret.
        # An empty value makes the endpoint unauthenticated — any internal actor
        # can POST to /internal/cache/invalidate and force all users offline.
        if not self.ws_hub_internal_secret:
            errors.append(
                "WS_HUB_INTERNAL_SECRET must be set in production. "
                "An empty value leaves the ws-hub cache-invalidation endpoint "
                "unauthenticated, allowing any internal actor to force users offline."
            )

        if errors:
            raise ValueError(
                "Production secret validation failed:\n"
                + "\n".join(f"  · {e}" for e in errors)
            )
        return self
