import hashlib

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.validation import raise_http_error, raise_not_found
from app.core.config import settings
from app.core.logging import get_logger
from app.core.ratelimit import sensitive_route_limit
from app.services.image_proxy import get_transformed_image
from app.utils.files import _get_storage_backend

router = APIRouter(tags=["images"])
logger = get_logger(__name__)

# LOW-W19: moved from inside the handler body to module level so the tuple is
# constructed once at import time rather than on every image request.
# TD-W5-05: User-generated content (avatars, uploads) must use a short TTL so
# GDPR deletion requests are honoured within a reasonable window.
_USER_CONTENT_PREFIXES = ("avatars/", "users/", "uploads/", "profile/")


@router.get(
    "/img/{path:path}",
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_static))
    ],
)
async def proxy_image(
    request: Request,
    path: str,
    w: int | None = Query(None, alias="w", ge=1, le=2000),
    accept: str | None = Header(None),
) -> Response:
    """
    Public image proxy endpoint.
    Retrieves an image from storage, optimizes it for the requesting browser,
    and applies optional resizing.
    """
    if not settings.image_proxy_enabled:
        # Using a generic 404 per security best practices or explicit 404
        # Since logic asked for 404, we'll stick to not found-ish or just http error
        # "Image proxy is disabled" - usually 404 is good to hide existence
        # Defaulting to en for system errors where no user locale is typically resolved
        # in this public endpoint
        raise_not_found("endpoint", "en", resource_id="Image Proxy")

    # Validate and snap width to allowed buckets to prevent cache fragmentation
    target_width = None
    if w:
        allowed = settings.image_proxy_allowed_widths
        if isinstance(allowed, list) and allowed:
            # Snap to nearest allowed width
            target_width = min(allowed, key=lambda x: abs(x - w))
        else:
            target_width = w

    from typing import Literal

    # Determine optimal format based on Accept header
    format_pref: Literal["avif", "webp", "original"] = "original"
    if accept:
        # Priority: AVIF > WebP > Original
        if "image/avif" in accept:
            format_pref = "avif"
        elif "image/webp" in accept:
            format_pref = "webp"

    backend = _get_storage_backend()
    try:
        # Path might have leading slash from URL capturing,
        # strip it for backend compatibility
        normalized_path = path.lstrip("/")

        data, mime = await get_transformed_image(
            backend, normalized_path, width=target_width, format_preference=format_pref
        )

        # ETag: 16 hex chars of SHA-256 (64 bits) — sufficient for cache discrimination.
        etag = f'"{hashlib.sha256(data).hexdigest()[:16]}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})

        # Static/system assets (no user PII) can keep the long immutable TTL.
        is_user_content = normalized_path.startswith(_USER_CONTENT_PREFIXES)
        if is_user_content:
            cache_control = "private, max-age=86400"  # 1 day — GDPR-safe
        else:
            cache_control = "public, max-age=31536000, immutable"

        return Response(
            content=data,
            media_type=mime,
            headers={
                "Cache-Control": cache_control,
                "ETag": etag,
                "Vary": "Accept, bucket-width",  # Inform caching layers
                "x-image-proxy-cache": (
                    "HIT" if target_width else "MISS"
                ),  # Simplified indication
            },
        )
    except ValueError:
        # Often file not found in storage
        raise_not_found("image", "en", resource_id=path)
    except Exception:  # RZ-22-01-JUSTIFIED: convert-to-domain — converts any proxy error to HTTP 500 (reviewed TD-27-04)
        logger.exception("Image proxy error for %s", path)
        raise_http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "errors.common.internal_error", "en"
        )
