from app.core.security_headers import add_security_headers


def test_security_headers_middleware():
    headers = {}
    add_security_headers(headers)
    assert "Content-Security-Policy" in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
