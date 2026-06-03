from pathlib import Path

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


def test_sanitize_html_basic():
    assert sanitize_html("<script>alert(1)</script>hello") == "hello"
    assert sanitize_html("<b>bold</b>", allow_basic_tags=True) == "<b>bold</b>"
    assert sanitize_html("<b>bold</b>", allow_basic_tags=False) == "bold"
    assert sanitize_html(None) == ""


def test_sanitize_rich_text():
    html = '<p>Hello <a href="https://example.com" onclick="bad()">World</a></p><script>alert(1)</script>'
    sanitized = sanitize_rich_text(html)
    assert "<p>Hello " in sanitized
    assert 'href="https://example.com"' in sanitized
    assert "onclick" not in sanitized
    assert "script" not in sanitized
    assert 'rel="noopener noreferrer"' in sanitized
    assert sanitize_rich_text(None) == ""


def test_sanitize_filename():
    # NFKD normalization decomposes ë into e + combining diaeresis
    assert sanitize_filename("hello/world.txt") == "hello_world.txt"
    assert sanitize_filename("../etc/passwd") == "_etc_passwd"
    assert sanitize_filename('invalid:"*?<>|chars.txt') == "invalid_______chars.txt"
    assert sanitize_filename("") == "unnamed"


def test_sanitize_path():
    # Use a relative-to-root path that resolves consistently in the test environment
    base = Path("C:/safe_dir") if Path("C:/").exists() else Path("/safe_dir")
    # Wrap in Path to ensure same type for comparison
    assert sanitize_path("file.txt", base) == base / "file.txt"
    assert sanitize_path("../../etc/passwd", base) is None
    assert sanitize_path("/absolute/path", base) is None


def test_sanitize_email():
    assert sanitize_email("  User@Example.COM  ") == "user@example.com"
    assert sanitize_email(None) == ""


def test_sanitize_url():
    assert sanitize_url("https://google.com") == "https://google.com"
    assert sanitize_url("javascript:alert(1)") is None
    assert sanitize_url("https://127.0.0.1") is None
    assert sanitize_url("https://user:pass@google.com") is None
    assert sanitize_url("https://[::1]") is None
    assert sanitize_url("") is None


def test_strip_control_chars():
    assert strip_control_chars("hello\x00world\n") == "helloworld\n"
    assert strip_control_chars("") == ""


def test_truncate():
    assert truncate("1234567890", 5) == "12..."
    assert truncate("short", 10) == "short"


def test_sanitize_optional_text():
    assert sanitize_optional_text(None) is None
    assert sanitize_optional_text(b"bytes") == "bytes"
    assert sanitize_optional_text("   ") is None
    assert sanitize_optional_text(123) == "123"
