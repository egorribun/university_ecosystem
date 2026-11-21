"""Third-party integration schemas."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import (
    Field,
    field_validator,
)

from app.core.policies.csp import SPOTIFY_IMAGE_ORIGIN
from app.schemas.common import BaseModel

_SPOTIFY_IMAGE_URL_MAX_LENGTH = 2048


def is_spotify_image_url(value: object) -> bool:
    """Return True only for an https URL on the one image origin the CSP allows."""
    if not isinstance(value, str) or len(value) > _SPOTIFY_IMAGE_URL_MAX_LENGTH:
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return f"{parts.scheme}://{parts.netloc}" == SPOTIFY_IMAGE_ORIGIN


class SpotifyAuthURL(BaseModel):
    url: str


class SpotifyNowPlayingOut(BaseModel):
    is_playing: bool
    progress_ms: int | None = None
    duration_ms: int | None = None
    track_id: str | None = None
    track_name: str | None = None
    artists: list[str] = Field(default_factory=list, json_schema_extra={"default": []})
    album_name: str | None = None
    album_image_url: str | None = None
    track_url: str | None = None
    preview_url: str | None = None
    fetched_at: datetime

    @field_validator("album_image_url")
    @classmethod
    def _drop_unlisted_image_origin(cls, value: str | None) -> str | None:
        # Stored rows may predate the origin check; never send an image the
        # page's img-src would block.
        return value if is_spotify_image_url(value) else None
