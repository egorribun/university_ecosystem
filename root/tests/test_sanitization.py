"""Tests for input sanitization utilities."""

import pytest
from pathlib import Path

from app.utils.sanitization import (
    sanitize_html,
    sanitize_filename,
    sanitize_path,
    sanitize_email,
    sanitize_url,
    strip_control_chars,
    truncate,
)


class TestSanitizeHtml:
    """Tests for sanitize_html."""

    def test_escapes_script_tags(self):
        """Test script tags are escaped."""
        result = sanitize_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_escapes_onclick(self):
        """Test onclick attributes are escaped."""
        result = sanitize_html('<div onclick="evil()">click</div>')
        assert "onclick" not in result or "&lt;" in result

    def test_empty_string(self):
        """Test empty string stays empty."""
        assert sanitize_html("") == ""

    def test_allow_basic_tags(self):
        """Test basic formatting tags can be preserved."""
        result = sanitize_html("<b>bold</b> <i>italic</i>", allow_basic_tags=True)
        assert "<b>" in result
        assert "</b>" in result
        assert "<i>" in result


class TestSanitizeFilename:
    """Tests for sanitize_filename."""

    def test_removes_path_separators(self):
        """Test path separators are removed."""
        result = sanitize_filename("../../../etc/passwd")
        assert "/" not in result
        assert ".." not in result

    def test_removes_hidden_file_prefix(self):
        """Test leading dots are removed."""
        result = sanitize_filename(".hidden")
        assert not result.startswith(".")

    def test_empty_returns_unnamed(self):
        """Test empty filename returns 'unnamed'."""
        assert sanitize_filename("") == "unnamed"

    def test_truncates_long_names(self):
        """Test long names are truncated."""
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name, max_length=255)
        assert len(result) <= 255
        assert result.endswith(".txt")

    def test_removes_invalid_windows_chars(self):
        """Test invalid Windows characters are removed."""
        result = sanitize_filename('file<>:"|?*.txt')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result


class TestSanitizePath:
    """Tests for sanitize_path."""

    def test_blocks_traversal(self):
        """Test path traversal is blocked."""
        base = Path("/app/uploads")
        result = sanitize_path("../../etc/passwd", base)
        assert result is None

    def test_allows_valid_path(self):
        """Test valid paths within base are allowed."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            subdir = base / "subdir"
            subdir.mkdir()

            result = sanitize_path("subdir", base)
            assert result is not None
            assert result == subdir


class TestSanitizeEmail:
    """Tests for sanitize_email."""

    def test_normalizes_case(self):
        """Test email is lowercased."""
        assert sanitize_email("USER@EXAMPLE.COM") == "user@example.com"

    def test_strips_whitespace(self):
        """Test whitespace is stripped."""
        assert sanitize_email("  user@example.com  ") == "user@example.com"

    def test_empty_string(self):
        """Test empty email returns empty."""
        assert sanitize_email("") == ""


class TestSanitizeUrl:
    """Tests for sanitize_url."""

    def test_allows_https(self):
        """Test HTTPS URLs are allowed."""
        result = sanitize_url("https://example.com/page")
        assert result == "https://example.com/page"

    def test_blocks_javascript(self):
        """Test javascript: URLs are blocked."""
        result = sanitize_url("javascript:alert(1)")
        assert result is None

    def test_blocks_data_urls(self):
        """Test data: URLs are blocked."""
        result = sanitize_url("data:text/html,<script>alert(1)</script>")
        assert result is None

    def test_blocks_ftp(self):
        """Test FTP URLs are blocked by default."""
        result = sanitize_url("ftp://files.example.com")
        assert result is None

    def test_empty_url(self):
        """Test empty URL returns None."""
        assert sanitize_url("") is None


class TestStripControlChars:
    """Tests for strip_control_chars."""

    def test_removes_null_byte(self):
        """Test null bytes are removed."""
        result = strip_control_chars("hello\x00world")
        assert "\x00" not in result
        assert result == "helloworld"

    def test_preserves_newlines(self):
        """Test newlines are preserved."""
        result = strip_control_chars("line1\nline2")
        assert "\n" in result


class TestTruncate:
    """Tests for truncate."""

    def test_short_text_unchanged(self):
        """Test short text is unchanged."""
        assert truncate("hello", 10) == "hello"

    def test_long_text_truncated(self):
        """Test long text is truncated with suffix."""
        result = truncate("hello world", 8)
        assert len(result) == 8
        assert result.endswith("...")

    def test_custom_suffix(self):
        """Test custom suffix works."""
        result = truncate("hello world", 8, suffix="…")
        assert result.endswith("…")
