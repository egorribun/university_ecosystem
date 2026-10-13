"""Unit tests for ``cached_endpoint`` + ``generate_cache_key`` (app/api/deps/etag.py).

``cached_endpoint`` carries production HTTP caching for list endpoints
(news/events/schedule): ETag-based 304s, locale-aware ``Vary``/``Content-Language``
headers, payload serialization (Pydantic model / list-of-Pydantic / dict fallback),
and cache populate. We exercise it hermetically with a REAL in-memory cache
(``MemoryCache``, ``enabled=True``) or ``NullCache`` (``enabled=False``) plus a stub
``version_resolver`` — no Redis, no FastAPI app — so it sidesteps the SQLite/Postgres
partition tier entirely.
"""

from __future__ import annotations

from typing import Any

import orjson
import pytest
from fastapi import Request, Response
from pydantic import BaseModel

from app.api.deps.etag import cached_endpoint, generate_cache_key
from app.core.tenant import get_current_tenant, set_current_tenant, tenant_id_ctx
from app.deps.cache import MemoryCache, NullCache, set_cache_backend


class _Item(BaseModel):
    a: int
    b: str = "x"


class _StubVersionResolver:
    """Duck-types the ``version_resolver`` the decorator awaits."""

    def __init__(self, version: str = "1") -> None:
        self._version = version

    async def get_version(self, _cache: Any) -> str:
        return self._version


def _build_request(
    *,
    method: str = "GET",
    if_none_match: str | None = None,
    accept_language: str | None = "en",
    cookie: str | None = None,
    authorization: str | None = None,
) -> Request:
    """Minimal ASGI ``Request`` mirroring tests/test_etag.py::_build_request."""
    headers: list[tuple[bytes, bytes]] = []
    if if_none_match is not None:
        headers.append((b"if-none-match", if_none_match.encode("latin-1")))
    if accept_language is not None:
        headers.append((b"accept-language", accept_language.encode("latin-1")))
    if cookie is not None:
        headers.append((b"cookie", cookie.encode("latin-1")))
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    scope = {
        "type": "http",
        "method": method,
        "path": "/x",
        "raw_path": b"/x",
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)  # type: ignore[arg-type]


def _decorate(version: str = "1", cache_control: str = "private, max-age=180") -> Any:
    return cached_endpoint(
        version_resolver=_StubVersionResolver(version),
        cache_prefix="test",
        cache_control=cache_control,
    )


@pytest.fixture(autouse=True)
def _reset_cache_backend() -> Any:
    # Each test injects its own backend; restore the default resolver afterwards
    # so get_cache() rebuilds from settings (NullCache under CACHE_ENABLED=false).
    yield
    set_cache_backend(None)


# ── 1. Missing Request/Response → caching skipped ────────────────────────────


@pytest.mark.asyncio
async def test_skips_caching_when_request_or_response_missing() -> None:
    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    # Neither injected → raw payload, no Response wrapping.
    assert await endpoint() == {"a": 1}
    # Only request present (response missing) → still skipped.
    assert await endpoint(request=_build_request()) == {"a": 1}


# ── 2. Cache disabled (NullCache) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_disabled_returns_200_with_etag_and_language_headers() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    out = await endpoint(request=_build_request(), response=Response())
    assert isinstance(out, Response)
    assert out.status_code == 200
    assert out.headers["ETag"].startswith('"')
    assert out.headers["Cache-Control"] == "private, max-age=180"
    assert "Content-Language" in out.headers
    _assert_identity_vary(out)
    # dict fallback serialization path.
    assert out.body == orjson.dumps({"a": 1}, option=orjson.OPT_SORT_KEYS)


@pytest.mark.asyncio
async def test_cache_disabled_returns_304_on_matching_if_none_match() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    first = await endpoint(request=_build_request(), response=Response())
    etag = first.headers["ETag"]
    second = await endpoint(
        request=_build_request(if_none_match=etag), response=Response()
    )
    assert second.status_code == 304
    assert second.body == b""
    assert second.headers["ETag"] == etag
    assert second.headers["Cache-Control"] == "private, max-age=180"
    _assert_identity_vary(second)


# ── 3. Cache enabled (MemoryCache) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_enabled_miss_executes_then_hit_returns_cached_payload() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)
    calls = {"n": 0}

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        calls["n"] += 1
        return {"a": 1}

    out = await endpoint(request=_build_request(), response=Response())
    assert isinstance(out, Response)
    assert out.status_code == 200
    assert calls["n"] == 1

    # Identical kwargs → identical cache key → hit, no re-execution.
    out2 = await endpoint(request=_build_request(), response=Response())
    assert calls["n"] == 1
    assert out2 == {"a": 1}  # cached.payload returned raw


