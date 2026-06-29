"""Tests for schema validators (app/schemas/validators.py).

Validates each validator function with valid, None, non-string, and malicious
inputs. Also tests Annotated types in Pydantic models.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.validators import (
    CleanStr,
    LongSanitizedStr,
    MediumSanitizedStr,
    RichTextStr,
    SafeFilename,
    SafeRichText,
    SafeUrl,
    SanitizedEmail,
    SanitizedInput,
    SanitizedStr,
    ShortSanitizedStr,
    _sanitize_email_validator,
    _sanitize_filename_validator,
    _sanitize_html_validator,
    _sanitize_html_with_basic_tags,
    _sanitize_optional_text_validator,
    _sanitize_rich_text_validator,
    _sanitize_url_validator,
    _strip_control_chars_validator,
    _truncate_256,
    _truncate_1000,
    _truncate_5000,
)


# ---------------------------------------------------------------------------
# _sanitize_html_validator
# ---------------------------------------------------------------------------


class TestSanitizeHtmlValidator:
    """Tests for the strict HTML sanitizer (escapes all tags)."""

    def test_valid_plain_text(self):
        """Plain text passes through unchanged."""
        assert _sanitize_html_validator("Hello, World!") == "Hello, World!"

    def test_none_input(self):
        """None returns empty string."""
        assert _sanitize_html_validator(None) == ""

    def test_non_string_input(self):
        """Non-string is converted via str()."""
        result = _sanitize_html_validator(42)
        assert result == "42"

    def test_xss_payload_escaped(self):
        """XSS script tags are stripped/escaped."""
        malicious = '<script>alert("xss")</script>'
        result = _sanitize_html_validator(malicious)
        assert "<script>" not in result
        assert "alert" in result  # Text content preserved without tags

    def test_html_entities_safe(self):
        """HTML entities are handled safely."""
        result = _sanitize_html_validator("<b>bold</b>")
        assert "<b>" not in result

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert _sanitize_html_validator("") == ""


# ---------------------------------------------------------------------------
# _sanitize_html_with_basic_tags
# ---------------------------------------------------------------------------


class TestSanitizeHtmlWithBasicTags:
    """Tests for the permissive HTML sanitizer (allows b/i/em/strong)."""

    def test_allows_bold(self):
        """<b> tag is preserved."""
        result = _sanitize_html_with_basic_tags("<b>bold</b>")
        assert "<b>" in result
        assert "</b>" in result

    def test_allows_italic(self):
        """<i> tag is preserved."""
        result = _sanitize_html_with_basic_tags("<i>italic</i>")
        assert "<i>" in result

    def test_allows_em(self):
        """<em> tag is preserved."""
        result = _sanitize_html_with_basic_tags("<em>emphasis</em>")
        assert "<em>" in result

    def test_allows_strong(self):
        """<strong> tag is preserved."""
        result = _sanitize_html_with_basic_tags("<strong>strong</strong>")
        assert "<strong>" in result

    def test_strips_dangerous_tags(self):
        """Script and other dangerous tags are stripped."""
        result = _sanitize_html_with_basic_tags('<script>alert(1)</script><b>ok</b>')
        assert "<script>" not in result
        assert "<b>ok</b>" in result

    def test_none_input(self):
        """None returns empty string."""
        assert _sanitize_html_with_basic_tags(None) == ""

    def test_non_string_input(self):
        """Non-string is converted via str()."""
        result = _sanitize_html_with_basic_tags(123)
        assert result == "123"


# ---------------------------------------------------------------------------
# _sanitize_email_validator
# ---------------------------------------------------------------------------


class TestSanitizeEmailValidator:
    """Tests for email normalization."""

    def test_normalizes_email(self):
        """Email is lowercased and stripped."""
        assert _sanitize_email_validator("  User@Example.COM  ") == "user@example.com"

    def test_none_returns_empty(self):
        """None is not a string → returns empty string."""
        assert _sanitize_email_validator(None) == ""

    def test_non_string_returns_empty(self):
        """Non-string returns empty string."""
        assert _sanitize_email_validator(42) == ""

    def test_already_normalized(self):
        """Already normalized email passes through."""
        assert _sanitize_email_validator("user@test.com") == "user@test.com"


# ---------------------------------------------------------------------------
# _sanitize_filename_validator
# ---------------------------------------------------------------------------


class TestSanitizeFilenameValidator:
    """Tests for filename sanitization (path traversal prevention)."""

    def test_normal_filename(self):
        """Normal filename passes through."""
        result = _sanitize_filename_validator("report.pdf")
        assert result == "report.pdf"

    def test_path_traversal_blocked(self):
        """Path traversal attempt ../../../etc/passwd is sanitized."""
        result = _sanitize_filename_validator("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_none_returns_unnamed(self):
        """None returns 'unnamed'."""
        assert _sanitize_filename_validator(None) == "unnamed"

    def test_non_string_returns_unnamed(self):
        """Non-string returns 'unnamed'."""
        assert _sanitize_filename_validator(42) == "unnamed"

    def test_empty_string_returns_unnamed(self):
        """Empty filename returns 'unnamed'."""
        result = _sanitize_filename_validator("")
        assert result == "unnamed"

    def test_hidden_file_prefix_stripped(self):
        """Leading dots are stripped to prevent hidden files."""
        result = _sanitize_filename_validator(".hidden")
        assert not result.startswith(".")


# ---------------------------------------------------------------------------
# _strip_control_chars_validator
# ---------------------------------------------------------------------------


class TestStripControlCharsValidator:
    """Tests for control character stripping."""

    def test_removes_null_byte(self):
        """Null bytes are removed."""
        result = _strip_control_chars_validator("hello\x00world")
        assert "\x00" not in result
        assert "helloworld" in result

    def test_removes_control_chars(self):
        """Control characters \\x00-\\x1f are removed (except \\t, \\n, \\r)."""
        # \\x01 (SOH) should be removed
        result = _strip_control_chars_validator("test\x01\x02\x03data")
        assert "\x01" not in result
        assert "\x02" not in result
        assert "testdata" in result

    def test_preserves_newlines_and_tabs(self):
        """Tabs (\\x09), newlines (\\x0a), carriage returns (\\x0d) are preserved."""
        result = _strip_control_chars_validator("line1\nline2\ttab\rreturn")
        assert "\n" in result
        assert "\t" in result

    def test_none_input(self):
        """None returns empty string."""
        assert _strip_control_chars_validator(None) == ""

    def test_non_string_input(self):
        """Non-string is converted via str()."""
        result = _strip_control_chars_validator(42)
        assert result == "42"


# ---------------------------------------------------------------------------
# _sanitize_url_validator
# ---------------------------------------------------------------------------


class TestSanitizeUrlValidator:
    """Tests for URL validation and sanitization."""

    def test_valid_https_url(self):
        """Valid HTTPS URL passes through."""
        url = "https://example.com/path"
        assert _sanitize_url_validator(url) == url

    def test_valid_http_url(self):
        """Valid HTTP URL passes through."""
        url = "http://example.com"
        assert _sanitize_url_validator(url) == url

    def test_blocks_javascript_scheme(self):
        """javascript: scheme is blocked."""
        assert _sanitize_url_validator("javascript:alert(1)") is None

    def test_blocks_data_scheme(self):
        """data: scheme is blocked."""
        assert _sanitize_url_validator("data:text/html,<h1>Hi</h1>") is None

    def test_none_returns_none(self):
        """None (not a string) returns None."""
        assert _sanitize_url_validator(None) is None

    def test_non_string_returns_none(self):
        """Non-string returns None."""
        assert _sanitize_url_validator(42) is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert _sanitize_url_validator("") is None

    def test_blocks_localhost(self):
        """localhost URLs are blocked (SSRF protection)."""
        assert _sanitize_url_validator("http://localhost/admin") is None
        assert _sanitize_url_validator("http://127.0.0.1/admin") is None


# ---------------------------------------------------------------------------
# _truncate_* boundary tests
# ---------------------------------------------------------------------------


class TestTruncation:
    """Tests for truncation validators at exact boundaries."""

    @pytest.mark.parametrize(
        ("truncator", "max_length"),
        [
            (_truncate_256, 256),
            (_truncate_1000, 1000),
            (_truncate_5000, 5000),
        ],
        ids=["truncate_256", "truncate_1000", "truncate_5000"],
    )
    def test_under_limit_unchanged(self, truncator, max_length):
        """Text shorter than limit passes through unchanged."""
        text = "a" * (max_length - 1)
        assert truncator(text) == text

    @pytest.mark.parametrize(
        ("truncator", "max_length"),
        [
            (_truncate_256, 256),
            (_truncate_1000, 1000),
            (_truncate_5000, 5000),
        ],
        ids=["truncate_256", "truncate_1000", "truncate_5000"],
    )
    def test_exact_limit_unchanged(self, truncator, max_length):
        """Text exactly at the limit passes through unchanged."""
        text = "a" * max_length
        assert truncator(text) == text

    @pytest.mark.parametrize(
        ("truncator", "max_length"),
        [
            (_truncate_256, 256),
            (_truncate_1000, 1000),
            (_truncate_5000, 5000),
        ],
        ids=["truncate_256", "truncate_1000", "truncate_5000"],
    )
    def test_over_limit_truncated(self, truncator, max_length):
        """Text exceeding the limit is truncated with '...' suffix."""
        text = "a" * (max_length + 100)
        result = truncator(text)
        assert len(result) == max_length
        assert result.endswith("...")


# ---------------------------------------------------------------------------
# _sanitize_optional_text_validator
# ---------------------------------------------------------------------------


class TestSanitizeOptionalTextValidator:
    """Tests for optional text sanitization."""

    def test_none_returns_none(self):
        """None input returns None."""
        assert _sanitize_optional_text_validator(None) is None

    def test_non_empty_string_passes(self):
        """Non-empty string passes through."""
        assert _sanitize_optional_text_validator("hello") == "hello"

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string returns None."""
        assert _sanitize_optional_text_validator("   ") is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert _sanitize_optional_text_validator("") is None


