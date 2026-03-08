from __future__ import annotations

import os

from pydantic import model_validator

from .base import BaseAppSettings

# Mirrors _DEVELOPMENT_ENVIRONMENTS from base.py to avoid a circular import.
_DEV_ENVS: frozenset[str] = frozenset(
    {"dev", "development", "local", "test", "testing"}
)


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

    # Elasticsearch — requires xpack.security (ELASTIC_PASSWORD must be set in production)
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_user: str = "elastic"
    elasticsearch_password: str = ""

    # ws-hub internal API (TD-NEW-07: cache invalidation on participant removal)
    ws_hub_internal_url: str = "http://ws-hub:8081"
    ws_hub_internal_secret: str = ""  # Must match WS_HUB_INTERNAL_SECRET in ws-hub config

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "IntegrationSettings":
        """Fail-fast on startup if critical secrets are missing in production.

        R-01 (audit 2026-03-08): Guards against operators deploying with empty or
        default-value secrets — services would start silently in an insecure state.
        Uses os.environ directly (not self.environment) to avoid depending on
        field ordering in pydantic-settings' multi-inheritance resolution.
        CI environments are also exempted to avoid breaking CI pipelines.
        """
        env_name = os.environ.get("ENVIRONMENT", "development").lower()
        is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
        if env_name in _DEV_ENVS or is_ci:
            return self

        errors: list[str] = []

        if not self.elasticsearch_password:
            errors.append(
                "ELASTICSEARCH_PASSWORD is required in production. "
                "Unauthenticated Elasticsearch access exposes all indexed data."
            )

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

        if errors:
            raise ValueError(
                "Production secret validation failed:\n"
                + "\n".join(f"  · {e}" for e in errors)
            )
        return self
