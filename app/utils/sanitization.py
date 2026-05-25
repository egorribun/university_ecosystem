"""
Input sanitization utilities.

Provides consistent sanitization for user input to prevent XSS, path traversal,
and other injection attacks.

HTML sanitization is powered by ``nh3`` — a Python binding for Mozilla's Ammonia
library (written in Rust). Ammonia parses HTML with the same html5ever engine used
by Firefox, which eliminates entire classes of bypass attacks that affect regex-based
sanitisers (pre-encoded entities, malformed tags, encoding tricks, etc.).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import nh3

# ---------------------------------------------------------------------------
# Tag / attribute allow-lists
# ---------------------------------------------------------------------------

# Tags allowed in plain text that permits *basic* inline formatting only.
_BASIC_TAGS: set[str] = {"b", "i", "em", "strong"}

# Tags allowed in rich-text editor output.
ALLOWED_RICH_TEXT_TAGS: frozenset[str] = frozenset(
    {
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
)

# Per-element attribute allow-lists consumed by nh3.
# Only <a> needs attributes; all other tags are stripped of their attributes
# automatically by nh3 when not listed here.
_RICH_TEXT_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title", "target"},
}

# URL schemes permitted inside href attributes.
# ``nh3`` enforces this at the parser level — ``javascript:`` / ``data:``
# can never appear in the output regardless of encoding tricks.
_SAFE_URL_SCHEMES: set[str] = {"http", "https"}


def sanitize_html(text: str, allow_basic_tags: bool = False) -> str:
    """Sanitize HTML from user input.

    Args:
        text: User input text.
        allow_basic_tags: If ``True``, allow ``<b>``, ``<i>``, ``<em>``,
            ``<strong>`` inline formatting tags.

    Returns:
        Sanitized text.  When *allow_basic_tags* is ``False`` all HTML tags
        are stripped and the text is returned as plain text (HTML entities
        are preserved so the output is safe to embed in HTML).
    """
    if not text:
        return ""
    if not allow_basic_tags:
        # Strip every tag — pure plain-text output.
        return nh3.clean(text, tags=set())
    # Allow only the four safe inline-formatting tags; no attributes.
    return nh3.clean(text, tags=_BASIC_TAGS, attributes={})


def sanitize_rich_text(html_content: str) -> str:
    """Sanitize rich-text HTML content using a whitelist approach.

    Allows a limited set of safe HTML tags for rich-text editors while
    stripping all dangerous elements and attributes.  URL schemes are
    restricted to ``http`` and ``https`` — ``javascript:``, ``data:``,
    ``vbscript:`` and similar schemes are rejected at the parser level by
    ``nh3`` and can never appear in the output.

    Args:
        html_content: Raw HTML from user input.

    Returns:
        Sanitized HTML containing only allowed tags and attributes.
    """
    if not html_content:
        return ""
    try:
        return nh3.clean(
            html_content,
            tags=set(ALLOWED_RICH_TEXT_TAGS),
            attributes=_RICH_TEXT_ATTRIBUTES,
            url_schemes=_SAFE_URL_SCHEMES,
            strip_comments=True,
            # nh3 automatically adds rel="noopener noreferrer" to every <a> tag.
            link_rel="noopener noreferrer",
        )
    except Exception as e:  # RZ-22-01-JUSTIFIED: convert-to-domain — converts nh3 errors to HTTPException (reviewed TD-27-04)
        import structlog
        from fastapi import HTTPException

        logger = structlog.get_logger(__name__)
        logger.error("sanitization_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid payload signature") from e


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to prevent path traversal and invalid characters.

    Args:
        filename: User-provided filename
        max_length: Maximum allowed length

    Returns:
        Safe filename
    """
    if not filename:
        return "unnamed"

    # Normalize unicode
    filename = unicodedata.normalize("NFKD", filename)

    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove null bytes and other control characters
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

    # Remove dangerous patterns
    filename = filename.lstrip(".")  # Prevent hidden files
    filename = re.sub(r"\.{2,}", ".", filename)  # Remove multiple dots

    # Remove or replace invalid Windows characters
    invalid_chars = r'[<>:"|?*]'
    filename = re.sub(invalid_chars, "_", filename)

    # Strip whitespace
    filename = filename.strip()

    # Truncate to max length while preserving extension
    if len(filename) > max_length:
        name, sep, ext = filename.rpartition(".")
        if sep == "." and ext:
            max_name_len = max_length - len(ext) - 1
            if max_name_len > 0:
                filename = f"{name[:max_name_len]}.{ext}"
            else:
                filename = filename[:max_length]
        else:
            filename = filename[:max_length]

    return filename or "unnamed"


