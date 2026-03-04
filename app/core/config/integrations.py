from __future__ import annotations

from .base import BaseAppSettings


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
