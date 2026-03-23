"""
HTML sanitization service — isomorphic with the WASM frontend crate.

Uses the `pyo3_sanitizer` native extension (Rust/ammonia) when available.
Falls back to `nh3` (a pure-Python-accessible Rust crate also backed by ammonia)
so the service works out-of-the-box in development environments that have not
compiled the PyO3 wheel via `maturin develop`.

Both backends produce semantically equivalent output because they both use
ammonia under the hood. The PyO3 extension is preferred in production because
it exposes the exact same builder configuration as the WASM frontend crate,
providing the strongest isomorphism guarantee.
"""

from __future__ import annotations

import logging

from app.core.logging import get_logger
from enum import Enum, auto

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Backend resolution — prefer native PyO3 extension, fall back to nh3.
# ---------------------------------------------------------------------------

try:
    import pyo3_sanitizer as _native

    _BACKEND_LABEL = "pyo3_sanitizer (native)"

    def _rich_text(html: str) -> str:
        return str(_native.sanitize_rich_text(html))

    def _basic(html: str) -> str:
        return str(_native.sanitize_html_basic(html))

    def _strip(html: str) -> str:
        return str(_native.strip_html(html))

except ImportError:
    # nh3 is an unconditional project dependency (pyproject.toml); the fallback
    # is always available even without a Rust toolchain.
    import nh3 as _nh3

    _BACKEND_LABEL = "nh3 (fallback)"

    _NH3_RICH_ATTRS: dict[str, set[str]] = {
        "a": {"href", "title", "target"},
    }
    _NH3_RICH_TAGS: set[str] = {
        "p",
        "br",
        "b",
        "i",
        "em",
        "strong",
        "u",
        "s",
        "strike",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "a",
        "blockquote",
        "code",
        "pre",
    }
    _NH3_BASIC_TAGS: set[str] = {"b", "i", "em", "strong"}

    def _rich_text(html: str) -> str:
        return _nh3.clean(
            html,
            tags=_NH3_RICH_TAGS,
            attributes=_NH3_RICH_ATTRS,
            url_schemes={"http", "https"},
            link_rel="noopener noreferrer",
        )

    def _basic(html: str) -> str:
        return _nh3.clean(html, tags=_NH3_BASIC_TAGS)

    def _strip(html: str) -> str:
        return _nh3.clean(html, tags=set())


_logger.debug("content_processing: using backend=%s", _BACKEND_LABEL)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SanitizationMode(Enum):
    """Sanitization intensity level.

    - RICH_TEXT: preserve formatting tags + safe links (blog posts, comments).
    - BASIC:     preserve only inline emphasis (display names, profile bios).
    - STRIP:     remove all markup, return plain text (search indices, logs).
    """

    RICH_TEXT = auto()
    BASIC = auto()
    STRIP = auto()


def sanitize(html: str, *, mode: SanitizationMode = SanitizationMode.RICH_TEXT) -> str:
    """Sanitize ``html`` according to ``mode``.

    Args:
        html:  Raw HTML string (may contain attacker-controlled content).
        mode:  Controls which HTML elements survive sanitization.

    Returns:
        A safe HTML string (RICH_TEXT/BASIC) or plain text (STRIP).

    Raises:
        ValueError: If ``mode`` is not a valid ``SanitizationMode``.
    """
    if mode is SanitizationMode.RICH_TEXT:
        return _rich_text(html)
    if mode is SanitizationMode.BASIC:
        return _basic(html)
    if mode is SanitizationMode.STRIP:
        return _strip(html)
    # Guard against future enum expansion without a corresponding branch.
    raise ValueError(f"Unhandled SanitizationMode: {mode!r}")
