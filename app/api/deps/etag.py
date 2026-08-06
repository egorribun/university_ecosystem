from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import Request, Response, status

from app.core.localization import normalize_locale, resolve_locale
from app.core.tenant import get_current_tenant
from app.deps.cache import etag_matches, format_etag, get_cache


def generate_cache_key(
    cache_prefix: str, version: str, locale: str, params: dict[str, Any]
) -> str:
    """
    Unified cache key generator that matches the logic used in cached_endpoint.
    Uses SHA256 of the sorted JSON-serialized parameters for robustness.
    """
    import hashlib
    import json

    signature = json.dumps(
        params,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")

    digest = hashlib.sha256(signature).hexdigest()
    normalized_version = str(version or "0").strip() or "0"
    normalized_locale = normalize_locale(locale)

    return f"{cache_prefix}:{normalized_version}:{normalized_locale}:{digest}"


def _set_language_headers(response: Response, locale: str) -> None:
    response.headers["Content-Language"] = locale

    # Inline _ensure_vary_header logic here to prevent circular imports with app.main
    vary = response.headers.get("Vary")
    if not vary:
        response.headers["Vary"] = "Accept-Language"
    elif "Accept-Language" not in vary:
        response.headers["Vary"] = f"{vary}, Accept-Language"


def cached_endpoint(
    version_resolver: Any,
    cache_prefix: str,
    cache_control: str = "private, max-age=180",
) -> Callable[..., Any]:
    """
    A unified decorator for FastAPI endpoints to handle ETag-based HTTP caching
    and automatically respond with 304 Not Modified when appropriate, adhering
    to DRY and SRP principles.

    Expects the endpoint to return the raw payload (DTO or dict). The decorator
    handles JSON serialization via Pydantic model_dump_json(), ETag hashing,
    and cache setting.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request")
            response: Response | None = kwargs.get("response")

            if not request or not response:
                # If the decorated endpoint forgot to include Request and Response in its signature,
                # we just skip the caching middleware to avoid crashing.
                return await func(*args, **kwargs)

            # 1. Resolve Locale
            # Attempt to extract user from kwargs if injected by Depends(get_current_user)
            user = kwargs.get("user")
            locale = resolve_locale(request=request, user=user)

            # Extract manually passed headers if the endpoint signature defined them
            if_none_match = kwargs.get("if_none_match") or request.headers.get(
                "if-none-match"
            )

            _set_language_headers(response, locale)
            response.headers["Cache-Control"] = cache_control

            # 2. Check Cache
            cache = get_cache()
            cache_key: str | None = None

            # Only apply caching logic for GET requests
            if cache.enabled and request.method in ("GET", "HEAD"):
                version = await version_resolver.get_version(cache)

                # Reconstruct the cache key based on the dynamic endpoint arguments.
                # FastAPI internals and services are excluded below.  The user
                # identity is reintroduced after filtering because some payloads
                # contain private fields such as `is_registered` or `is_liked`.
                # Omitting it would let one user's response populate a shared
                # cache key for every other user (SEC-09).
                cacheable_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if k
                    not in (
                        "request",
                        "response",
                        "user",
                        "db",
                        "events",
                        "checker",
                        "if_none_match",
                        "background",
                        "notifications",
                    )
                }

                if user is not None:
                    user_id = getattr(user, "id", None)
                    if user_id is not None:
                        cacheable_kwargs["__authenticated_user_id"] = str(user_id)

                # Tenant-scoped rows are protected by RLS at the database layer,
                # but a cache hit bypasses that query entirely. Include the
                # request's tenant context so one tenant can never receive a
                # cached payload populated by another tenant (SEC-09).
                cacheable_kwargs["__tenant_id"] = get_current_tenant()

                cache_key = generate_cache_key(
                    cache_prefix=cache_prefix,
                    version=str(version),
                    locale=locale,
                    params=cacheable_kwargs,
                )

                cached = await cache.get(cache_key)
                if cached:
                    etag_header = format_etag(cached.etag)
                    if etag_matches(cached.etag, if_none_match):
                        not_modified = Response(
                            status_code=status.HTTP_304_NOT_MODIFIED
                        )
                        not_modified.headers["ETag"] = etag_header
                        not_modified.headers["Cache-Control"] = cache_control
                        _set_language_headers(not_modified, locale)
                        return not_modified
                    response.headers["ETag"] = etag_header
                    return cached.payload

            # 3. Execute Core Business Logic
            payload = await func(*args, **kwargs)

            # If the endpoint returned a raw Starlette Response (e.g., streaming), return it immediately
            if isinstance(payload, Response):
                return payload

            # 4. Process the Payload (PERF-02 Optimization)
            # Instead of jsonable_encoder + orjson.dumps, we use Pydantic's Rust-backed serializer if possible.
            import hashlib

            is_pydantic = hasattr(payload, "model_dump_json")
            if is_pydantic:
                serialized_bytes = payload.model_dump_json(by_alias=True).encode(
                    "utf-8"
                )
            elif (
                isinstance(payload, list)
                and len(payload) > 0
                and hasattr(payload[0], "model_dump_json")
            ):
                # Handle lists of Pydantic models
                # Construct JSON array string manually to keep Rust speed for inner objects
                inner = ",".join(
                    item.model_dump_json(by_alias=True) for item in payload
                )
                serialized_bytes = f"[{inner}]".encode()
            else:
                # Fallback for standard dicts
                import orjson
                from fastapi.encoders import jsonable_encoder

                encoded = jsonable_encoder(payload)
                serialized_bytes = orjson.dumps(encoded, option=orjson.OPT_SORT_KEYS)

            digest = hashlib.sha256(serialized_bytes).hexdigest()
            weak_header = f'"{format_etag(digest).strip(chr(34))}"'

            # 5. Populate Cache & Headers
            if cache.enabled and cache_key:
                import json

                # The cache.set expects dict/list for the Redis payload, not raw bytes.
                # Since we just serialized it to bytes, we parse it back. Fast enough in ujson/orjson,
                # but cache.set handles the final Redis serialization.
                parsed_payload = json.loads(serialized_bytes)
                entry = await cache.set(cache_key, parsed_payload)
                etag_header = format_etag(entry.etag)
                if etag_matches(entry.etag, if_none_match):
                    not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                    not_modified.headers["ETag"] = etag_header
                    not_modified.headers["Cache-Control"] = cache_control
                    _set_language_headers(not_modified, locale)
                    return not_modified

                final_response = Response(
                    content=serialized_bytes, media_type="application/json"
                )
                final_response.headers["ETag"] = etag_header
                final_response.headers["Cache-Control"] = cache_control
                _set_language_headers(final_response, locale)
                return final_response

            if etag_matches(digest, if_none_match):
                not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                not_modified.headers["ETag"] = weak_header
                not_modified.headers["Cache-Control"] = cache_control
                _set_language_headers(not_modified, locale)
                return not_modified

            final_response = Response(
                content=serialized_bytes, media_type="application/json"
            )
            final_response.headers["ETag"] = weak_header
            final_response.headers["Cache-Control"] = cache_control
            _set_language_headers(final_response, locale)
            return final_response

        return wrapper

    return decorator
