"""Closure tests for localization fallback and malformed dictionary entries."""

from __future__ import annotations

from app.core.localization import core, formatting


def test_translate_tries_default_locale_after_requested_locale_misses(monkeypatch):
    monkeypatch.setattr(core, "resolve_locale", lambda **_kwargs: "xx")

    assert formatting.translate("notifications.default_title") == "Notification"


def test_translate_uses_any_non_empty_translation_as_last_fallback(monkeypatch):
    translations = dict(formatting.TRANSLATIONS)
    translations["session.closure.only_fr"] = {"fr": "Bonjour"}
    monkeypatch.setattr(formatting, "TRANSLATIONS", translations)
    monkeypatch.setattr(core, "resolve_locale", lambda **_kwargs: "xx")

    assert formatting.translate("session.closure.only_fr") == "Bonjour"


def test_weekday_aliases_skip_missing_and_non_alphabetic_dictionary_values(
    monkeypatch,
):
    translations = dict(formatting.TRANSLATIONS)
    translations.pop("schedule.weekday.tuesday", None)
    translations["schedule.weekday.monday"] = {"en": "123"}
    monkeypatch.setattr(formatting, "TRANSLATIONS", translations)

    static_aliases = dict(formatting._WEEKDAY_STATIC_ALIASES)
    static_aliases["monday"] = ("---",)
    monkeypatch.setattr(formatting, "_WEEKDAY_STATIC_ALIASES", static_aliases)
    formatting.weekday_aliases.cache_clear()
    try:
        aliases = formatting.weekday_aliases()
    finally:
        formatting.weekday_aliases.cache_clear()

    assert aliases["tue"] == 1
    assert "123" not in aliases
    assert "---" not in aliases