def sanitize_path(path: str, base_dir: str | Path) -> Path | None:
    """
    Sanitize a path to prevent directory traversal.

    Args:
        path: User-provided path
        base_dir: Base directory that path must be within

    Returns:
        Safe absolute path, or None if path escapes base_dir
    """
    try:
        base = Path(base_dir).resolve()
        user_path = (base / path).resolve()

        # Check if resolved path is within base
        if base in user_path.parents or user_path == base:
            return user_path
        return None
    except (ValueError, OSError):  # RZ-28-01
        return None


def sanitize_email(email: str) -> str:
    """
    Normalize and sanitize an email address.

    Args:
        email: User-provided email

    Returns:
        Normalized email (lowercase, stripped)
    """
    return email.strip().lower() if email else ""


def sanitize_url(
    url: str, allowed_schemes: tuple[str, ...] = ("http", "https")
) -> str | None:
    """
    Validate and sanitize a URL with SSRF protections.

    Args:
        url: User-provided URL
        allowed_schemes: Tuple of allowed schemes

    Returns:
        Sanitized URL or None if invalid/dangerous
    """
    from ipaddress import ip_address
    from urllib.parse import urlparse

    if not url:
        return None

    url = url.strip()

    # Block dangerous scheme patterns early (case-insensitive)
    lower_url = url.lower()
    dangerous_patterns = ("javascript:", "data:", "vbscript:", "file:")
    if any(pattern in lower_url for pattern in dangerous_patterns):
        return None

    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme.lower() not in allowed_schemes:
            return None

        # Check for netloc (domain)
        if not parsed.netloc:
            return None

        # Block credentials in URL (potential for phishing/SSRF)
        if parsed.username or parsed.password:
            return None

        # Extract hostname (strip port if present)
        hostname = parsed.hostname
        if not hostname:
            return None

        # Block unicode domain exploits (IDN homograph attacks)
        try:
            hostname.encode("ascii")
        except UnicodeEncodeError:
            # Contains non-ASCII - could be IDN homograph attack
            # Allow only if it's a proper punycode domain
            if not hostname.startswith("xn--"):
                return None

        # Block private/local IP addresses (SSRF protection)
        try:
            ip = ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return None
        except ValueError:
            # Not an IP address, it's a hostname - that's fine
            pass

        # Block localhost variants
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):  # noqa: S104
            return None

        return url
    except (
        ValueError,
        UnicodeError,
    ):  # RZ-26-01 + RZ-22-01: narrowed — URL parsing errors
        return None


def strip_control_chars(text: str) -> str:
    """
    Remove control characters from text.

    Args:
        text: Input text

    Returns:
        Text with control characters removed
    """
    if not text:
        return ""
    # Keep line feeds and tabs, remove other control chars
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to max length with suffix.

    Args:
        text: Input text
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def sanitize_optional_text(value: Any) -> str | None:
    """Normalize optional text values to strings."""
    if value is None:
        return None
    if isinstance(value, bytes | bytearray):
        try:
            decoded = value.decode("utf-8")
        except (
            UnicodeDecodeError,
            ValueError,
        ):  # RZ-22-01: narrowed — bytes decode errors
            decoded = value.decode("utf-8", "ignore")
        return decoded if decoded.strip() else None
    if isinstance(value, str):
        return value if value.strip() else None
    text = str(value)
    return text if text.strip() else None


__all__ = [
    "sanitize_email",
    "sanitize_filename",
    "sanitize_html",
    "sanitize_optional_text",
    "sanitize_path",
    "sanitize_rich_text",
    "sanitize_url",
    "strip_control_chars",
    "truncate",
]
