import pytest

from app.api import news
from app.localization import DEFAULT_LOCALE


def test_normalized_cache_locale_supported_and_default_fallback():
    assert news._normalized_cache_locale("en") == "en"
    assert news._normalized_cache_locale("ru") == "ru"
    assert news._normalized_cache_locale(None) == DEFAULT_LOCALE


@pytest.mark.parametrize(
    "value,expected",
    [
        ("text", "text"),
        ("   spaced   ", "   spaced   "),
        ("   ", None),
        (123, None),
    ],
)
def test_non_empty_text(value, expected):
    assert news._non_empty_text(value) == expected


def test_localized_text_prefers_requested_locale_with_fallbacks():
    # English takes English value first, falls back to Russian
    assert (
        news._localized_text("en", ru_value="Русский", en_value="English") == "English"
    )
    assert news._localized_text("en", ru_value="Русский", en_value=None) == "Русский"

    # Default locale uses English value first, then Russian fallback
    assert (
        news._localized_text(DEFAULT_LOCALE, ru_value="Русский", en_value="English")
        == "English"
    )
    assert (
        news._localized_text(DEFAULT_LOCALE, ru_value="", en_value="English")
        == "English"
    )


def test_news_cache_keys_include_all_locales_and_legacy_prefixes():
    keys = news._news_cache_keys(news_id=42)

    # Base list cache key and per-locale patterns
    assert news._LEGACY_NEWS_LIST_CACHE_KEY in keys
    for locale in news._CACHE_LOCALES:
        expected_wildcard = f"{news._NEWS_LIST_CACHE_PREFIX}:{locale}:*"
        assert expected_wildcard in keys

    # Item-specific cache keys include legacy and localized variants
    assert news._legacy_news_item_cache_key(42) in keys
    for locale in news._CACHE_LOCALES:
        assert news._news_item_cache_key(42, locale) in keys
