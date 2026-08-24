from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Literal
from urllib.parse import urljoin

from app.core.config import settings


def get_optimized_image_url(
    original_url: str | None,
    *,
    width: int | None = None,
    height: int | None = None,
    extension: Literal["avif", "webp", "jpg", "png"] | None = "avif",
    gravity: str = "sm",
    enlarge: bool = False,
    extend: bool = False,
) -> str | None:
    """
    Generate a signed imgproxy URL for the given original image URL.

    If imgproxy is not configured (missing keys) or the URL is empty,
    returns the original URL.
    """
    if not original_url:
        return None

    # Skip optimization if keys are missing
    if not settings.imgproxy_key or not settings.imgproxy_salt:
        return original_url

    # Local files might need to be prefixed with the backend URL
    # for imgproxy to fetch them
    full_source_url = original_url
    if original_url.startswith("/"):
        # For imgproxy to fetch it, we need to provide a full URL
        # We assume the app is accessible by imgproxy via its service name
        backend_url = "http://backend:8000"
        full_source_url = urljoin(backend_url, original_url)

    # Encode source URL
    source_url_encoded = (
        base64.urlsafe_b64encode(full_source_url.encode()).rstrip(b"=").decode()
    )

    # Build processing options
    # Refer to imgproxy documentation for more options
    resizing_type = "fit"
    width = width or 0
    height = height or 0

    options = (
        f"/rs:{resizing_type}:{width}:{height}:{int(enlarge)}:{int(extend)}/g:{gravity}"
    )
    if extension:
        path = f"{options}/{source_url_encoded}.{extension}"
    else:
        path = f"{options}/{source_url_encoded}"

    # Sign the path
    key = bytes.fromhex(settings.imgproxy_key)
    salt = bytes.fromhex(settings.imgproxy_salt)

    msg = salt + path.encode()
    signature = hmac.new(key, msg, hashlib.sha256).digest()
    signature_encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    # Build final URL
    # Do not use urljoin here: the signed path begins with "/", which would
    # silently discard a deployment prefix such as "/imgproxy".
    return f"{settings.imgproxy_base_url.rstrip('/')}/{signature_encoded}{path}"