# ---------------------------------------------------------------------------
# _sanitize_rich_text_validator
# ---------------------------------------------------------------------------


class TestSanitizeRichTextValidator:
    """Tests for rich text HTML sanitization."""

    def test_allows_safe_tags(self):
        """Rich text allows p, br, b, i, a tags."""
        html = "<p>Hello <b>world</b></p>"
        result = _sanitize_rich_text_validator(html)
        assert "<p>" in result
        assert "<b>" in result

    def test_strips_script(self):
        """Script tags are stripped from rich text."""
        html = '<p>OK</p><script>alert("xss")</script>'
        result = _sanitize_rich_text_validator(html)
        assert "<script>" not in result
        assert "<p>OK</p>" in result

    def test_none_input(self):
        """None returns empty string."""
        assert _sanitize_rich_text_validator(None) == ""

    def test_non_string_input(self):
        """Non-string is converted via str()."""
        result = _sanitize_rich_text_validator(42)
        assert result == "42"


# ---------------------------------------------------------------------------
# Annotated types in Pydantic models
# ---------------------------------------------------------------------------


class TestAnnotatedTypesInPydanticModel:
    """Verify that Annotated validator types work correctly in Pydantic models."""

    def test_sanitized_str_in_model(self):
        """SanitizedStr strips HTML tags in a Pydantic model."""

        class TestModel(BaseModel):
            name: SanitizedStr

        model = TestModel(name="<b>Bold</b> text")
        assert "<b>" not in model.name
        assert "Bold" in model.name

    def test_short_sanitized_str_truncates(self):
        """ShortSanitizedStr truncates to 256 characters."""

        class TestModel(BaseModel):
            title: ShortSanitizedStr

        long_text = "a" * 300
        model = TestModel(title=long_text)
        assert len(model.title) <= 256

    def test_medium_sanitized_str_truncates(self):
        """MediumSanitizedStr truncates to 1000 characters."""

        class TestModel(BaseModel):
            description: MediumSanitizedStr

        long_text = "a" * 1100
        model = TestModel(description=long_text)
        assert len(model.description) <= 1000

    def test_long_sanitized_str_truncates(self):
        """LongSanitizedStr truncates to 5000 characters."""

        class TestModel(BaseModel):
            content: LongSanitizedStr

        long_text = "a" * 5100
        model = TestModel(content=long_text)
        assert len(model.content) <= 5000

    def test_sanitized_email_normalizes(self):
        """SanitizedEmail normalizes email in a model."""

        class TestModel(BaseModel):
            email: SanitizedEmail

        model = TestModel(email="  USER@EXAMPLE.COM  ")
        assert model.email == "user@example.com"

    def test_safe_filename_blocks_traversal(self):
        """SafeFilename blocks path traversal in a model."""

        class TestModel(BaseModel):
            file: SafeFilename

        model = TestModel(file="../../../etc/passwd")
        assert ".." not in model.file
        assert "/" not in model.file

    def test_clean_str_strips_control_chars(self):
        """CleanStr strips control characters in a model."""

        class TestModel(BaseModel):
            text: CleanStr

        model = TestModel(text="hello\x00\x01world")
        assert "\x00" not in model.text
        assert "\x01" not in model.text

    def test_safe_url_validates(self):
        """SafeUrl validates URLs in a model."""

        class TestModel(BaseModel):
            url: SafeUrl

        model = TestModel(url="https://example.com")
        assert model.url == "https://example.com"

    def test_safe_url_blocks_javascript(self):
        """SafeUrl rejects javascript: URLs in a model."""

        class TestModel(BaseModel):
            url: SafeUrl

        model = TestModel(url="javascript:alert(1)")
        assert model.url is None

    def test_sanitized_input_optional(self):
        """SanitizedInput returns None for empty/whitespace."""

        class TestModel(BaseModel):
            note: SanitizedInput

        model = TestModel(note="   ")
        assert model.note is None

    def test_rich_text_str_allows_formatting(self):
        """RichTextStr allows basic formatting tags."""

        class TestModel(BaseModel):
            content: RichTextStr

        model = TestModel(content="<b>bold</b> and <i>italic</i>")
        assert "<b>" in model.content
        assert "<i>" in model.content
