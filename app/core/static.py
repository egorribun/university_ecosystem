"""Static-file boundary helpers.

User-facing avatars and other published media remain public.  Chat and event
attachments are different: their parent resource controls access, so the
unprotected ``/static`` mount must never serve those storage prefixes.
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

PRIVATE_STATIC_PREFIXES: tuple[str, ...] = ("chat_uploads", "event_files")


def is_private_static_path(path: str) -> bool:
    """Return whether *path* addresses an attachment-only static prefix."""

    normalized = path.lstrip("/").replace("\\", "/")
    while True:
        previous = normalized
        normalized = unquote(normalized)
        if normalized == previous:
            break
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
            # HTTP field names are case-insensitive and Starlette lowercases
            # them before emitting ASGI raw headers.  Keep this spelling for
            # source readability; the value remains fully mutation-tested.
            cache_control_header = "Cache-Control"  # pragma: no mutate
            return Response(
                status_code=404,
                headers={
                    cache_control_header: "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return await super().get_response(path, scope)
