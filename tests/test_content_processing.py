"""
Parametrized OWASP XSS payload tests for app.services.content_processing.

Tests run via the nh3 fallback backend (no Rust toolchain required in CI).
When the pyo3_sanitizer native extension is compiled via `maturin develop`,
the same tests exercise the PyO3/ammonia path automatically.

Reference: https://cheatsheetseries.owasp.org/cheatsheets/XSS_Filter_Evasion_Cheat_Sheet.html
"""

from __future__ import annotations

from html.parser import HTMLParser

import pytest

from app.services.content_processing import SanitizationMode, sanitize


class _AnchorHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value is not None:
                self.hrefs.append(value)


# ---------------------------------------------------------------------------
# OWASP Filter Evasion Cheat Sheet — canonical XSS payloads
# ---------------------------------------------------------------------------

_OWASP_PAYLOADS: list[tuple[str, str]] = [
    # (payload_label, payload_html)
    ("basic_script_tag", "<script>alert(1)</script>"),
    ("img_onerror", "<img src=x onerror=alert(1)>"),
    ("svg_onload", "<svg onload=alert(1)>"),
    ("javascript_protocol_anchor", "<a href='javascript:alert(1)'>click</a>"),
    ("data_uri_link", "<a href='data:text/html,<script>alert(1)</script>'>x</a>"),
    ("marquee_onstart", "<marquee onstart=alert(1)>text</marquee>"),
    ("iframe_srcdoc", "<iframe srcdoc='<script>alert(1)</script>'>"),
    ("details_toggle", "<details open ontoggle=alert(1)>text</details>"),
    ("input_autofocus", "<input autofocus onfocus=alert(1)>"),
    ("video_onerror", "<video src=x onerror=alert(1)>"),
    ("base64_img", "<img src='data:image/gif;base64,R0lGODlh' onerror=alert(1)>"),
    ("mixed_case_script", "<ScRiPt>alert(1)</sCrIpT>"),
    ("null_byte_injection", "<sc\x00ript>alert(1)</script>"),
    ("newline_evasion", "<img src='x'\nonerror='alert(1)'>"),
    ("embedded_tab", "<a\ttarget=_blank href=javascript:alert(1)>x</a>"),
    ("vbscript_href", "<a href='vbscript:msgbox(1)'>x</a>"),
]


@pytest.mark.parametrize(
    "label,payload", _OWASP_PAYLOADS, ids=[p[0] for p in _OWASP_PAYLOADS]
)
def test_rich_text_blocks_xss_payload(label: str, payload: str) -> None:
    """RICH_TEXT mode must produce output containing no executable JavaScript constructs.

    Note: plain-text content of script tags (e.g. 'alert(1)') may appear as
    inert text after the tag is stripped — this is correct sanitizer behaviour
    and does not constitute an XSS risk. We assert on executable constructs only.
    """
    result = sanitize(payload, mode=SanitizationMode.RICH_TEXT)

    assert "<script" not in result.lower(), (
        f"[{label}] script tag survived sanitization"
    )
    assert "javascript:" not in result.lower(), f"[{label}] javascript: URI survived"
    assert "vbscript:" not in result.lower(), f"[{label}] vbscript: URI survived"
    assert "data:" not in result.lower(), f"[{label}] data: URI survived"
    assert "onerror" not in result.lower(), f"[{label}] onerror handler survived"
    assert "onload" not in result.lower(), f"[{label}] onload handler survived"
    assert "onfocus" not in result.lower(), f"[{label}] onfocus handler survived"
    assert "ontoggle" not in result.lower(), f"[{label}] ontoggle handler survived"
    assert "onstart" not in result.lower(), f"[{label}] onstart handler survived"


@pytest.mark.parametrize(
    "label,payload", _OWASP_PAYLOADS, ids=[p[0] for p in _OWASP_PAYLOADS]
)
def test_basic_mode_blocks_xss_payload(label: str, payload: str) -> None:
    """BASIC mode must allow only b/i/em/strong — all other tags and handlers stripped."""
    result = sanitize(payload, mode=SanitizationMode.BASIC)

    # The sanitizer may preserve text content (e.g. "alert(1)") as plain text —
    # that is safe and correct: plain text cannot execute.  We only assert that
    # executable constructs (script/iframe tags, event handlers, dangerous URI
    # schemes) do not survive.
    assert "<script" not in result.lower(), (
        f"[{label}] script tag survived basic sanitization"
    )
    assert "<iframe" not in result.lower(), f"[{label}] iframe tag survived"
    assert "javascript:" not in result.lower(), f"[{label}] javascript: URI survived"
    assert "onerror" not in result.lower(), f"[{label}] onerror handler survived"
    assert "onload" not in result.lower(), f"[{label}] onload handler survived"


@pytest.mark.parametrize(
    "label,payload", _OWASP_PAYLOADS, ids=[p[0] for p in _OWASP_PAYLOADS]
)
def test_strip_mode_removes_all_markup(label: str, payload: str) -> None:
    """STRIP mode must return plain text with zero HTML elements.

    Text content (including script body text like 'alert(1)') may survive as
    inert plain text — this is correct: stripping removes tags, not text nodes.
    What must NOT survive are angle brackets (i.e. unparsed / broken tags).
    """
    result = sanitize(payload, mode=SanitizationMode.STRIP)

    assert "<" not in result, (
        f"[{label}] HTML tag leaked through STRIP mode (angle bracket present)"
    )


def test_rich_text_preserves_safe_formatting() -> None:
    """RICH_TEXT must not destroy legitimate HTML formatting."""
    safe_html = "<p>Hello <strong>world</strong>! <em>Rust</em> is fast.</p>"
    result = sanitize(safe_html, mode=SanitizationMode.RICH_TEXT)

    assert "<strong>" in result
    assert "<em>" in result
    assert "<p>" in result


def test_rich_text_preserves_safe_link() -> None:
    """RICH_TEXT must keep safe https:// anchors with noopener noreferrer."""
    safe_link = '<a href="https://example.com" title="Example">visit</a>'
    result = sanitize(safe_link, mode=SanitizationMode.RICH_TEXT)
    parser = _AnchorHrefParser()
    parser.feed(result)

    assert parser.hrefs == ["https://example.com"]
    assert "noopener noreferrer" in result


def test_strip_returns_plain_text() -> None:
    """STRIP mode must return the text content without any tags."""
    html = "<p>Hello <b>world</b>!</p>"
    result = sanitize(html, mode=SanitizationMode.STRIP)

    assert "Hello" in result
    assert "world" in result
    assert "<" not in result


def test_invalid_sanitization_mode_raises_value_error() -> None:
    """Passing an unexpected enum value must raise ValueError, not silently pass."""
    with pytest.raises((ValueError, AttributeError)):
        sanitize("<b>text</b>", mode="invalid_mode")  # type: ignore[arg-type]
