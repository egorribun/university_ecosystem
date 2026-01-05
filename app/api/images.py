from fastapi import APIRouter, Header, HTTPException, Query, Response

from app.core.config import settings
from app.services.image_proxy import get_transformed_image
from app.utils.files import _get_storage_backend

router = APIRouter(tags=["images"])


@router.get("/img/{path:path}")
async def proxy_image(
    path: str,
    w: int | None = Query(None, alias="w", ge=1, le=2000),
    accept: str | None = Header(None),
):
    """
    Public image proxy endpoint.
    Retrieves an image from storage, optimizes it for the requesting browser,
    and applies optional resizing.
    """
    if not settings.image_proxy_enabled:
        raise HTTPException(status_code=404, detail="Image proxy is disabled")

    # Validate and snap width to allowed buckets to prevent cache fragmentation
    target_width = None
    if w:
        allowed = settings.image_proxy_allowed_widths
        if isinstance(allowed, list) and allowed:
            # Snap to nearest allowed width
            target_width = min(allowed, key=lambda x: abs(x - w))
        else:
            target_width = w

    # Determine optimal format based on Accept header
    format_pref = "original"
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

        return Response(
            content=data,
            media_type=mime,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "Vary": "Accept, bucket-width",  # Inform caching layers
                "x-image-proxy-cache": (
                    "HIT" if target_width else "MISS"
                ),  # Simplified indication
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        from logging import getLogger

        getLogger(__name__).exception("Image proxy error for %s", path)
        raise HTTPException(status_code=500, detail="Internal image processing error")
