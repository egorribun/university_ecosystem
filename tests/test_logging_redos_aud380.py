from __future__ import annotations

import subprocess
import sys

import pytest

from app.core.logging import _redact_free_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail alice+alerts@example.com now", "mail [REDACTED] now"),
        ("mail .+alice@example.com now", "mail .+[REDACTED] now"),
        ("mail .+@example.com now", "mail .+@example.com now"),
        ("a@b and redis@10.0.0.1", "a@b and redis@10.0.0.1"),
        ("mail " + "a" * 1000 + "@example.com", "mail [REDACTED]"),
        ("mail üabc.test@example.com", "mail üabc[REDACTED]"),
        ("mail üabc@example.com", "mail üabc@example.com"),
        ("a@b.cc+person@example.com", "[REDACTED][REDACTED]"),
        ("a@b.cc-person@example.com", "[REDACTED][REDACTED]"),
        ("a@b.cc+@example.com", "[REDACTED][REDACTED]"),
        (
            "a@b.cc+person@example.com+x@y.org",
            "[REDACTED][REDACTED][REDACTED]",
        ),
        ("üfoo@bar.co+person@example.com", "üfoo@[REDACTED]"),
        ("a@b.cc__person@example.com", "a@[REDACTED]"),
        ("a@b.cc.person@example.com", "[REDACTED]@example.com"),
    ],
)
def test_email_redaction_preserves_matching_behavior(text: str, expected: str) -> None:
    assert _redact_free_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("build   :   555-0199", "build   :   555-0199"),
        ("identifier 555-0199", "identifier 555-0199"),
        ("record=: 555-0199", "record=: [REDACTED]"),
        ("phone   =   555.123.4567", "phone   =   [REDACTED]"),
        ("phone=: 555.123.4567", "phone=: 555.123.4567"),
    ],
)
def test_phone_redaction_preserves_context_matching(text: str, expected: str) -> None:
    assert _redact_free_text(text) == expected


def test_email_redaction_handles_long_non_email_candidate_promptly() -> None:
    program = (
        "from app.core.logging import _redact_free_text\n"
        "candidate = 'a.' * 120000\n"
        "assert _redact_free_text(candidate + ' alice@example.com') == "
        "candidate + ' [REDACTED]'\n"
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and inline test program
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr


def test_email_redaction_handles_many_adjacent_addresses_promptly() -> None:
    program = (
        "from app.core.logging import _redact_free_text\n"
        "candidate = 'a@b.cc+' * 12000 + 'person@example.com'\n"
        "assert _redact_free_text(candidate) == '[REDACTED]' * 12001\n"
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and inline test program
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr


def test_phone_redaction_handles_many_matches_promptly() -> None:
    program = (
        "from app.core.logging import _redact_free_text\n"
        "candidate = '555-0199; ' * 12000\n"
        "result = _redact_free_text(candidate + 'build 555-0199; phone: 555.123.4567')\n"
        "assert result == '[REDACTED]; ' * 12000 + 'build 555-0199; phone: [REDACTED]'\n"
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and inline test program
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
