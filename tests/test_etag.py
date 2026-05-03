"""Unit tests for the ETag / conditional-request layer.

The four helpers (``compute_etag``, ``format_etag``, ``parse_if_none_match``,
``etag_matches``) and ``conditional_response`` carry the production traffic;
news/events/schedule routes call them directly. ``ETagMiddleware`` is
defined but currently not registered anywhere in ``app/main.py``, so it
isn't exercised here — its body-handling path interacts with Starlette's
``BaseHTTPMiddleware`` streaming wrapper in a way that needs separate
investigation outside this routine maintenance scope.

Edge cases covered:

* compute_etag: bytes/str input symmetry, deterministic, 32 hex chars,
  unicode / empty input;
* format_etag: idempotent, empty passthrough, whitespace stripping;
* parse_if_none_match: weak (``W/"foo"``), strong (``"foo"``), wildcard
  (``*``), mixed lists, malformed (no quotes / unterminated quote / lone
  ``W/``), case-insensitive ``W/`` prefix, surrounding whitespace,
  quoted-empty edge case, very-long opaque tag;
* etag_matches: empty edge cases, wildcard, list membership,
  case-sensitivity;
* conditional_response: 200 with body + ETag when no If-None-Match,
  304 on exact match / wildcard, full body on mismatch, custom
  status_code passes through.
"""

from __future__ import annotations

import re

import orjson
from fastapi import Request

from app.core.etag import (
    compute_etag,
    conditional_response,
    etag_matches,
    format_etag,
    parse_if_none_match,
)

# ── 1. compute_etag ──────────────────────────────────────────────────────────


class TestComputeEtag:
    """``compute_etag`` is a deterministic 32-hex-char fingerprint."""

    def test_str_and_bytes_match_for_same_text(self) -> None:
        """Encoding-symmetry: utf-8 string and its bytes encoding yield same digest."""
        assert compute_etag("hello") == compute_etag(b"hello")

    def test_returns_exactly_32_hex_chars(self) -> None:
        """Truncated SHA-256 — 32 lowercase hex chars (LOW-W19)."""
        digest = compute_etag(b"any-content")
        assert len(digest) == 32
        assert re.fullmatch(r"[0-9a-f]{32}", digest)

    def test_deterministic(self) -> None:
        """Same input → same digest, every call."""
        assert compute_etag(b"x") == compute_etag(b"x")

    def test_different_content_different_etag(self) -> None:
        """Distinct inputs produce distinct (or at least non-identical) digests."""
        assert compute_etag(b"alpha") != compute_etag(b"beta")

    def test_empty_input_is_well_defined(self) -> None:
        """An empty body still produces a 32-char digest (no crash)."""
        digest = compute_etag(b"")
        assert len(digest) == 32

    def test_unicode_content(self) -> None:
        """Multi-byte UTF-8 content is hashed via its bytes encoding."""
        digest = compute_etag("Тест 🚀 αβγ")
        assert len(digest) == 32


# ── 2. format_etag ───────────────────────────────────────────────────────────


class TestFormatEtag:
    """``format_etag`` wraps an opaque-tag in ``"…"`` exactly once."""

    def test_wraps_in_quotes(self) -> None:
        assert format_etag("abc") == '"abc"'

    def test_idempotent_when_already_quoted(self) -> None:
        assert format_etag('"abc"') == '"abc"'

    def test_empty_passes_through_untouched(self) -> None:
        """Empty string returns empty string — caller decides what to do."""
        assert format_etag("") == ""

    def test_strips_whitespace(self) -> None:
        assert format_etag("  abc  ") == '"abc"'

    def test_preserves_inner_quotes(self) -> None:
        """Already-quoted values keep their inner content verbatim."""
        assert format_etag('"x y z"') == '"x y z"'


# ── 3. parse_if_none_match — RFC 7232 §2.3 weak comparison ──────────────────


