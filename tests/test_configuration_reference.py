"""Regression checks for the operator-facing configuration reference."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env_assignments() -> dict[str, list[int]]:
    assignments: defaultdict[str, list[int]] = defaultdict(list)
    pattern = re.compile(r"^\s*([A-Z][A-Z0-9_]*)=")
    for line_number, line in enumerate(
        (ROOT / ".env.example").read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        match = pattern.match(line)
        if match:
            assignments[match.group(1)].append(line_number)
    return dict(assignments)


def test_env_example_has_no_duplicate_assignments() -> None:
    duplicate_assignments = {
        key: lines for key, lines in _env_assignments().items() if len(lines) > 1
    }

    assert duplicate_assignments == {}


def test_configuration_reference_tracks_runtime_defaults_and_security_semantics() -> (
    None
):
    document = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")

    rows = {
        match.group(1): line
        for line in document.splitlines()
        if (match := re.search(r"\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", line))
    }
    expected_rows = {
        "ALGORITHM": "| `RS256` |",
        "MFA_CHALLENGE_TTL_SECONDS": "| `600`",
        "RATE_LIMIT_DEFAULT": "| `200/minute`",
        "SPICEDB_PRESHARED_KEY": "| `development-preshared-key`",
        "RUST_OPTIMIZER_URL": "| `http://rust-optimizer:8080`",
        "OUTBOX_BATCH_SIZE": "| `20`",
        "OUTBOX_POLL_INTERVAL_SECONDS": "| `5.0`",
        "SMTP_SECURITY": "| `none`",
        "SMTP_STARTTLS": "| `false`",
        "MFA_EMAIL_OTP_HMAC_KEYS": "| Empty locally",
        "MFA_EMAIL_DELIVERY_KEKS": "| Empty locally",
        "MFA_TRUSTED_DEVICE_HMAC_KEYS": "| Empty locally",
        "REVOCATION_REDIS_URL": "| Required outside development",
        "RATE_LIMIT_STORAGE_URI": "| `memory://`",
    }
    for variable, expected in expected_rows.items():
        assert variable in rows
        assert expected in rows[variable]

    assert "`HS256`" in document
    assert "development/testing only" in document
    assert "`NOTIFY_PROVIDER`" not in document
    assert "`RETENTION_LOGS_DAYS`" not in document
    assert "`RETENTION_CHATS_DAYS`" not in document


def test_local_example_marks_mfa_ttl_as_an_explicit_override() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "# Local profile override: runtime default is 600 seconds." in example
    assert "MFA_CHALLENGE_TTL_SECONDS=300" in example