@pytest.mark.asyncio
async def test_authenticated_identity_is_private_and_cache_key_isolated() -> None:
    """HTTP and Redis caches must keep identity-specific responses separated."""
    cache = MemoryCache()
    set_cache_backend(cache)
    calls = {"n": 0}

    class _User:
        def __init__(self, user_id: str) -> None:
            self.id = user_id

    @cached_endpoint(
        version_resolver=_StubVersionResolver(),
        cache_prefix="identity-test",
        cache_control="public, max-age=60",
    )
    async def endpoint(*, user: _User, **_kwargs: Any) -> dict[str, str]:
        calls["n"] += 1
        return {"user_id": user.id}

    user_a = _User("user-a")
    user_b = _User("user-b")
    a_headers = {"cookie": "session=a", "authorization": "Bearer a"}
    b_headers = {"cookie": "session=b", "authorization": "Bearer b"}
    first = await endpoint(
        request=_build_request(**a_headers), response=Response(), user=user_a
    )
    second = await endpoint(
        request=_build_request(**b_headers), response=Response(), user=user_b
    )
    third_response = Response()
    third = await endpoint(
        request=_build_request(**a_headers), response=third_response, user=user_a
    )

    assert first.body == b'{"user_id":"user-a"}'
    assert second.body == b'{"user_id":"user-b"}'
    assert first.headers["Cache-Control"] == "private, no-store"
    assert second.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(first)
    _assert_identity_vary(second)
    assert third == {"user_id": "user-a"}
    assert third_response.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(third_response)
    not_modified = await endpoint(
        request=_build_request(if_none_match=first.headers["ETag"], **a_headers),
        response=Response(),
        user=user_a,
    )
    assert not_modified.status_code == 304
    assert not_modified.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(not_modified)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_tenant_context_is_part_of_cache_identity() -> None:
    """A tenant must never receive another tenant's cached payload."""
    cache = MemoryCache()
    set_cache_backend(cache)
    calls = {"n": 0}

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, str]:
        calls["n"] += 1
        return {"tenant_id": get_current_tenant()}

    tenant_a = set_current_tenant("tenant-a")
    try:
        first = await endpoint(request=_build_request(), response=Response())
    finally:
        # The explicit reset keeps this ContextVar isolated from later tests.
        tenant_id_ctx.reset(tenant_a)

    tenant_b = set_current_tenant("tenant-b")
    try:
        second = await endpoint(request=_build_request(), response=Response())
    finally:
        tenant_id_ctx.reset(tenant_b)

    assert first.body == b'{"tenant_id":"tenant-a"}'
    assert second.body == b'{"tenant_id":"tenant-b"}'
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_cache_enabled_hit_returns_304_on_match() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    first = await endpoint(request=_build_request(), response=Response())
    etag = first.headers["ETag"]
    second = await endpoint(
        request=_build_request(if_none_match=etag), response=Response()
    )
    assert second.status_code == 304
    assert second.headers["ETag"] == etag
    assert second.headers["Cache-Control"] == "private, max-age=180"
    _assert_identity_vary(second)


@pytest.mark.asyncio
async def test_cache_enabled_populate_branch_304_when_client_etag_matches_fresh() -> (
    None
):
    cache = MemoryCache()
    set_cache_backend(cache)

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    first = await endpoint(request=_build_request(), response=Response())
    etag = first.headers["ETag"]
    # Force a miss so the populate branch re-runs with a matching client ETag.
    cache._entries.clear()
    out = await endpoint(
        request=_build_request(if_none_match=etag), response=Response()
    )
    assert out.status_code == 304
    assert out.headers["ETag"] == etag


@pytest.mark.asyncio
async def test_non_get_method_bypasses_cache_lookup() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    out = await endpoint(request=_build_request(method="POST"), response=Response())
    assert out.status_code == 200
    # POST is not GET/HEAD → no cache_key computed → nothing stored.
    assert len(cache._entries) == 0


# ── 4. Payload serialization branches ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pydantic_payload_serialized_via_model_dump_json() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> _Item:
        return _Item(a=5, b="hi")

    out = await endpoint(request=_build_request(), response=Response())
    assert out.status_code == 200
    assert out.body == _Item(a=5, b="hi").model_dump_json(by_alias=True).encode("utf-8")


