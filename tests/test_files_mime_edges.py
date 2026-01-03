from app.utils import files


def test_normalize_mime_type_strips_parameters_and_whitespace():
    assert (
        files._normalize_mime_type("  TEXT/PLAIN; charset=utf-8  ")  # noqa: SLF001
        == "text/plain"
    )


def test_polyglot_detection_flags_script_in_pdf():
    payload = b"%PDF-1.4\n<script>alert(1)</script>"
    result = files._looks_like_polyglot(payload, "application/pdf")  # noqa: SLF001
    assert result is True


def test_polyglot_detection_allows_clean_svg():
    payload = (
        b"<svg xmlns='http://www.w3.org/2000/svg'><rect width='10' height='10'/></svg>"
    )
    assert files._looks_like_polyglot(payload, "image/svg+xml") is False  # noqa: SLF001
