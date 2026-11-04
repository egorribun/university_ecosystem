"""AUD-422: CONFIGURATION.md documents every typed ``Settings`` field.

The runtime ``Settings`` model is the source of truth for operator variables.
Each field is read from the environment under its uppercased field name, so a
new field without a CONFIGURATION.md row fails here instead of silently
becoming an undocumented knob.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
_ROW = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", re.MULTILINE)


def _documented_variables() -> set[str]:
    document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    return set(_ROW.findall(document))


def _documented_default_cells() -> dict[str, str]:
    document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    return {
        match.group(1): line.rstrip().removesuffix("|").rsplit("|", 1)[-1].strip()
        for line in document.splitlines()
        if (match := re.match(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", line))
    }


def _settings_variables() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def test_configuration_reference_documents_every_settings_field() -> None:
    missing = sorted(_settings_variables() - _documented_variables())

    assert missing == []


def test_timeout_poll_and_retention_settings_are_documented() -> None:
    documented = _documented_variables()

    assert {
        "SMTP_MFA_TOTAL_TIMEOUT_SECONDS",
        "NOTIFICATIONS_SCHEDULER_POLL_SECONDS",
        "NOTIFICATION_QUEUE_DEAD_LETTER_RETENTION_DAYS",
    } <= documented


def test_timeout_poll_and_retention_defaults_match_settings() -> None:
    rows = _documented_default_cells()
    for name in (
        "SMTP_MFA_TOTAL_TIMEOUT_SECONDS",
        "NOTIFICATIONS_SCHEDULER_POLL_SECONDS",
        "NOTIFICATION_QUEUE_DEAD_LETTER_RETENTION_DAYS",
    ):
        assert rows[name] == f"`{Settings.model_fields[name.lower()].default}`"


def test_plain_scalar_defaults_match_runtime_settings() -> None:
    rows = _documented_default_cells()
    checked = 0
    for name, field in Settings.model_fields.items():
        default = field.default
        if type(default) not in (bool, int, float):
            continue
        cell = rows[name.upper()]
        value = re.fullmatch(
            r"`(true|false|-?\d+(?:\.\d+)?)`(?: \(backend\))?", cell, re.IGNORECASE
        )
        if value is None:
            continue
        checked += 1
        rendered = value.group(1).lower()
        if type(default) is bool:
            assert rendered == str(default).lower(), name
        else:
            assert rendered not in {"true", "false"}, name
            assert Decimal(rendered) == Decimal(str(default)), name
    assert checked >= 100


def test_password_policy_defaults_are_documented_at_runtime_values() -> None:
    document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    rows = {
        match.group(1): line
        for line in document.splitlines()
        if (match := re.match(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", line))
    }

    assert "| `12`" in rows["PASSWORD_MIN_LENGTH"]
    assert "| `2`" in rows["PASSWORD_ZXCVBN_MIN_SCORE"]