@pytest.mark.asyncio
async def test_list_of_pydantic_payload_serialized() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> list[_Item]:
        return [_Item(a=1), _Item(a=2)]

    out = await endpoint(request=_build_request(), response=Response())
    inner = ",".join(_Item(a=i).model_dump_json(by_alias=True) for i in (1, 2))
    assert out.body == f"[{inner}]".encode()


@pytest.mark.asyncio
async def test_list_of_dicts_uses_dict_fallback_branch() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> list[dict[str, int]]:
        return [{"a": 1}]  # list[0] has no model_dump_json → jsonable_encoder branch

    out = await endpoint(request=_build_request(), response=Response())
    assert out.body == orjson.dumps([{"a": 1}], option=orjson.OPT_SORT_KEYS)


@pytest.mark.asyncio
async def test_starlette_response_passthrough_not_cached() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)
    custom = Response(content=b"stream", media_type="text/plain")

    @_decorate()
    async def endpoint(**_kwargs: Any) -> Response:
        return custom

    out = await endpoint(request=_build_request(), response=Response())
    assert out is custom
    assert len(cache._entries) == 0


# ── 5. Locale / Vary header handling ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_existing_vary_header_is_appended() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    resp = Response()
    resp.headers["Vary"] = "Accept-Encoding"
    await endpoint(request=_build_request(), response=resp)
    assert resp.headers["Vary"] == (
        "Accept-Encoding, Accept-Language, Cookie, Authorization"
    )


@pytest.mark.asyncio
async def test_existing_accept_language_vary_not_duplicated() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    resp = Response()
    resp.headers["Vary"] = "Accept-Language"
    await endpoint(request=_build_request(), response=resp)
    assert resp.headers["Vary"] == "Accept-Language, Cookie, Authorization"


@pytest.mark.asyncio
async def test_vary_merge_deduplicates_case_insensitively_and_preserves_origin() -> (
    None
):
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> dict[str, int]:
        return {"a": 1}

    resp = Response()
    resp.headers["Vary"] = "oRiGiN, accept-language, ORIGIN, cOoKiE"
    await endpoint(request=_build_request(), response=resp)

    assert resp.headers["Vary"] == ("oRiGiN, accept-language, cOoKiE, Authorization")


# ── 6. generate_cache_key (standalone) ───────────────────────────────────────


def test_generate_cache_key_is_order_independent_and_structured() -> None:
    k1 = generate_cache_key("p", "3", "en", {"limit": 10, "cursor": "abc"})
    k2 = generate_cache_key("p", "3", "en", {"cursor": "abc", "limit": 10})
    assert k1 == k2  # sort_keys → param order does not matter
    parts = k1.split(":")
    assert parts[0] == "p"
    assert parts[1] == "3"
    assert len(parts) == 4  # prefix:version:locale:digest


def test_generate_cache_key_normalizes_blank_version_to_zero() -> None:
    assert generate_cache_key("p", "", "en", {}).split(":")[1] == "0"
    assert generate_cache_key("p", "0", "en", {}).split(":")[1] == "0"


def test_generate_cache_key_distinct_params_distinct_key() -> None:
    a = generate_cache_key("p", "1", "en", {"limit": 10})
    b = generate_cache_key("p", "1", "en", {"limit": 20})
    assert a != b


@pytest.mark.asyncio
async def test_public_anonymous_responses_vary_identity_on_miss_hit_and_304() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)
    calls = {"n": 0}
    public_policy = "public, max-age=60, stale-while-revalidate=120"

    @cached_endpoint(
        version_resolver=_StubVersionResolver(),
        cache_prefix="public-test",
        cache_control=public_policy,
    )
    async def endpoint(*, user: Any = None, **_kwargs: Any) -> dict[str, None]:
        calls["n"] += 1
        return {"user": None if user is None else user.id}

    first = await endpoint(request=_build_request(), response=Response(), user=None)
    assert isinstance(first, Response)
    assert first.status_code == 200
    assert first.headers["Cache-Control"] == public_policy
    _assert_identity_vary(first)

    hit_response = Response()
    hit = await endpoint(request=_build_request(), response=hit_response, user=None)
    assert hit == {"user": None}
    assert hit_response.headers["Cache-Control"] == public_policy
    _assert_identity_vary(hit_response)

    not_modified = await endpoint(
        request=_build_request(if_none_match=first.headers["ETag"]),
        response=Response(),
        user=None,
    )
    assert not_modified.status_code == 304
    assert not_modified.headers["Cache-Control"] == public_policy
    _assert_identity_vary(not_modified)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_nonpublic_tenant_response_uses_private_no_store() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)

    @_decorate(cache_control="public, max-age=60")
    async def endpoint(**_kwargs: Any) -> dict[str, str]:
        return {"tenant": get_current_tenant()}

    token = set_current_tenant("tenant-a")
    try:
        out = await endpoint(request=_build_request(), response=Response(), user=None)
    finally:
        tenant_id_ctx.reset(token)

    assert out.status_code == 200
    assert out.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(out)


