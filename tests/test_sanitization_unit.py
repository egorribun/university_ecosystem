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


def test_sanitize_rich_text_exceptions(monkeypatch):
    import nh3
    import pytest
    from fastapi import HTTPException

    def mock_clean(*args, **kwargs):
        raise Exception("nh3 fail")

    monkeypatch.setattr(nh3, "clean", mock_clean)
    with pytest.raises(HTTPException) as exc_info:
        sanitize_rich_text("<p>Hello</p>")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid payload signature"


def test_sanitize_filename_max_length():
    assert sanitize_filename("hello.txt", max_length=3) == "hel"
    assert sanitize_filename("hellotxt", max_length=4) == "hell"


def test_sanitize_path_edge_cases(monkeypatch):
    from pathlib import Path

    base = Path("/safe_dir")
    assert sanitize_path("file\x00.txt", base) is None

    def mock_resolve(*args, **kwargs):
        raise OSError("mock resolve error")

    monkeypatch.setattr(Path, "resolve", mock_resolve)
    assert sanitize_path("file.txt", base) is None


def test_sanitize_url_edge_cases():
    # Empty netloc/hostname
    assert sanitize_url("https://:8080") is None
    # IDN homograph attack
    assert sanitize_url("https://привет.рф") is None
    # IDN homograph starting with xn-- (has cyrillic)
    assert sanitize_url("https://xn--привет") == "https://xn--привет"
    # Punycode allowed
    assert (
        sanitize_url("https://xn--e1afmkfd.xn--p1ai") == "https://xn--e1afmkfd.xn--p1ai"
    )
    # Private / Local IP blocks
    assert sanitize_url("https://192.168.1.1") is None
    assert sanitize_url("https://10.0.0.1") is None
    assert sanitize_url("https://169.254.1.1") is None
    # Public IP allowed
    assert sanitize_url("https://8.8.8.8") == "https://8.8.8.8"
    # Value/UnicodeError
    assert sanitize_url("https://[invalid-ipv6-port") is None
    # Empty netloc branches
    assert sanitize_url("https:///path") is None
    assert sanitize_url("https:") is None

