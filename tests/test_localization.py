from starlette.datastructures import Headers, QueryParams

from app.core.localization import resolve_locale, translate


class _DummyRequest:
    def __init__(self, query: dict[str, str] | None = None, headers=None) -> None:
        self.query_params = QueryParams(query or {})
        self.headers = Headers(headers or {})


class _DummyUser:
    def __init__(self, preferred_locale: str | None = None) -> None:
        self.preferred_locale = preferred_locale


def test_resolve_locale_prefers_query_param_over_header():
    request = _DummyRequest(query={"lang": "ru"}, headers={"Accept-Language": "en"})

    assert resolve_locale(request=request) == "ru"


def test_resolve_locale_uses_user_preference():
    request = _DummyRequest(headers={"Accept-Language": "en-US"})
    user = _DummyUser(preferred_locale="ru")

    assert resolve_locale(request=request, user=user) == "ru"


def test_translate_falls_back_to_english():
    # Unknown locale should fall back to English
    assert translate("notifications.default_title", locale="de") == "Notification"
