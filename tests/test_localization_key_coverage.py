"""Every user-facing ``errors.*`` translation key used in ``app/`` must exist.

``translate`` falls back to the raw key when an entry is missing, which leaks
identifiers such as ``errors.chat.self_chat`` straight into API responses.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.core.localization.dictionary import TRANSLATIONS

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
_ERROR_KEY = re.compile(r"^errors(?:\.[a-z0-9_]+)+$")
_DICTIONARY = APP_ROOT / "core" / "localization" / "dictionary.py"


def _used_error_keys() -> dict[str, str]:
    used: dict[str, str] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path == _DICTIONARY:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _ERROR_KEY.match(node.value)
            ):
                used.setdefault(
                    node.value, f"{path.relative_to(APP_ROOT)}:{node.lineno}"
                )
    return used


def test_every_used_error_key_has_a_translation() -> None:
    missing = {
        key: where
        for key, where in _used_error_keys().items()
        if key not in TRANSLATIONS
    }
    assert not missing, f"error keys without translations: {missing}"


def test_every_translation_provides_both_locales() -> None:
    incomplete = [
        key
        for key, entry in TRANSLATIONS.items()
        if not entry.get("ru") or not entry.get("en")
    ]
    assert not incomplete