@pytest.mark.asyncio
async def test_response_passthrough_receives_identity_cache_headers() -> None:
    set_cache_backend(NullCache())

    class _User:
        id = "user-a"

    @_decorate(cache_control="public, max-age=60")
    async def endpoint(**_kwargs: Any) -> Response:
        return Response(content=b"payload", headers={"Vary": "Origin"})

    out = await endpoint(
        request=_build_request(cookie="session=a", authorization="Bearer a"),
        response=Response(),
        user=_User(),
    )

    assert out.status_code == 200
    assert out.body == b"payload"
    assert out.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(out)
    assert "origin" in _vary_tokens(out)


def _vary_tokens(response: Response) -> set[str]:
    return {
        value.strip().casefold()
        for value in response.headers.get("Vary", "").split(",")
        if value.strip()
    }


def _assert_identity_vary(response: Response) -> None:
    assert {"cookie", "authorization", "accept-language"} <= _vary_tokens(response)


@pytest.mark.asyncio
async def test_anonymous_response_passthrough_preserves_explicit_cache_policy() -> None:
    set_cache_backend(NullCache())

    @_decorate(cache_control="public, max-age=60")
    async def endpoint(**_kwargs: Any) -> Response:
        return Response(
            content=b"payload",
            headers={"Cache-Control": "no-store", "Vary": "Origin"},
        )

    out = await endpoint(request=_build_request(), response=Response(), user=None)

    assert out.status_code == 200
    assert out.body == b"payload"
    assert out.headers["Cache-Control"] == "no-store"
    _assert_identity_vary(out)
    assert "origin" in _vary_tokens(out)


@pytest.mark.asyncio
async def test_anonymous_response_passthrough_gets_configured_policy_if_absent() -> (
    None
):
    set_cache_backend(NullCache())
    public_policy = "public, max-age=60"

    @_decorate(cache_control=public_policy)
    async def endpoint(**_kwargs: Any) -> Response:
        return Response(content=b"payload", headers={"Vary": "Origin"})

    out = await endpoint(request=_build_request(), response=Response(), user=None)

    assert out.status_code == 200
    assert out.headers["Cache-Control"] == public_policy
    _assert_identity_vary(out)
    assert "origin" in _vary_tokens(out)


@pytest.mark.asyncio
async def test_vary_wildcard_remains_a_standalone_dimension() -> None:
    set_cache_backend(NullCache())

    @_decorate()
    async def endpoint(**_kwargs: Any) -> Response:
        return Response(content=b"payload", headers={"Vary": "*, Origin, Cookie"})

    out = await endpoint(request=_build_request(), response=Response())

    assert out.headers["Vary"] == "*"


@pytest.mark.asyncio
async def test_idless_principal_stays_private_on_memory_cache_hit() -> None:
    cache = MemoryCache()
    set_cache_backend(cache)
    calls = {"n": 0}

    class _TransientPrincipal:
        id = None

    principal = _TransientPrincipal()
    public_policy = "public, max-age=60"

    @cached_endpoint(
        version_resolver=_StubVersionResolver(),
        cache_prefix="idless-principal-test",
        cache_control=public_policy,
    )
    async def endpoint(*, user: _TransientPrincipal, **_kwargs: Any) -> dict[str, str]:
        calls["n"] += 1
        return {"principal": "transient"}

    auth_headers = {"cookie": "session=idless", "authorization": "Bearer idless"}
    first = await endpoint(
        request=_build_request(**auth_headers), response=Response(), user=principal
    )
    assert isinstance(first, Response)
    assert first.body == b'{"principal":"transient"}'
    assert first.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(first)

    hit_response = Response()
    hit = await endpoint(
        request=_build_request(**auth_headers),
        response=hit_response,
        user=principal,
    )
    assert hit == {"principal": "transient"}
    assert hit_response.headers["Cache-Control"] == "private, no-store"
    _assert_identity_vary(hit_response)
    assert calls["n"] == 1
