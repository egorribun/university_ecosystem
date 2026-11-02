"""Enforce finite historical Gitleaks fingerprint identities."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GITLEAKS_IGNORE_PATH = REPOSITORY_ROOT / ".gitleaksignore"
APPROVED_FINGERPRINTS = (
    "089a99548453760e3325fca925c92f8975343b72:services/pkg/logging/logging_test.go:generic-api-key:21",
    "0fc7af03b7f403ba6c77a2aaf26602f9e60927b4:.github/workflows/ci.yml:generic-api-key:1621",
    "0fc7af03b7f403ba6c77a2aaf26602f9e60927b4:.github/workflows/ci.yml:generic-api-key:1680",
    "31f848784087f3e481135d36f27eafa516016002:docs/superpowers/plans/STATUS.md:generic-api-key:23",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1000",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1007",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1014",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1021",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1028",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1035",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1042",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1049",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1056",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1063",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1070",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1077",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1084",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1091",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:1098",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:986",
    "527478a3d58905270a94e06e39ef4f2c07270f35:.secrets.baseline:generic-api-key:993",
    "ab4063f9064b34ae2c234d60da4a2c74463f330d:services/gateway/internal/config/config_test.go:generic-api-key:458",
    "c7402955b6071a80a4ff3b0367c63b78de0144fd:docs/superpowers/plans/2026-10-19-reset-link-fragment-redaction.md:generic-api-key:15",
    "d9948f315e05d3c28cdb3e5439a9b04b72515fe7:docs/superpowers/plans/2026-09-22-mvp-safe-pause-handoff.md:generic-api-key:39",
    "f0ed193e7824078f1047ad7f782014059ed5450b:tests/test_internal_hmac_secret_security.py:generic-api-key:16",
)


# One observed historical code-expression false positive. This does not approve
# another commit, path, rule or line, including later copies of the same code.
CODE_EXPRESSION_FINGERPRINT = (
    "75de40e472f1ef8fccedea286b0b5b456c29f1c5:"
    "tests/test_cwv_rum_security.py:generic-api-key:939"
)


# Public test-password digest moved into added historical baseline lines.
# Approval binds only this commit/path/rule/line, not later copies of the hash.
PUBLIC_TEST_PASSWORD_HASH_FINGERPRINT = (
    "3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9:.secrets.baseline:generic-api-key:1820"
)
REVIEWED_ADDITIONS = (
    CODE_EXPRESSION_FINGERPRINT,
    PUBLIC_TEST_PASSWORD_HASH_FINGERPRINT,
)


def _assert_exact_approved_fingerprints(path: Path) -> None:
    """Keep exceptions bound to immutable commit, path, rule, and line."""

    assert path.is_file()
    fingerprints = path.read_text(encoding="utf-8").splitlines()
    expected = sorted((*APPROVED_FINGERPRINTS, *REVIEWED_ADDITIONS))

    assert len(APPROVED_FINGERPRINTS) == 25
    assert len(set(REVIEWED_ADDITIONS)) == 2
    assert not set(REVIEWED_ADDITIONS).intersection(APPROVED_FINGERPRINTS)
    assert len(fingerprints) == 27
    assert fingerprints == expected
    assert len(set(fingerprints)) == len(fingerprints)
    assert set(fingerprints) == set(expected)
    assert [
        fingerprint
        for fingerprint in fingerprints
        if fingerprint not in REVIEWED_ADDITIONS
    ] == list(APPROVED_FINGERPRINTS)
    assert all(
        re.fullmatch(
            r"[0-9a-f]{40}:[A-Za-z0-9._/-]+:generic-api-key:[1-9][0-9]*",
            fingerprint,
        )
        for fingerprint in fingerprints
    )


def test_gitleaks_ignore_contains_only_exact_approved_fingerprints() -> None:
    _assert_exact_approved_fingerprints(GITLEAKS_IGNORE_PATH)


def test_exact_27_identity_inventory_accepts_only_the_reviewed_additions(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".gitleaksignore"
    fingerprints = sorted((*APPROVED_FINGERPRINTS, *REVIEWED_ADDITIONS))
    path.write_text("\n".join(fingerprints) + "\n", encoding="utf-8")

    _assert_exact_approved_fingerprints(path)


@pytest.mark.parametrize("reviewed_fingerprint", REVIEWED_ADDITIONS)
@pytest.mark.parametrize(
    "mutation",
    [
        "commit",
        "path",
        "rule",
        "line",
        "global_fingerprint",
        "wildcard_commit",
        "wildcard_path",
        "wildcard_rule",
        "wildcard_line",
        "path_backslash",
        "duplicate",
        "unapproved_extra",
        "missing_original",
        "missing_reviewed",
        "changed_original",
        "reordered",
        "blank_line",
    ],
)
def test_disposition_guard_rejects_scope_and_original_inventory_drift(
    tmp_path: Path, mutation: str, reviewed_fingerprint: str
) -> None:
    fingerprints = sorted((*APPROVED_FINGERPRINTS, *REVIEWED_ADDITIONS))
    parts = reviewed_fingerprint.split(":")
    replacement = None
    field_changes = {
        "commit": (0, "0" * 40),
        "path": (1, "tests/unapproved_case.py"),
        "rule": (2, "unapproved-rule"),
        "line": (3, "940"),
        "wildcard_commit": (0, "*"),
        "wildcard_path": (1, "tests/*"),
        "wildcard_rule": (2, "*"),
        "wildcard_line": (3, "*"),
    }
    if mutation in field_changes:
        index, value = field_changes[mutation]
        parts[index] = value
        replacement = ":".join(parts)
    elif mutation == "global_fingerprint":
        replacement = ":".join(parts[1:])
    elif mutation == "path_backslash":
        parts[1] = parts[1].replace("/", "\\") if "/" in parts[1] else "\\" + parts[1]
        replacement = ":".join(parts)
    elif mutation == "duplicate":
        fingerprints.append(reviewed_fingerprint)
    elif mutation == "unapproved_extra":
        parts[3] = "940"
        fingerprints.append(":".join(parts))
    elif mutation == "missing_reviewed":
        fingerprints.remove(reviewed_fingerprint)
    elif mutation == "missing_original":
        fingerprints.remove(APPROVED_FINGERPRINTS[0])
    elif mutation == "changed_original":
        original = APPROVED_FINGERPRINTS[0].split(":")
        original[3] = "22"
        fingerprints[fingerprints.index(APPROVED_FINGERPRINTS[0])] = ":".join(original)
    elif mutation == "reordered":
        fingerprints.reverse()
    elif mutation == "blank_line":
        fingerprints.append("")

    if replacement is not None:
        fingerprints[fingerprints.index(reviewed_fingerprint)] = replacement
    if mutation != "reordered":
        fingerprints.sort()
    path = tmp_path / ".gitleaksignore"
    path.write_text("\n".join(fingerprints) + "\n", encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_exact_approved_fingerprints(path)
