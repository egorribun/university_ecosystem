"""
Pydantic validators for sanitized input types.

Provides type-safe validators that automatically sanitize user input
to prevent XSS and injection attacks.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import AfterValidator

from app.utils.sanitization import (
    sanitize_email,
    sanitize_filename,
    sanitize_html,
    sanitize_optional_text,
    sanitize_rich_text,
    sanitize_url,
    strip_control_chars,
    truncate,
)


def _sanitize_html_validator(value: Any) -> str:
    """Sanitize HTML, escaping all tags."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return sanitize_html(value, allow_basic_tags=False)


def _sanitize_html_with_basic_tags(value: Any) -> str:
    """Sanitize HTML, allowing basic formatting tags."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return sanitize_html(value, allow_basic_tags=True)


def _sanitize_rich_text_validator(value: Any) -> str:
    """Sanitize rich text HTML with whitelist approach."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return sanitize_rich_text(value)


def _sanitize_email_validator(value: Any) -> str:
    """Normalize and sanitize email address."""
    if not isinstance(value, str):
        return ""
    return sanitize_email(value)


def _sanitize_filename_validator(value: Any) -> str:
    """Sanitize filename to prevent path traversal."""
    if not isinstance(value, str):
        return "unnamed"
    return sanitize_filename(value)


def _strip_control_chars_validator(value: Any) -> str:
    """Strip control characters from text."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return strip_control_chars(value)


def _sanitize_url_validator(value: Any) -> str | None:
    """Validate and sanitize URL."""
    if not isinstance(value, str):
        return None
    return sanitize_url(value)


def _sanitize_optional_text_validator(value: Any) -> str | None:
    """Sanitize optional text input."""
    return sanitize_optional_text(value)


def _truncate_256(value: str) -> str:
    """Truncate string to 256 characters."""
    return truncate(value, 256)


def _truncate_1000(value: str) -> str:
    """Truncate string to 1000 characters."""
    return truncate(value, 1000)


def _truncate_5000(value: str) -> str:
    """Truncate string to 5000 characters."""
    return truncate(value, 5000)


# Annotated types for use in Pydantic models
# These automatically sanitize input when validating

# Plain text - escapes all HTML
SanitizedStr = Annotated[str, AfterValidator(_sanitize_html_validator)]

# Rich text - allows basic formatting tags (b, i, em, strong)
RichTextStr = Annotated[str, AfterValidator(_sanitize_html_with_basic_tags)]

# Email - normalized and lowercase
SanitizedEmail = Annotated[str, AfterValidator(_sanitize_email_validator)]

# Filename - safe for filesystem operations
SafeFilename = Annotated[str, AfterValidator(_sanitize_filename_validator)]

# Text without control characters
CleanStr = Annotated[str, AfterValidator(_strip_control_chars_validator)]

# URL - validated and sanitized
SafeUrl = Annotated[str | None, AfterValidator(_sanitize_url_validator)]

# Optional sanitized text (trims whitespace, None if empty)
SanitizedInput = Annotated[
    str | None, AfterValidator(_sanitize_optional_text_validator)
]

# Short text fields with length limits
ShortSanitizedStr = Annotated[
    str,
    AfterValidator(_sanitize_html_validator),
    AfterValidator(_truncate_256),
]

# Medium text fields
MediumSanitizedStr = Annotated[
    str,
    AfterValidator(_sanitize_html_validator),
    AfterValidator(_truncate_1000),
]

# Long text/content fields
LongSanitizedStr = Annotated[
    str,
    AfterValidator(_sanitize_html_validator),
    AfterValidator(_truncate_5000),
]

# Rich text content - whitelist-based sanitization for user content
SafeRichText = Annotated[str, AfterValidator(_sanitize_rich_text_validator)]


__all__ = [
    "CleanStr",
    "LongSanitizedStr",
    "MediumSanitizedStr",
    "RichTextStr",
    "SafeFilename",
    "SafeRichText",
    "SafeUrl",
    "SanitizedEmail",
    "SanitizedInput",
    "SanitizedStr",
    "ShortSanitizedStr",
]
