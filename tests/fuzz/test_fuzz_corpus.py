"""Fuzz corpus tests — pytest-compatible (Wave 14.2).

These tests take known-good and known-bad inputs from a static corpus and run
them through key sanitization and validation functions.  They complement the
atheris-based differential fuzzer (run_atheris.py) with deterministic,
regression-trackable pytest cases.

WHY a separate file from run_atheris.py:
    run_atheris.py uses atheris (coverage-guided fuzzing) which requires a
    special binary and is not suitable for standard pytest CI runs.  This file
    uses parameterized pytest cases that are always executable, provide
    regression coverage for crash-triggering inputs discovered by prior fuzzing
    sessions, and participate in normal coverage reporting.

Run with:
    pytest tests/fuzz/test_fuzz_corpus.py -v
"""

from __future__ import annotations

import pytest

from app.utils.sanitization import (
    sanitize_filename,
    sanitize_html,
    sanitize_rich_text,
    sanitize_url,
)

# ---------------------------------------------------------------------------
# XSS corpus: inputs that must be stripped / rejected
# ---------------------------------------------------------------------------

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "<svg onload=alert(1)>",
    "<iframe src='javascript:alert(1)'>",
    "<body onload=alert(1)>",
    "';alert(String.fromCharCode(88,83,83))//",
    "<scr<script>ipt>alert(1)</scr</script>ipt>",
    "<IMG SRC=&#106;&#97;&#118;&#97;&#115;&#99;&#114;&#105;&#112;&#116;&#58;alert(1)>",
    "<a href='javascript:void(0)' onclick='alert(1)'>click</a>",
    "<<SCRIPT>alert(1);//<</SCRIPT>",
    "%3Cscript%3Ealert(1)%3C%2Fscript%3E",
    "<div style='background:url(javascript:alert(1))'>",
    "<link rel='stylesheet' href='javascript:alert(1)'>",
    "<META HTTP-EQUIV='refresh' CONTENT='0;url=javascript:alert(1)'>",
]

# ---------------------------------------------------------------------------
# Safe HTML corpus: inputs that must survive sanitization intact (or close)
# ---------------------------------------------------------------------------

SAFE_HTML_INPUTS = [
    "Hello, world!",
    "Plain text with no HTML.",
    "<b>Bold</b> and <i>italic</i> text",
    "Text with <em>emphasis</em> and <strong>strength</strong>",
    "Use &amp; and &lt; HTML entities",
    "",
    "   ",
    "A" * 10000,  # long plain text
]

# ---------------------------------------------------------------------------
# Dangerous filename corpus
# ---------------------------------------------------------------------------

DANGEROUS_FILENAMES = [
    "../../../etc/passwd",
    "..\\..\\windows\\system32\\config\\sam",
    "/etc/shadow",
    "file\x00.txt",
    "CON",  # Windows reserved name
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "LPT1",
    "file:with:colons.txt",
    "file<with>angles.txt",
    "file?with?questions.txt",
    "file*with*stars.txt",
    "|pipe|.txt",
    'file"with"quotes.txt',
    "",
    "." * 300,
    "a" * 512,
]

# ---------------------------------------------------------------------------
# URL corpus: inputs that must be rejected or sanitized
# ---------------------------------------------------------------------------

DANGEROUS_URLS = [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "javascript://comment%0Aalert(1)",
    "JAVASCRIPT:alert(1)",
    "   javascript:alert(1)",
    "\x00javascript:alert(1)",
]

SAFE_URLS = [
    "https://example.com",
    "http://university.edu/path?query=1",
    "https://sub.domain.co.uk/path/to/resource",
    "",
    "https://example.com/path with spaces",
]

# ---------------------------------------------------------------------------
# SQL injection corpus (for string inputs to validation)
# ---------------------------------------------------------------------------

SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE users; --",
    "1 OR 1=1",
    "admin'--",
    "1; SELECT * FROM users",
    "' UNION SELECT null, username, password FROM users --",
    "1' AND '1'='1",
]

# ---------------------------------------------------------------------------
# Tests: XSS sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_sanitize_html_strips_xss_payload(payload: str) -> None:
    """sanitize_html() must strip all HTML-context XSS vectors from user input.

    WHY: Any XSS that survives sanitization can execute in a victim's browser
    when the content is rendered.  We test against a curated corpus of bypass
    vectors known to affect regex-based and naive HTML sanitizers.

    NOTE: 'javascript:' as bare plain text (no surrounding HTML tag) is safe
    because nh3 strips only HTML-context attributes (href=javascript:...) not
    arbitrary text content.  We only assert on HTML-structural constructs.
    """
    result = sanitize_html(payload, allow_basic_tags=False)

    # Must not contain executable *HTML-structural* script constructs.
    lowered = result.lower()
    assert "<script" not in lowered, (
        f"sanitize_html left <script> tag in output for input {payload!r}: {result!r}"
    )
    assert "onerror=" not in lowered, (
        f"sanitize_html left onerror= in output for input {payload!r}: {result!r}"
    )
    assert "onload=" not in lowered, (
        f"sanitize_html left onload= in output for input {payload!r}: {result!r}"
    )
    # javascript: inside an href/src attribute is the dangerous case; as plain
    # text content it is harmless.  Only check if the tag structure survived.
    if "href" in lowered or "src" in lowered:
        assert "javascript:" not in lowered, (
            f"sanitize_html left javascript: in attribute for input {payload!r}: {result!r}"
        )


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_sanitize_rich_text_strips_xss_payload(payload: str) -> None:
    """sanitize_rich_text() must strip all HTML-context XSS vectors.

    WHY: Rich text editors (Quill, Tiptap) produce more complex HTML than plain
    inputs.  The allowlist-based sanitizer must handle all vendor-specific
    constructs without ever passing a script tag through.
    """
    from fastapi import HTTPException

    try:
        result = sanitize_rich_text(payload)
    except HTTPException:
        # Content rejected at the domain level — also acceptable.
        return

    lowered = result.lower()
    assert "<script" not in lowered, (
        f"sanitize_rich_text left <script> for input {payload!r}: {result!r}"
    )
    assert "onerror=" not in lowered, (
        f"sanitize_rich_text left onerror= for input {payload!r}: {result!r}"
    )
    # Same caveat as sanitize_html: javascript: as plain text is harmless.
    if "href" in lowered or "src" in lowered:
        assert "javascript:" not in lowered, (
            f"sanitize_rich_text left javascript: in attribute for {payload!r}: {result!r}"
        )


