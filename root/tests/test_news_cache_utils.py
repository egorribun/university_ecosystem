import re

from app.api import news


def test_normalized_cache_locale_accepts_supported_locales():
    assert news._normalized_cache_locale("en") == "en"
    assert news._normalized_cache_locale("ru") == "ru"


def test_normalized_cache_locale_defaults_to_ru_for_unknown():
    assert news._normalized_cache_locale("es") == news.DEFAULT_LOCALE
    assert news._normalized_cache_locale(None) == news.DEFAULT_LOCALE


def test_news_list_cache_key_reflects_locale_and_params():
    key = news._news_list_cache_key("en", 10, None, "v1")
    assert f":en:" in key
    ru_key = news._news_list_cache_key("es", 10, None, "v1")
    assert f":{news.DEFAULT_LOCALE}:" in ru_key


def test_news_item_cache_key_uses_normalized_locale():
    key = news._news_item_cache_key(5, "en")
    assert key == "news:item:5:en"
    default_key = news._news_item_cache_key(7, "es")
    assert default_key.endswith(f":{news.DEFAULT_LOCALE}")


def test_news_cache_keys_include_legacy_and_localized_variants():
    keys = news._news_cache_keys(3)
    legacy_item_keys = [k for k in keys if re.match(r"news:item:3", k)]
    assert any(key.startswith(news._LEGACY_NEWS_ITEM_PREFIX) for key in keys)
    assert any(key.endswith(":ru") for key in legacy_item_keys)
    assert news._LEGACY_NEWS_LIST_CACHE_KEY in keys


def test_non_empty_text_filters_blank_strings():
    assert news._non_empty_text("text") == "text"
    assert news._non_empty_text("   ") is None
    assert news._non_empty_text(123) is None