class TestParseIfNoneMatch:
    """``parse_if_none_match`` extracts opaque tags for downstream matching."""

    def test_none_returns_empty_list(self) -> None:
        assert parse_if_none_match(None) == []

    def test_empty_returns_empty_list(self) -> None:
        assert parse_if_none_match("") == []

    def test_single_strong_etag(self) -> None:
        assert parse_if_none_match('"abc"') == ["abc"]

    def test_single_weak_etag(self) -> None:
        """``W/"abc"`` strips the W/ prefix and unwraps the quotes."""
        assert parse_if_none_match('W/"abc"') == ["abc"]

    def test_lowercase_w_prefix(self) -> None:
        """Per RFC the prefix is case-insensitive (``W/`` or ``w/``)."""
        assert parse_if_none_match('w/"abc"') == ["abc"]

    def test_weak_with_internal_whitespace(self) -> None:
        """RFC 7230 list rules — ``W/ "abc"`` is permitted (LOW-W19)."""
        assert parse_if_none_match('W/ "abc"') == ["abc"]

    def test_wildcard(self) -> None:
        assert parse_if_none_match("*") == ["*"]

    def test_multiple_etags_mixed_strong_weak(self) -> None:
        """Comma-separated list with both weak and strong forms."""
        result = parse_if_none_match('"abc", W/"def", "ghi"')
        assert result == ["abc", "def", "ghi"]

    def test_silently_drops_unquoted_token(self) -> None:
        """Bare unquoted tokens are dropped (not standards-conformant)."""
        # Note: 'abc' (no quotes) is not a valid ETag and is silently ignored.
        assert parse_if_none_match("abc") == []

    def test_silently_drops_unterminated_quote(self) -> None:
        """``"abc`` with no closing quote is dropped."""
        assert parse_if_none_match('"abc') == []

    def test_silently_drops_lone_w_prefix(self) -> None:
        """``W/`` with no quoted opaque-tag is dropped."""
        assert parse_if_none_match("W/") == []

    def test_silently_drops_weak_without_quotes(self) -> None:
        """``W/abc`` (no quotes around opaque-tag) is dropped."""
        assert parse_if_none_match("W/abc") == []

    def test_strips_outer_whitespace_in_each_part(self) -> None:
        """Surrounding whitespace per item is permitted."""
        assert parse_if_none_match(' "abc" , "def" ') == ["abc", "def"]

    def test_quoted_empty_string_passes_as_empty_tag(self) -> None:
        """``""`` parses to an empty string opaque-tag (rare but valid syntax)."""
        # The implementation strips the quotes — empty inner is an empty entry.
        assert parse_if_none_match('""') == [""]

    def test_very_long_etag(self) -> None:
        """A very long opaque-tag is preserved as-is."""
        long_tag = "x" * 10_000
        assert parse_if_none_match(f'"{long_tag}"') == [long_tag]


# ── 4. etag_matches ──────────────────────────────────────────────────────────


class TestEtagMatches:
    """``etag_matches`` is the gate between cached and fresh content."""

    def test_empty_etag_never_matches(self) -> None:
        assert etag_matches("", ["abc"]) is False

    def test_empty_list_never_matches(self) -> None:
        assert etag_matches("abc", []) is False

    def test_wildcard_always_matches(self) -> None:
        assert etag_matches("anything", ["*"]) is True

    def test_member_matches(self) -> None:
        assert etag_matches("abc", ["xxx", "abc", "yyy"]) is True

    def test_non_member_does_not_match(self) -> None:
        assert etag_matches("abc", ["xxx", "yyy"]) is False

    def test_case_sensitive_match(self) -> None:
        """ETags are case-sensitive opaque values per RFC 7232."""
        assert etag_matches("ABC", ["abc"]) is False


# ── 5. conditional_response — direct helper ──────────────────────────────────


def _build_request(if_none_match: str | None = None) -> Request:
    """Build a minimal ASGI Request for ``conditional_response``."""
    headers: list[tuple[bytes, bytes]] = []
    if if_none_match is not None:
        headers.append((b"if-none-match", if_none_match.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "raw_path": b"/x",
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope)  # type: ignore[arg-type]


def test_conditional_response_200_when_no_if_none_match() -> None:
    """Without If-None-Match, a 200 is returned with body + ETag."""
    request = _build_request()
    resp = conditional_response(request, {"a": 1})
    assert resp.status_code == 200
    assert resp.headers["etag"].startswith('"')
    assert resp.body == orjson.dumps({"a": 1})


def test_conditional_response_304_when_etag_matches() -> None:
    """A matching If-None-Match returns 304 with no body."""
    request = _build_request()
    first = conditional_response(request, {"a": 1})
    etag = first.headers["etag"]

    second_request = _build_request(if_none_match=etag)
    second = conditional_response(second_request, {"a": 1})
    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert second.body == b""


def test_conditional_response_304_on_wildcard() -> None:
    """``If-None-Match: *`` always returns 304."""
    request = _build_request(if_none_match="*")
    resp = conditional_response(request, {"a": 1})
    assert resp.status_code == 304


def test_conditional_response_full_content_on_mismatch() -> None:
    """A wrong If-None-Match returns a full 200 with the new body."""
    request = _build_request(if_none_match='"stale"')
    resp = conditional_response(request, {"a": 2})
    assert resp.status_code == 200
    assert resp.body == orjson.dumps({"a": 2})


def test_conditional_response_uses_custom_status_code() -> None:
    """When 200 is not desired, the ``status_code`` argument flows through."""
    request = _build_request()
    resp = conditional_response(request, [1, 2, 3], status_code=201)
    assert resp.status_code == 201
