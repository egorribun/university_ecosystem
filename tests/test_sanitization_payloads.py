"""Adversarial payload tests for ``app.utils.sanitization``.

The existing ``tests/test_sanitization_unit.py`` covers happy paths.
This module adds defence-in-depth coverage:

* OWASP XSS cheat-sheet payloads against ``sanitize_html`` and
  ``sanitize_rich_text``;
* SSRF / scheme / IP / IDN / credential blocks in ``sanitize_url``;
* path-traversal payloads against ``sanitize_filename`` and
  ``sanitize_path``;
* Hypothesis-based invariants — sanitizers never raise, output is
  always a string (or expected None), no path separator survives a
  filename sanitisation, no control char survives strip_control_chars.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hypo_settings
from hypothesis import strategies as st

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

# ── 1. sanitize_html / sanitize_rich_text — OWASP XSS payloads ──────────────


# Curated subset of OWASP XSS Filter Evasion Cheat Sheet — the goal is to
# verify that nh3's html5ever-based parser strips ALL of these to a safe
# fragment. We assert the dangerous tokens are gone, not the exact output
# (nh3 may legitimately escape rather than drop).
_DANGEROUS_TOKENS: list[str] = [
    "javascript:",
    "<script",
    "onerror=",
    "onload=",
    "onmouseover=",
    "onclick=",
    "<iframe",
    "<svg",
    "<embed",
    "<object",
    "<base",
    "<meta",
    "vbscript:",
    "expression(",
    "data:text/html",
]


@pytest.mark.parametrize(
    "payload",
    [
        # Classic image-error
        '<img src="x" onerror="alert(1)">',
        # SVG with onload
        '<svg onload="alert(1)">',
        # Iframe javascript src
        '<iframe src="javascript:alert(1)"></iframe>',
        # Style with expression (old IE)
        '<div style="background: expression(alert(1))">',
        # Malformed script
        '<<SCRIPT>alert("XSS");//<</SCRIPT>',
        # Embedded null byte in script tag
        "<scr\x00ipt>alert(1)</script>",
        # data: URL in href
        '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">click</a>',
        # vbscript: scheme
        '<a href="vbscript:alert(1)">click</a>',
        # case-confused javascript
        '<a href="JavaScript:alert(1)">click</a>',
        # CSS expression
        "<style>body{background:expression(alert(1))}</style>",
        # Base href hijack
        '<base href="https://evil.example.com/">',
    ],
)
def test_sanitize_html_strips_xss_tokens(payload: str) -> None:
    """Plain-text mode must remove every dangerous HTML construct."""
    out = sanitize_html(payload, allow_basic_tags=False).lower()
    for token in _DANGEROUS_TOKENS:
        # ``token`` may legitimately appear escaped inside text; we want it
        # to NOT survive as the raw substring. nh3 escapes < to &lt; etc.
        assert token not in out, f"Token {token!r} survived: {out!r}"


@pytest.mark.parametrize(
    "payload",
    [
        '<p onclick="alert(1)">click</p>',
        '<p style="color: red">styled</p>',  # style is not allow-listed
        '<a href="javascript:alert(1)">click</a>',
        '<a href="data:text/html,...">click</a>',
        '<a href="vbscript:msgbox(1)">click</a>',
        # script with attribute permitted on rich-text wrapper but not <script>
        "<p><script>alert(1)</script></p>",
    ],
)
def test_sanitize_rich_text_strips_dangerous_attributes_and_schemes(
    payload: str,
) -> None:
    out = sanitize_rich_text(payload).lower()
    for token in (
        "javascript:",
        "onclick=",
        "<script",
        "data:text/html",
        "vbscript:",
    ):
        assert token not in out


def test_sanitize_rich_text_keeps_safe_anchor_with_rel() -> None:
    """A safe http link survives, and nh3 adds rel='noopener noreferrer'."""
    out = sanitize_rich_text('<p><a href="https://example.com">go</a></p>')
    assert 'href="https://example.com"' in out
    # nh3 adds rel="noopener noreferrer" to every <a>.
    assert 'rel="noopener noreferrer"' in out


def test_sanitize_rich_text_strips_html_comments() -> None:
    out = sanitize_rich_text("<p>before<!-- secret --> after</p>")
    assert "<!--" not in out
    assert "secret" not in out


# ── 2. sanitize_url — SSRF / scheme / IDN defences ──────────────────────────


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",  # case
        "data:text/html,...",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "ftp://example.com/",  # not in default allow-list
        "//evil.com",  # no scheme
        "",  # empty
    ],
)
def test_sanitize_url_rejects_dangerous_schemes(bad_url: str) -> None:
    assert sanitize_url(bad_url) is None


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://localhost/",
        "https://127.0.0.1/",
        "https://0.0.0.0/",
        "https://[::1]/",
        "https://10.0.0.1/",  # private
        "https://192.168.1.1/",  # private
        "https://172.16.0.1/",  # private
        "https://169.254.169.254/",  # AWS metadata link-local
    ],
)
def test_sanitize_url_blocks_private_loopback_link_local(bad_url: str) -> None:
    assert sanitize_url(bad_url) is None


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://user:pass@example.com/",  # credentials
        "https://user@example.com/",  # username only
        "https://пример.com/",  # IDN homograph (cyrillic)
    ],
)
def test_sanitize_url_blocks_credentials_and_idn_homograph(bad_url: str) -> None:
    assert sanitize_url(bad_url) is None


def test_sanitize_url_accepts_punycode_idn() -> None:
    """Properly-encoded punycode (xn--) is allowed."""
    out = sanitize_url("https://xn--e1afmkfd.xn--p1ai/")
    assert out == "https://xn--e1afmkfd.xn--p1ai/"


@pytest.mark.parametrize(
    "good_url",
    [
        "https://example.com/",
        "http://example.com/path?q=1",
        "https://sub.example.com:8080/",
        "https://example.com/x?a=b&c=d#anchor",
    ],
)
def test_sanitize_url_accepts_safe_urls(good_url: str) -> None:
    assert sanitize_url(good_url) == good_url


def test_sanitize_url_custom_allowed_schemes() -> None:
    """Caller can pass a tighter scheme list."""
    # https-only — http should be rejected.
    assert sanitize_url("http://example.com/", allowed_schemes=("https",)) is None
    assert (
        sanitize_url("https://example.com/", allowed_schemes=("https",))
        == "https://example.com/"
    )


# ── 3. sanitize_filename — path traversal + Windows reserved ────────────────


@pytest.mark.parametrize(
    ("inp", "must_not_contain"),
    [
        ("../../../etc/passwd", ("/", "\\")),
        ("..\\..\\windows\\system32", ("/", "\\")),
        ("foo/bar.txt", ("/",)),
        ("foo\\bar.txt", ("\\",)),
        ("file\x00.txt", ("\x00",)),
        ("CON.txt", ()),  # Windows reserved name (we accept; only chars are stripped)
        ('bad<>:"|?*name.txt', ("<", ">", ":", '"', "|", "?", "*")),
        # Multiple dots collapse to one
        ("a..b...c.txt", ("..",)),
    ],
)
def test_sanitize_filename_strips_dangerous_characters(
    inp: str, must_not_contain: tuple[str, ...]
) -> None:
    out = sanitize_filename(inp)
    for forbidden in must_not_contain:
        assert forbidden not in out, f"{forbidden!r} survived in {out!r}"


def test_sanitize_filename_strips_leading_dot() -> None:
    """Leading dots (Unix hidden file) are stripped."""
    assert not sanitize_filename(".env").startswith(".")


def test_sanitize_filename_empty_returns_unnamed() -> None:
    assert sanitize_filename("") == "unnamed"
    # Whitespace-only collapses to empty after strip → 'unnamed'.
    assert sanitize_filename("   ") == "unnamed"


def test_sanitize_filename_preserves_extension_on_truncation() -> None:
    long_name = "a" * 300
    out = sanitize_filename(f"{long_name}.txt", max_length=50)
    assert out.endswith(".txt")
    assert len(out) <= 50


# ── 4. sanitize_path — directory-traversal sandbox ──────────────────────────


def test_sanitize_path_within_base(tmp_path: Path) -> None:
    """A safe relative path under the base resolves successfully."""
    target = tmp_path / "subdir" / "file.txt"
    target.parent.mkdir()
    target.write_text("x")
    out = sanitize_path("subdir/file.txt", tmp_path)
    assert out is not None
    assert out == target.resolve()


def test_sanitize_path_blocks_traversal(tmp_path: Path) -> None:
    """``../`` traversal escapes the base — return None."""
    out = sanitize_path("../../etc/passwd", tmp_path)
    assert out is None


def test_sanitize_path_handles_absolute_path(tmp_path: Path) -> None:
    """An absolute path that escapes the base returns None."""
    # Use a path that's clearly outside tmp_path. tempfile.gettempdir()
    # avoids hardcoding "/tmp" or relying on env vars.
    elsewhere = Path(tempfile.gettempdir()).resolve() / "definitely_outside_base"
    out = sanitize_path(str(elsewhere), tmp_path)
    # Either returns None (escape) or stays inside (depending on resolution).
    if out is not None:
        assert tmp_path.resolve() in out.parents or out == tmp_path.resolve()


# ── 5. sanitize_email — case + whitespace ───────────────────────────────────


def test_sanitize_email_lowercases_and_strips() -> None:
    assert sanitize_email("  Foo@Bar.COM  ") == "foo@bar.com"


def test_sanitize_email_empty_input() -> None:
    assert sanitize_email("") == ""


# ── 6. strip_control_chars — null bytes + control chars ─────────────────────


def test_strip_control_chars_removes_null_bytes() -> None:
    assert strip_control_chars("hello\x00world") == "helloworld"


def test_strip_control_chars_keeps_tab_lf_cr() -> None:
    """Tab, LF and CR are preserved; other control chars stripped.

    The regex strips 0x00-0x08, 0x0b, 0x0c, 0x0e-0x1f, 0x7f — so 0x09 (tab),
    0x0a (LF) and 0x0d (CR) all pass through (essential for legitimate text).
    """
    s = "line1\nline2\ttab\rcr\x07bell"
    out = strip_control_chars(s)
    assert "\n" in out
    assert "\t" in out
    assert "\r" in out  # CR is permitted
    assert "\x07" not in out


def test_strip_control_chars_empty_returns_empty() -> None:
    assert strip_control_chars("") == ""


# ── 7. truncate ─────────────────────────────────────────────────────────────


def test_truncate_short_text_unchanged() -> None:
    assert truncate("hi", 100) == "hi"


def test_truncate_long_text() -> None:
    out = truncate("a" * 50, 10)
    assert out.endswith("...")
    assert len(out) == 10


def test_truncate_custom_suffix() -> None:
    out = truncate("a" * 50, 10, suffix="…")
    assert out.endswith("…")
    assert len(out) == 10


# ── 8. sanitize_optional_text ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("hello", "hello"),
        (b"bytes", "bytes"),
        (b"   ", None),
        (42, "42"),
        # Invalid UTF-8 falls back to lossy decode.
        (b"\xff\xfe", None),  # Decodes to nothing meaningful, should be None.
    ],
)
def test_sanitize_optional_text_normalises(inp: object, expected: str | None) -> None:
    """Numbers stringify, blanks become None, bytes decode."""
    result = sanitize_optional_text(inp)
    if expected is None:
        assert result is None
    else:
        assert result == expected


# ── 9. Property-based invariants ─────────────────────────────────────────────


@hypo_settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
@given(html=st.text(max_size=300))
def test_sanitize_html_never_raises(html: str) -> None:
    """``sanitize_html`` always returns a string, never raises."""
    out = sanitize_html(html, allow_basic_tags=False)
    assert isinstance(out, str)


@hypo_settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
@given(filename=st.text(min_size=0, max_size=300))
def test_sanitize_filename_no_path_separator(filename: str) -> None:
    """No matter the input, the output never contains / or \\ or null."""
    out = sanitize_filename(filename, max_length=255)
    assert "/" not in out
    assert "\\" not in out
    assert "\x00" not in out
    assert len(out) <= 255


@hypo_settings(max_examples=50)
@given(text=st.text(max_size=200))
def test_strip_control_chars_idempotent(text: str) -> None:
    """``strip_control_chars`` applied twice == applied once."""
    once = strip_control_chars(text)
    twice = strip_control_chars(once)
    assert once == twice


@hypo_settings(max_examples=50)
@given(text=st.text(max_size=200))
def test_strip_control_chars_no_disallowed_chars_remain(text: str) -> None:
    """No disallowed control byte survives."""
    out = strip_control_chars(text)
    # The regex strips \x00-\x08, \x0b, \x0c, \x0e-\x1f, \x7f.
    forbidden = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    assert forbidden.search(out) is None
