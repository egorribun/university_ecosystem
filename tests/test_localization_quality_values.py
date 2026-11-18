"""Reject unacceptable header weights without changing locale precedence."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.auth.login import _login_auth_error_for_request_locale
from app.core.localization import core


def _request(header: str, *, query: bytes = b"") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login/json",
            "headers": [(b"accept-language", header.encode("ascii"))],
            "query_string": query,
        }
    )


@pytest.mark.parametrize(
    "quality",
    ("0", "0.000", "-0", "-0.1", "1.001", "2", "NaN", "inf", "-inf", "bad", ""),
)
def test_header_without_acceptable_supported_weight_has_no_candidate(quality: str):
    assert core._locale_from_accept_language(f"ru;q={quality}") is None


@pytest.mark.parametrize("quality", ("1.001", "2", "NaN", "inf", "bad"))
def test_invalid_weight_cannot_outrank_valid_supported_language(quality: str):
    assert core._locale_from_accept_language(f"ru;q={quality}, en;q=0.5") == "en"


@pytest.mark.parametrize(
    ("header", "expected"),
    (
        ("ru;q=0.001,en;q=0", "ru"),
        ("ru;Q=1.000,en;q=0.9", "ru"),
        ("ru;q=0.1,en;q=0.9", "en"),
        ("ru,en;q=0.9", "ru"),
        ("ru;q=0.5,en;q=0.5", "ru"),
        ("en;q=0.5,ru;q=0.5", "en"),
        ("ru-RU;q=0.8,en-US;q=0.7", "ru"),
    ),
)
def test_valid_weights_and_stable_ties_keep_existing_matching(header, expected):
    assert core._locale_from_accept_language(header) == expected


@pytest.mark.parametrize("header", ("ru;q=0", "ru;q=bad", "ru;q=2", "ru;q=NaN"))
def test_real_request_uses_default_when_header_has_no_acceptable_candidate(header):
    request = _request(header)
    assert core.resolve_locale(request=request) == "en"
    assert core.resolve_locale(request=request, default="ru") == "ru"


def test_explicit_query_and_user_preferences_still_precede_header():
    request = _request("ru;q=0,en;q=1", query=b"lang=ru")
    assert core.resolve_locale("en", request=request) == "en"
    assert core.resolve_locale(request=request) == "ru"
    assert core.resolve_locale(
        request=_request("ru;q=0,en;q=1"),
        user=SimpleNamespace(preferred_locale="ru"),
    ) == "ru"


@pytest.mark.parametrize(
    ("header", "default", "expected"),
    (
        ("*", "ru", "ru"),
        ("*;q=0", "ru", "ru"),
        ("de;q=1", "ru", "ru"),
        ("ru;q=0,*;q=1", "en", "en"),
        ("en;q=0,ru;q=0", "ru", "ru"),
        ("*;q=1,en;q=0.5", "ru", "en"),
    ),
)
def test_no_new_wildcard_expansion_or_not_acceptable_response(
    header, default, expected
):
    # The existing application fallback is retained. This is not a complete
    # RFC 4647 matcher or an implementation of HTTP 406 negotiation.
    assert core.resolve_locale(request=_request(header), default=default) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (401, "Could not validate credentials"),
        (423, "Too many failed attempts. Your account is temporarily locked."),
    ),
)
@pytest.mark.parametrize("header", ("ru;q=0", "ru;q=NaN,en;q=1"))
def test_login_error_translation_keeps_auth_status_headers_and_safe_locale(
    status, expected, header
):
    original = HTTPException(
        status_code=status,
        detail="private original",
        headers={"WWW-Authenticate": "Bearer", "Retry-After": "30"},
    )
    result = _login_auth_error_for_request_locale(original, _request(header))
    assert result is not None
    assert result.status_code == status
    assert result.headers == {"WWW-Authenticate": "Bearer", "Retry-After": "30"}
    assert result.detail == expected
    assert original.detail == "private original"
