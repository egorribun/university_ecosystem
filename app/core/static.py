"""Static-file boundary helpers.

User-facing avatars and other published media remain public.  Chat and event
attachments are different: their parent resource controls access, so the
unprotected ``/static`` mount must never serve those storage prefixes.
"""

from __future__ import annotations

import posixpath
from urllib.parse import unquote

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

PRIVATE_STATIC_PREFIXES: tuple[str, ...] = (
    "chat_uploads",
    "event_files",
    "quarantine",
)
_CACHE_CONTROL_HEADER = "Cache-Control"


def is_private_static_path(path: str) -> bool:
    """Return whether *path* addresses an attachment-only static prefix."""

    normalized = path.lstrip("/").replace("\\", "/")
    while True:
        previous = normalized
        normalized = unquote(normalized)
        if normalized == previous:
            break
    # ``StaticFiles.lookup_path`` resolves dot-segments with
    # ``os.path.realpath`` before serving a file.  Normalize the same URL
    # shape here so an attachment prefix cannot be hidden behind a harmless
    # looking parent-directory segment (for example ``foo/../chat_uploads``).
    normalized = posixpath.normpath(normalized)
    if normalized.startswith("static/"):
        normalized = normalized[len("static/") :]
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in PRIVATE_STATIC_PREFIXES
    )


class PublicStaticFiles(StaticFiles):
    """Serve public media while failing closed for private attachment paths."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        if is_private_static_path(path):
            return Response(
                status_code=404,
                headers={
                    _CACHE_CONTROL_HEADER: "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return await super().get_response(path, scope)