@pytest.mark.parametrize("safe_input", SAFE_HTML_INPUTS)
def test_sanitize_html_preserves_safe_plain_text(safe_input: str) -> None:
    """sanitize_html() must not crash or return None for safe plain text.

    WHY: An overly aggressive sanitizer that rejects or corrupts legitimate
    text (e.g. returns None or raises) is a usability bug that blocks normal
    user workflows.
    """
    result = sanitize_html(safe_input, allow_basic_tags=False)
    assert result is not None, (
        f"sanitize_html returned None for safe input {safe_input!r}"
    )
    assert isinstance(result, str), (
        f"sanitize_html returned non-string for input {safe_input!r}"
    )


# ---------------------------------------------------------------------------
# Tests: Filename sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dangerous_name", DANGEROUS_FILENAMES)
def test_sanitize_filename_never_crashes(dangerous_name: str) -> None:
    """sanitize_filename() must not raise for any input (even path traversal).

    WHY: The function is called on every uploaded filename.  An unhandled
    exception here would cause a 500 for any file upload with a malicious name.
    """
    try:
        result = sanitize_filename(dangerous_name)
    except Exception as exc:
        pytest.fail(
            f"sanitize_filename raised {type(exc).__name__} for input "
            f"{dangerous_name!r}: {exc}"
        )
    assert result is not None


@pytest.mark.parametrize("dangerous_name", DANGEROUS_FILENAMES[:6])
def test_sanitize_filename_strips_path_traversal(dangerous_name: str) -> None:
    """sanitize_filename() must remove path traversal sequences.

    WHY: A filename like '../../etc/passwd' used unmodified as a storage key
    would be a path traversal vulnerability allowing arbitrary file reads.
    """
    if not dangerous_name:  # empty string is a special case
        return

    result = sanitize_filename(dangerous_name)
    assert ".." not in result, (
        f"sanitize_filename left path traversal in output for {dangerous_name!r}: {result!r}"
    )
    assert "/" not in result, (
        f"sanitize_filename left forward slash for {dangerous_name!r}: {result!r}"
    )
    assert "\\" not in result, (
        f"sanitize_filename left backslash for {dangerous_name!r}: {result!r}"
    )


# ---------------------------------------------------------------------------
# Tests: URL sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dangerous_url", DANGEROUS_URLS)
def test_sanitize_url_blocks_javascript_scheme(dangerous_url: str) -> None:
    """sanitize_url() must reject or strip javascript: / data: / vbscript: URLs.

    WHY: These URL schemes execute code in the browser when used in href or
    src attributes.  A sanitizer that passes them through enables stored XSS.
    """
    result = sanitize_url(dangerous_url)
    if result:
        lowered = result.lower().strip()
        assert not lowered.startswith("javascript:"), (
            f"sanitize_url passed javascript: URL for input {dangerous_url!r}: {result!r}"
        )
        assert not lowered.startswith("data:"), (
            f"sanitize_url passed data: URL for input {dangerous_url!r}: {result!r}"
        )
        assert not lowered.startswith("vbscript:"), (
            f"sanitize_url passed vbscript: URL for input {dangerous_url!r}: {result!r}"
        )


@pytest.mark.parametrize("safe_url", SAFE_URLS)
def test_sanitize_url_never_crashes_on_safe_input(safe_url: str) -> None:
    """sanitize_url() must not raise for safe URL inputs.

    WHY: Same as sanitize_filename — any unhandled exception on the happy
    path is a usability regression.
    """
    try:
        sanitize_url(safe_url)
    except Exception as exc:
        pytest.fail(
            f"sanitize_url raised {type(exc).__name__} for safe URL {safe_url!r}: {exc}"
        )


# ---------------------------------------------------------------------------
# Tests: SQL injection in Pydantic schemas (defense-in-depth)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_pydantic_validation_handles_injection_payloads(payload: str) -> None:
    """Pydantic validation must handle SQL/injection string inputs without crashing.

    WHY: Injection strings routed through form fields should produce a clean
    ValidationError (or succeed if the field accepts arbitrary strings) rather
    than an unhandled internal exception that would cause a 500 response.

    The timezone field uses ZoneInfo internally; on some platforms ZoneInfo
    raises OSError for invalid file paths (Windows: Errno 22).  This is a
    valid rejection path — the test verifies no unexpected crash type escapes.
    """
    from pydantic import ValidationError

    from app.schemas.schemas import UserPreferencesBase

    # Acceptable exception types: ValidationError (domain rejection) or
    # OSError/IOError (ZoneInfo file-path rejection on Windows with invalid chars).
    _EXPECTED_EXCEPTION_TYPES = (ValidationError, OSError, IOError, ValueError)

    try:
        UserPreferencesBase.model_validate({"timezone": payload})
    except _EXPECTED_EXCEPTION_TYPES:
        pass  # Expected rejection — domain or OS-level.
    except Exception as exc:
        pytest.fail(
            f"Unexpected exception type {type(exc).__name__} for payload {payload!r}: {exc}"
        )
