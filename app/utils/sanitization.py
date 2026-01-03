"""
Input sanitization utilities.

Provides consistent sanitization for user input to prevent XSS, path traversal,
and other injection attacks.
"""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path


def sanitize_html(text: str, allow_basic_tags: bool = False) -> str:
    """
    Sanitize HTML from user input.

    Args:
        text: User input text
        allow_basic_tags: If True, allow <b>, <i>, <em>, <strong>

    Returns:
        Sanitized text with HTML entities escaped
    """
    if not text:
        return ""

    # First escape all HTML entities
    result = html.escape(text)

    # Optionally restore basic formatting tags
    if allow_basic_tags:
        safe_tags = {
            "&lt;b&gt;": "<b>",
            "&lt;/b&gt;": "</b>",
            "&lt;i&gt;": "<i>",
            "&lt;/i&gt;": "</i>",
            "&lt;em&gt;": "<em>",
            "&lt;/em&gt;": "</em>",
            "&lt;strong&gt;": "<strong>",
            "&lt;/strong&gt;": "</strong>",
        }
        for escaped, original in safe_tags.items():
            result = result.replace(escaped, original)

    return result


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
        name, _, ext = filename.rpartition(".")
        if ext:
            max_name_len = max_length - len(ext) - 1
            filename = f"{name[:max_name_len]}.{ext}"
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
    except (ValueError, OSError):
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
    Validate and sanitize a URL.

    Args:
        url: User-provided URL
        allowed_schemes: Tuple of allowed schemes

    Returns:
        Sanitized URL or None if invalid
    """
    from urllib.parse import urlparse

    if not url:
        return None

    url = url.strip()

    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme not in allowed_schemes:
            return None

        # Check for netloc (domain)
        if not parsed.netloc:
            return None

        # Prevent javascript: and data: schemes even in params
        if "javascript:" in url.lower() or "data:" in url.lower():
            return None

        return url
    except Exception:
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


__all__ = [
    "sanitize_html",
    "sanitize_filename",
    "sanitize_path",
    "sanitize_email",
    "sanitize_url",
    "strip_control_chars",
    "truncate",
]
