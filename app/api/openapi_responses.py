"""Shared OpenAPI descriptions for client errors that middleware or guards return.

Each entry documents a 4xx that the request path can really produce; attach only
the ones that apply to a route. They describe existing behaviour and change none.
"""

from __future__ import annotations

from typing import Any

ResponseDocs = dict[int | str, dict[str, Any]]

# TrustedHostMiddleware rejects a Host header outside ALLOWED_HOSTS on every route.
INVALID_HOST: ResponseDocs = {
    400: {"description": "The Host header is not one of the allowed hosts"}
}
UNAUTHENTICATED: ResponseDocs = {
    401: {"description": "Not authenticated, or the session is invalid or expired"}
}
# CSRFMiddleware guards every unsafe method outside its exempt prefixes.
CSRF_REJECTED: ResponseDocs = {
    403: {"description": "The CSRF token is missing or does not match the cookie"}
}
ADMIN_FORBIDDEN: ResponseDocs = {
    403: {"description": "The authenticated user lacks the global admin permission"}
}
RATE_LIMITED: ResponseDocs = {
    429: {"description": "Rate limit exceeded; retry after the Retry-After interval"}
}


def combine(*parts: ResponseDocs) -> ResponseDocs:
    """Merge response documentation; a repeated status keeps both descriptions."""
    merged: ResponseDocs = {}
    for part in parts:
        for status_code, doc in part.items():
            if status_code in merged:
                first = merged[status_code]["description"]
                merged[status_code] = {
                    "description": f"{first}; or {doc['description']}"
                }
            else:
                merged[status_code] = dict(doc)
    return merged
