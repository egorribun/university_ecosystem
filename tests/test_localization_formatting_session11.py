"""Session 11 coverage: app/core/localization/formatting.py pure functions.

No DB, no async. Exercises _normalize_weekday_token, translate (fallback chain +
.format), translate_lesson_type (alias/canonical/unknown/None/empty), and
resolve_weekday_index + weekday_aliases (alias resolution incl. localized RU/EN
short forms). Translation values asserted are read verbatim from
app/core/localization/dictionary.py.
"""

from __future__ import annotations

from app.core.localization.formatting import (
    _normalize_weekday_token,
    resolve_weekday_index,
    translate,
    translate_lesson_type,
    weekday_aliases,
)


# ── _normalize_weekday_token ──────────────────────────────────────────────────
def test_normalize_weekday_token_none_returns_none() -> None:
    assert _normalize_weekday_token(None) is None


def test_normalize_weekday_token_empty_string_returns_none() -> None:
    assert _normalize_weekday_token("") is None


def test_normalize_weekday_token_strips_nonalpha_and_lowercases() -> None:
    assert _normalize_weekday_token("Mon-2!") == "mon"
    assert _normalize_weekday_token("ПН.") == "пн"  # cyrillic kept (isalpha)


def test_normalize_weekday_token_all_nonalpha_returns_none() -> None:
    assert _normalize_weekday_token("123 ---") is None


# ── translate ─────────────────────────────────────────────────────────────────
def test_translate_resolved_locale_ru() -> None:
    assert translate("schedule.lesson.type.lecture", locale="ru") == "Лекция"


def test_translate_falls_back_to_default_locale() -> None:
    # "de" is unsupported -> resolve_locale normalizes to "en"
    assert translate("schedule.lesson.type.lecture", locale="de") == "Lecture"


def test_translate_missing_key_returns_default() -> None:
    assert translate("no.such.key.session11", default="FALLBACK") == "FALLBACK"


def test_translate_missing_key_no_default_returns_key() -> None:
    assert translate("no.such.key.session11") == "no.such.key.session11"


def test_translate_format_interpolation() -> None:
    out = translate("errors.already_exists", locale="en", identifier="X42")
    assert out == "Record already exists: X42"


def test_translate_format_missing_kwarg_returns_unformatted() -> None:
    # kwargs present but missing the {identifier} placeholder -> KeyError swallowed
    out = translate("errors.already_exists", locale="en", wrong_kwarg="z")
    assert out == "Record already exists: {identifier}"


def test_translate_no_kwargs_returns_text_unchanged() -> None:
    assert translate("notifications.default_title", locale="en") == "Notification"


# ── translate_lesson_type ─────────────────────────────────────────────────────
def test_translate_lesson_type_none() -> None:
    assert translate_lesson_type(None) is None


def test_translate_lesson_type_empty_returns_empty() -> None:
    assert translate_lesson_type("   ") == ""  # stripped to "" then returned


def test_translate_lesson_type_ru_alias() -> None:
    assert translate_lesson_type("Лекция", locale="ru") == "Лекция"
    assert translate_lesson_type("лк", locale="en") == "Lecture"


def test_translate_lesson_type_canonical_english() -> None:
    assert translate_lesson_type("practice", locale="en") == "Practical class"


def test_translate_lesson_type_canonical_via_translations_fallback() -> None:
    # "lab" is a TRANSLATIONS key but NOT an _LESSON_TYPE_ALIASES key
    # -> exercises the canonical-resolved-from-translations branch
    assert translate_lesson_type("lab", locale="en") == "Lab work"


def test_translate_lesson_type_unknown_returns_raw() -> None:
    assert translate_lesson_type("Physics 101", locale="en") == "Physics 101"


# ── weekday_aliases + resolve_weekday_index ───────────────────────────────────
def test_weekday_aliases_contains_english_canonical_and_short() -> None:
    aliases = weekday_aliases()
    assert aliases["monday"] == 0
    assert aliases["mon"] == 0
    assert aliases["sunday"] == 6
    assert aliases["sun"] == 6


def test_weekday_aliases_contains_localized_russian() -> None:
    aliases = weekday_aliases()
    assert aliases["понедельник"] == 0
    assert aliases["пн"] == 0
    assert aliases["воскресенье"] == 6
    assert aliases["вс"] == 6


def test_weekday_aliases_is_cached() -> None:
    assert weekday_aliases() is weekday_aliases()  # lru_cache returns same dict


def test_resolve_weekday_index_english() -> None:
    assert resolve_weekday_index("Wednesday") == 2
    assert resolve_weekday_index("wed") == 2
    assert resolve_weekday_index("FRI") == 4


def test_resolve_weekday_index_russian() -> None:
    assert resolve_weekday_index("Вторник") == 1
    assert resolve_weekday_index("сб") == 5


def test_resolve_weekday_index_none_input() -> None:
    assert resolve_weekday_index(None) is None
    assert resolve_weekday_index("   ") is None


def test_resolve_weekday_index_unknown() -> None:
    assert resolve_weekday_index("Caturday") is None
