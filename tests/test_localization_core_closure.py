from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.localization import core


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"),
        (" RU ", "ru"),
        ("de", "en"),
        (None, "en"),
        ("", "en"),
    ],
)
def test_normalize_locale(value, expected):
    assert core.normalize_locale(value) == expected


def test_localized_text_prefers_requested_locale_then_falls_back():
    assert core.localized_text("en", en="English", ru="Русский") == "English"
    assert core.localized_text("en", en=" ", ru="Русский") == "Русский"
    assert core.localized_text("ru", en="English", ru="Русский") == "Русский"
    assert core.localized_text("ru", en="English", ru=" ") == "English"
    assert core.localized_text("ru", en=None, ru=None) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        (" EN ", "en"),
        ("ru-RU", "ru"),
        ("en_US", "en"),
        ("de-DE", None),
    ],
)
def test_internal_locale_normalization(value, expected):
    assert core._normalize_locale(value) == expected


class _Unstringifiable:
    def __str__(self):
        raise TypeError("cannot stringify")


def test_accept_language_parsing_quality_and_invalid_values(monkeypatch):
    assert core._locale_from_accept_language(None) is None
    assert core._locale_from_accept_language(_Unstringifiable()) is None
    assert core._locale_from_accept_language(" , de-DE;q=bad, fr") is None
    assert core._locale_from_accept_language("de;q=0.9, ru-RU;q=0.8, en;q=0.7") == "ru"
    assert core._locale_from_accept_language("en;q=0.2, ru;q=0.9") == "ru"
    assert core._locale_from_accept_language("en;q=0.5;unused=1") == "en"

    monkeypatch.setattr(core, "_normalize_locale", lambda _value: "xx")
    assert core._locale_from_accept_language("xx,xx") is None


def test_resolve_locale_direct_and_query_parameter_precedence():
    request = SimpleNamespace(query_params={"lang": "de", "locale": "ru-RU"})
    assert core.resolve_locale("EN-us", request=request) == "en"
    assert core.resolve_locale(request=request) == "ru"


class _BrokenParams:
    def get(self, key):
        raise (AttributeError if key == "lang" else TypeError)("broken")


def test_resolve_locale_handles_broken_query_params_and_user_preferences():
    request = SimpleNamespace(query_params=_BrokenParams())
    user = SimpleNamespace(preferred_locale=None, preferred_language="ru")
    assert core.resolve_locale(request=request, user=user) == "ru"


def test_resolve_locale_uses_user_attribute_order_and_accept_language():
    user = SimpleNamespace(preferred_locale="", preferred_language="en-US", locale="ru")
    request = SimpleNamespace(
        query_params=None,
        headers={"Accept-Language": "ru;q=0.9,en-US;q=0.8"},
    )
    assert core.resolve_locale(request=request, user=user) == "en"

    no_user = SimpleNamespace(
        query_params=None, headers={"Accept-Language": "ru;q=0.9"}
    )
    assert core.resolve_locale(request=no_user) == "ru"

    empty_user = SimpleNamespace(
        preferred_locale=None,
        preferred_language=None,
        locale=None,
        language=None,
    )
    unknown_header = SimpleNamespace(
        query_params=None, headers={"Accept-Language": "de"}
    )
    assert core.resolve_locale(request=unknown_header, user=empty_user) == "en"
    no_headers = SimpleNamespace(query_params=None, headers=None)
    assert core.resolve_locale(request=no_headers, user=empty_user) == "en"


class _BrokenHeaders:
    def get(self, key):
        raise AttributeError("headers unavailable")


def test_resolve_locale_header_error_and_default_fallback():
    request = SimpleNamespace(query_params=None, headers=_BrokenHeaders())
    assert core.resolve_locale(request=request, default="ru") == "ru"
    assert core.resolve_locale(default="de") == "en"
