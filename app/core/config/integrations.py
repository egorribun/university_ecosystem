from __future__ import annotations

from .base import BaseAppSettings


class IntegrationSettings(BaseAppSettings):
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_token_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/spotify/callback"
    spotify_scopes: str = "user-read-currently-playing user-read-playback-state"
    rust_optimizer_url: str = "http://rust-optimizer:8080"
    spicedb_endpoint: str = "spicedb:50051"
    spicedb_preshared_key: str = "development-preshared-key"
