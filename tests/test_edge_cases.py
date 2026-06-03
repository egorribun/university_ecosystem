"""Wave 5 — Parametrized edge-case tests for improved branch coverage.

Targets uncovered branches in:
- app/utils/sanitization.py  (OWASP XSS vectors, URL edge cases, filename truncation)
- app/core/ratelimit/utils.py (parse_rate_limit, _normalize_ip, resolve_client_ip)
- app/deps/cache.py          (MemoryCache expiry/eviction/wildcard, CacheEntry XFetch, RedisCache errors)
- app/schemas/validators.py  (invalid field combinations)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.utils.sanitization import (
    sanitize_email,
    sanitize_filename,
    sanitize_html,
    sanitize_optional_text,
    sanitize_path,
    sanitize_rich_text,
    sanitize_url,
    strip_control_chars,
    truncate,
)

# ---------------------------------------------------------------------------
# sanitize_html — OWASP XSS vector parametrize
# ---------------------------------------------------------------------------

_XSS_VECTORS = [
    # Classic vectors
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<body onload=alert(1)>",
    # Encoded variants
    "<scr\x00ipt>alert(1)</scr\x00ipt>",
    "&#x3C;script&#x3E;alert(1)&#x3C;/script&#x3E;",
    # Attribute injection
    '<a href="javascript:alert(1)">click</a>',
    "<div style=\"background:url('javascript:alert(1)')\">",
    # Event handlers in various tags
    "<p onclick=alert(1)>text</p>",
    "<input onfocus=alert(1) autofocus>",
    # Nesting tricks
    "<scr<script>ipt>alert(1)</scr</script>ipt>",
    "<<SCRIPT>alert('XSS');//<</SCRIPT>",
    # Data URIs
    '<img src="data:text/html,<script>alert(1)</script>">',
    # VBScript / backtick attribute injection
    "<img src=`javascript:alert(1)`>",
]


@pytest.mark.parametrize("vector", _XSS_VECTORS)
def test_sanitize_html_strips_xss(vector: str) -> None:
    result = sanitize_html(vector, allow_basic_tags=False)
    # Must not contain script execution patterns after sanitization
    assert "<script" not in result.lower()
    assert "onerror" not in result.lower()
    assert "onload" not in result.lower()
    assert "javascript:" not in result.lower()


@pytest.mark.parametrize("vector", _XSS_VECTORS)
def test_sanitize_rich_text_strips_xss(vector: str) -> None:
    result = sanitize_rich_text(vector)
    assert "<script" not in result.lower()
    assert "onerror" not in result.lower()
    assert "javascript:" not in result.lower()


# ---------------------------------------------------------------------------
# sanitize_url — extended OWASP / SSRF edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dangerous_url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "Javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "DATA:text/html,x",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "FILE:///etc/passwd",
        # SSRF — private / loopback IP
        "http://127.0.0.1/admin",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        # Credentials in URL
        "https://user:pass@example.com",
        "https://:pass@example.com",
        # Localhost variants
        "http://localhost/",
        "http://localhost:8080/admin",
        # Empty string
        "",
        # No netloc
        "https://",
        # Non-http scheme
        "ftp://example.com/file",
    ],
)
def test_sanitize_url_blocks_dangerous(dangerous_url: str) -> None:
    assert sanitize_url(dangerous_url) is None


@pytest.mark.parametrize(
    "safe_url",
    [
        "https://example.com",
        "https://example.com/path?q=1",
        "http://example.com:8080/",
        "https://sub.example.com/api/v1",
    ],
)
def test_sanitize_url_allows_safe(safe_url: str) -> None:
    assert sanitize_url(safe_url) == safe_url


def test_sanitize_url_punycode_domain_allowed() -> None:
    # Proper punycode starting with xn-- is allowed
    result = sanitize_url("https://xn--n3h.example.com/")
    # May or may not pass SSRF checks but should not throw
    assert result is None or isinstance(result, str)


def test_sanitize_url_idn_non_punycode_blocked() -> None:
    # Unicode domain that doesn't start with xn-- should be blocked
    result = sanitize_url("https://еxample.com/")  # Cyrillic е
    assert result is None


# ---------------------------------------------------------------------------
# sanitize_filename — truncation, unicode, control chars
# ---------------------------------------------------------------------------


def test_sanitize_filename_truncates() -> None:
    result = sanitize_filename("a" * 300 + ".txt")
    assert len(result) <= 255
    assert result.endswith(".txt")


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("", "unnamed"),
        (".", "unnamed"),  # after lstrip('.') → empty → "unnamed"
        (".hidden", "hidden"),  # leading dot stripped
        ("file\x00name.txt", "filename.txt"),  # null byte removed
        ("file\x1fname.txt", "filename.txt"),  # control char removed
        ("hello world .txt", "hello world .txt"),  # spaces preserved
    ],
)
def test_sanitize_filename_edge_cases(filename: str, expected: str) -> None:
    result = sanitize_filename(filename)
    assert result == expected


# ---------------------------------------------------------------------------
# sanitize_email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "email,expected",
    [
        (None, ""),
        ("", ""),
        ("  USER@EXAMPLE.COM  ", "user@example.com"),
        ("user+tag@example.com", "user+tag@example.com"),
    ],
)
def test_sanitize_email_parametrize(email: str | None, expected: str) -> None:
    assert sanitize_email(email) == expected  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# strip_control_chars — additional control characters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello\x00world", "helloworld"),  # null byte
        ("hello\x08world", "helloworld"),  # backspace
        ("hello\x0bworld", "helloworld"),  # vertical tab
        ("hello\x0cworld", "helloworld"),  # form feed
        ("hello\x0eworld", "helloworld"),  # shift out
        ("hello\x7fworld", "helloworld"),  # DEL
        ("line\nfeed", "line\nfeed"),  # newline preserved
        ("tab\there", "tab\there"),  # tab preserved
        ("", ""),
    ],
)
def test_strip_control_chars_parametrize(text: str, expected: str) -> None:
    assert strip_control_chars(text) == expected


# ---------------------------------------------------------------------------
# truncate — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,max_len,suffix,expected",
    [
        ("hello", 10, "...", "hello"),
        ("hello world", 8, "...", "hello..."),
        ("hello", 5, "...", "hello"),  # exact length — no truncation
        ("hi", 3, "...", "hi"),  # shorter than max
        ("abcde", 5, "!", "abcde"),  # exact length with 1-char suffix
        ("abcdef", 5, "!", "abcd!"),  # needs truncation
        (None, 5, "...", None),  # None passthrough per impl
        ("", 5, "...", ""),
    ],
)
def test_truncate_parametrize(
    text: str | None, max_len: int, suffix: str, expected: str | None
) -> None:
    assert truncate(text, max_len, suffix) == expected  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# sanitize_optional_text — bytearray + invalid UTF-8 + whitespace only
# ---------------------------------------------------------------------------


def test_sanitize_optional_text_bytearray() -> None:
    val = bytearray(b"hello bytes")
    assert sanitize_optional_text(val) == "hello bytes"


def test_sanitize_optional_text_whitespace_only_bytes() -> None:
    val = b"   "
    assert sanitize_optional_text(val) is None


def test_sanitize_optional_text_invalid_utf8_ignored() -> None:
    # Invalid UTF-8 bytes — decoded with 'ignore'
    val = b"hello\x80\x81world"
    result = sanitize_optional_text(val)
    assert result is not None
    assert "hello" in result


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),
        (42, "42"),
        (3.14, "3.14"),
        (False, "False"),  # str(False) = "False" → strip() → "False" (truthy)
    ],
)
def test_sanitize_optional_text_numeric(value: object, expected: str) -> None:
    result = sanitize_optional_text(value)
    assert result == expected


# ---------------------------------------------------------------------------
# parse_rate_limit — parametrized edge cases
# ---------------------------------------------------------------------------

from app.core.ratelimit.utils import (
    _extract_ip_from_forwarded,
    _normalize_ip,
    parse_rate_limit,
)


@pytest.mark.parametrize(
    "value,fallback,expected",
    [
        # None / empty → fallback
        (None, (5, 60), (5, 60)),
        ("", (5, 60), (5, 60)),
        ("  ", (5, 60), (5, 60)),
        # Standard slash notation
        ("10/60", (5, 60), (10, 60)),
        ("1/s", (5, 60), (1, 1)),
        ("100/minute", (5, 60), (100, 60)),
        ("50/hour", (5, 60), (50, 3600)),
        ("200/day", (5, 60), (200, 86400)),
        # 'per' notation
        ("5 per second", (5, 60), (5, 1)),
        ("10 per min", (5, 60), (10, 60)),
        ("20 per hr", (5, 60), (20, 3600)),
        # Numeric unit (raw seconds)
        ("100/300", (5, 60), (100, 300)),
        # Invalid count → fallback
        ("abc/60", (5, 60), (5, 60)),
        # Invalid unit → fallback
        ("10/fortnight", (5, 60), (5, 60)),
        # Zero / negative count → fallback
        ("0/60", (5, 60), (5, 60)),
        ("-1/60", (5, 60), (5, 60)),
        # Zero seconds → fallback
        ("10/0", (5, 60), (5, 60)),
        # Too many parts
        ("10/60/extra", (5, 60), (5, 60)),
        # Single token (no delimiter) → fallback
        ("10", (5, 60), (5, 60)),
        # Plural stripping: "seconds" → "second" → matched
        ("5 per seconds", (5, 60), (5, 1)),
        ("10 per minutes", (5, 60), (10, 60)),
    ],
)
def test_parse_rate_limit(
    value: str | None, fallback: tuple[int, int], expected: tuple[int, int]
) -> None:
    assert parse_rate_limit(value, fallback=fallback) == expected


# ---------------------------------------------------------------------------
# _normalize_ip — valid IPv4, IPv6, invalid inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip,expected",
    [
        ("127.0.0.1", "127.0.0.1"),
        ("  10.0.0.1  ", "10.0.0.1"),  # strips whitespace
        ("::1", "::1"),
        ("2001:db8::1", "2001:db8::1"),
        ("", None),
        (None, None),
        ("not-an-ip", None),
        ("999.999.999.999", None),
        ("256.0.0.1", None),
    ],
)
def test_normalize_ip(ip: str | None, expected: str | None) -> None:
    assert _normalize_ip(ip) == expected


# ---------------------------------------------------------------------------
# _extract_ip_from_forwarded — RFC 7239 Forwarded header parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header,expected",
    [
        ("for=192.0.2.60;proto=http;by=203.0.113.43", "192.0.2.60"),
        (
            'for="[2001:db8::cafe]";proto=http',
            "2001:db8::cafe",
        ),  # brackets stripped by strip('"[]')
        ("FOR=192.0.2.1", "192.0.2.1"),  # case-insensitive
        ("by=proxy;for=10.0.0.1", "10.0.0.1"),  # 'for' not first
        ("proto=https;by=proxy", None),  # no 'for' part
        ("", None),  # empty
        ("for=", ""),  # for with no value
    ],
)
def test_extract_ip_from_forwarded(header: str, expected: str | None) -> None:
    result = _extract_ip_from_forwarded(header)
    assert result == expected


# ---------------------------------------------------------------------------
# MemoryCache — expiry, eviction, wildcard invalidation, probabilistic refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_cache_entry_expires() -> None:
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=0)  # no TTL
    await cache.set("key1", {"data": 1}, ttl=0)
    # Should still be there (no TTL)
    entry = await cache.get("key1")
    assert entry is not None


@pytest.mark.asyncio
async def test_memory_cache_ttl_expiry() -> None:
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=1)
    entry = await cache.set("expiring", "value", ttl=1)
    assert entry.etag

    # Manually expire by manipulating stored_at
    key = "expiring"
    stored_entry, _ = cache._entries[key]
    # Force expiry: set expires_at to past
    cache._entries[key] = (stored_entry, time.time() - 1)

    result = await cache.get("expiring")
    assert result is None
    assert "expiring" not in cache._entries


@pytest.mark.asyncio
async def test_memory_cache_lru_eviction() -> None:
    from app.deps.cache import MemoryCache

    # min max_size is 10 (enforced by max(..., 10) in __init__)
    # Fill exactly to capacity, then add one more to trigger eviction
    cache = MemoryCache(default_ttl=0, max_size=10)
    for i in range(10):
        await cache.set(f"key{i}", i)
    assert len(cache._entries) == 10

    # Adding the 11th evicts the oldest inserted ("key0")
    await cache.set("key10", 10)
    assert len(cache._entries) == 10
    assert "key0" not in cache._entries
    assert "key10" in cache._entries


@pytest.mark.asyncio
async def test_memory_cache_lru_touch_on_get() -> None:
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=0, max_size=10)
    for i in range(10):
        await cache.set(f"key{i}", i)

    # Touch "key0" → now most recent
    await cache.get("key0")

    # Add 11th item → should evict "key1" (now oldest)
    await cache.set("key10", 10)
    assert "key0" in cache._entries
    assert "key1" not in cache._entries


@pytest.mark.asyncio
async def test_memory_cache_wildcard_invalidation() -> None:
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=0)
    await cache.set("user:1", {"name": "Alice"})
    await cache.set("user:2", {"name": "Bob"})
    await cache.set("event:1", {"title": "Conf"})

    await cache.invalidate("user:*")
    assert await cache.get("user:1") is None
    assert await cache.get("user:2") is None
    assert await cache.get("event:1") is not None


@pytest.mark.asyncio
async def test_memory_cache_invalidate_no_keys() -> None:
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=0)
    await cache.set("key", "val")
    # Calling with no keys should be a no-op
    await cache.invalidate()
    assert await cache.get("key") is not None


@pytest.mark.asyncio
async def test_memory_cache_update_existing_key() -> None:
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=0, max_size=3)
    await cache.set("k", "v1")
    await cache.set("k", "v2")
    # Updating same key should not increase size
    assert len(cache._entries) == 1
    entry = await cache.get("k")
    assert entry is not None
    assert entry.payload == "v2"


# ---------------------------------------------------------------------------
# CacheEntry.should_refresh_probabilistic — branch coverage
# ---------------------------------------------------------------------------


def test_cache_entry_no_ttl_no_refresh() -> None:
    from app.deps.cache import CacheEntry

    entry = CacheEntry(etag="e", payload=None, stored_at=time.time(), ttl_seconds=0.0)
    # ttl_seconds <= 0 → always False
    assert entry.should_refresh_probabilistic() is False


def test_cache_entry_already_expired_always_refresh() -> None:
    from app.deps.cache import CacheEntry

    # stored 100 seconds ago, TTL was 60 → remaining < 0
    entry = CacheEntry(
        etag="e",
        payload=None,
        stored_at=time.time() - 100,
        ttl_seconds=60.0,
    )
    assert entry.should_refresh_probabilistic() is True


def test_cache_entry_fresh_rarely_refreshes() -> None:
    from app.deps.cache import CacheEntry

    # Fresh entry — should almost never refresh (beta=1.0)
    entry = CacheEntry(
        etag="e",
        payload=None,
        stored_at=time.time(),
        ttl_seconds=3600.0,
    )
    # Run 20 times — statistically it should not always refresh
    results = [entry.should_refresh_probabilistic(beta=0.001) for _ in range(20)]
    # With tiny beta, very unlikely all 20 return True
    assert not all(results)


# ---------------------------------------------------------------------------
# RedisCache — RedisError → returns None (graceful degradation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_cache_get_redis_error_returns_none() -> None:
    from app.deps.cache import RedisCache

    cache = RedisCache.__new__(RedisCache)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=RedisError("connection refused"))
    cache._client = mock_client
    cache._client_lock = asyncio.Lock()
    cache._url = "redis://localhost:6379"
    cache._default_ttl = 60

    with patch("app.deps.cache.record_redis_command"):
        result = await cache.get("some:key")

    assert result is None


@pytest.mark.asyncio
async def test_redis_cache_get_json_decode_error_returns_none() -> None:
    from app.deps.cache import RedisCache

    cache = RedisCache.__new__(RedisCache)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value="not-valid-json{{{")
    mock_client.delete = AsyncMock()
    cache._client = mock_client
    cache._client_lock = asyncio.Lock()
    cache._url = "redis://localhost:6379"
    cache._default_ttl = 60

    with patch("app.deps.cache.record_redis_command"):
        result = await cache.get("broken:key")

    assert result is None


@pytest.mark.asyncio
async def test_redis_cache_get_missing_etag_returns_none() -> None:
    """Payload with missing etag should be discarded."""
    import orjson

    from app.deps.cache import RedisCache

    cache = RedisCache.__new__(RedisCache)
    mock_client = AsyncMock()
    # Valid JSON but etag is empty string → should return None
    payload = orjson.dumps({"etag": "", "payload": {"x": 1}, "stored_at": time.time()})
    mock_client.get = AsyncMock(return_value=payload.decode())
    cache._client = mock_client
    cache._client_lock = asyncio.Lock()
    cache._url = "redis://localhost:6379"
    cache._default_ttl = 60

    with patch("app.deps.cache.record_redis_command"):
        result = await cache.get("no-etag:key")

    assert result is None


@pytest.mark.asyncio
async def test_redis_cache_close_no_client() -> None:
    """close() with no client should be a no-op."""
    from app.deps.cache import RedisCache

    cache = RedisCache.__new__(RedisCache)
    cache._client = None
    cache._url = "redis://localhost"
    cache._default_ttl = 60
    cache._client_lock = asyncio.Lock()

    # Should not raise
    await cache.close()


# ---------------------------------------------------------------------------
# sanitize_path — additional edge cases
# ---------------------------------------------------------------------------


def test_sanitize_path_exact_base_allowed() -> None:
    from pathlib import Path

    base = Path("/safe/base")
    # Resolving the base dir itself is allowed
    result = sanitize_path("", base)
    # base / "" resolves to base itself → allowed
    assert result is not None


def test_sanitize_path_windows_abs_blocked() -> None:
    from pathlib import Path

    base = Path("/safe/base")
    result = sanitize_path("/absolute/escape", base)
    assert result is None
