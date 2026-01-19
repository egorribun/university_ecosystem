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


# Allowed tags and attributes for rich text sanitization
ALLOWED_RICH_TEXT_TAGS = frozenset(
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

ALLOWED_LINK_ATTRIBUTES = frozenset({"href", "title", "target", "rel"})

# Pattern to match HTML tags with optional attributes
_TAG_PATTERN = re.compile(
    r"<(/?)(\w+)([^>]*)>",
    re.IGNORECASE | re.DOTALL,
)

# Pattern to extract href attribute
_HREF_PATTERN = re.compile(
    r'\bhref\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)


def sanitize_rich_text(html_content: str) -> str:
    """
    Sanitize rich text HTML content with whitelist approach.

    Allows a limited set of safe HTML tags for rich text editors
    while stripping all dangerous elements and attributes.

    Args:
        html_content: Raw HTML from user input

    Returns:
        Sanitized HTML with only allowed tags
    """
    if not html_content:
        return ""

    def replace_tag(match: re.Match) -> str:
        closing_slash = match.group(1)
        tag_name = match.group(2).lower()
        attributes_str = match.group(3)

        # Strip disallowed tags entirely
        if tag_name not in ALLOWED_RICH_TEXT_TAGS:
            return ""

        # For closing tags, just return the clean closing tag
        if closing_slash:
            return f"</{tag_name}>"

        # For anchor tags, validate href and add security attributes
        if tag_name == "a":
            href_match = _HREF_PATTERN.search(attributes_str)
            if href_match:
                href = href_match.group(1)
                # Only allow http/https URLs
                if href.startswith(("http://", "https://", "/")):
                    # Escape href value and add security attributes
                    safe_href = html.escape(href, quote=True)
                    return (
                        f'<a href="{safe_href}" '
                        'rel="noopener noreferrer" target="_blank">'
                    )
            # Invalid or missing href - strip the link
            return ""

        # For all other allowed tags, return clean tag without attributes
        return f"<{tag_name}>"

    # Replace tags according to whitelist
    result = _TAG_PATTERN.sub(replace_tag, html_content)

    # Escape any remaining < or > that might be malformed HTML
    result = result.replace("<", "&lt;").replace(">", "&gt;")

    # Restore the valid tags we just created (they use our specific format)
    for tag in ALLOWED_RICH_TEXT_TAGS:
        result = result.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        result = result.replace(f"&lt;/{tag}&gt;", f"</{tag}>")

    # Restore anchor tags with attributes
    result = re.sub(
        r'&lt;a href="([^"]*)" rel="noopener noreferrer" target="_blank"&gt;',
        r'<a href="\1" rel="noopener noreferrer" target="_blank">',
        result,
    )

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
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
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
    "sanitize_rich_text",
    "sanitize_filename",
    "sanitize_path",
    "sanitize_email",
    "sanitize_url",
    "strip_control_chars",
    "truncate",
]
