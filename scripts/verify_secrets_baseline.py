#!/usr/bin/env python3
"""Fail-closed verification for a detect-secrets baseline.

The committed baseline is an allowlist of individual findings, not merely a
list of files.  A fresh scan must therefore be a subset of the baseline (old
entries are allowed to become stale when a secret is removed), while a pull
request must not add a new suppression relative to a trusted base baseline.

An owner-authored policy update may opt into exact-identity dispositions only
when the protected workflow explicitly confirms the author and candidate change.
Other pull requests use the trusted base and ignore candidate policy additions.

Usage::

    python scripts/verify_secrets_baseline.py BASELINE CURRENT_SCAN
    python scripts/verify_secrets_baseline.py BASELINE CURRENT_SCAN \
        --trusted-base-baseline TRUSTED_BASELINE \
        --trusted-base-source-sha BASE_SHA

Exit code 0 means no unsuppressed findings were detected.  Exit code 1 means
the current scan found a finding that is not in the committed baseline, or a
pull request added a suppression for a finding relative to its trusted base, or
the source delta added an inline secret-allowlist pragma. The source check
runs when --trusted-base-source-sha is supplied. Exit code 2 means an
artifact or trusted source delta is missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


class BaselineArtifactError(ValueError):
    """Raised when a baseline or scan artifact cannot be trusted."""


class SourceDeltaError(ValueError):
    """Raised when a trusted source delta cannot be verified safely."""


_SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_INLINE_SECRET_ALLOWLIST_PATTERN = re.compile(
    r"\bpragma\s*:\s*allowlist\s+secret\b", re.IGNORECASE
)
_DIFF_HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_FALSE_POSITIVE_ALLOWED_TYPE = "Hex High Entropy String"
_FALSE_POSITIVE_HEX_CATEGORIES = frozenset(
    {
        "public_integrity_digest",
        "documented_crypto_test_vector",
        "independent_contract_fingerprint",
    }
)
_FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES = {
    "ci_test_contract_sentinel": frozenset(
        {
            (".github/workflows/ci.yml", "Basic Auth Credentials"),
            (".github/workflows/ci.yml", "Secret Keyword"),
            (".github/workflows/nightly-full-gate.yml", "Secret Keyword"),
            (
                "frontend/scripts/frontend-quality-contract.test.mjs",
                "Secret Keyword",
            ),
            (
                "frontend/src/api/hooks/__tests__/campusConfig.test.ts",
                "Secret Keyword",
            ),
            (
                "tests/test_live_stand_resource_guard.py",
                "Base64 High Entropy String",
            ),
            (
                "tests/test_start_docker_orphan_ownership.py",
                "Base64 High Entropy String",
            ),
        }
    ),
    "public_package_integrity_metadata": frozenset(
        {
            (
                "frontend/scripts/stryker-inventory.test.mjs",
                "Base64 High Entropy String",
            ),
        }
    ),
    "public_totp_algorithm_alphabet": frozenset(
        {
            (
                "frontend/tests/e2e-live/totp-recovery.live.spec.ts",
                "Base64 High Entropy String",
            ),
        }
    ),
    "documented_dummy_password_hash": frozenset(
        {
            ("app/auth/security.py", "Secret Keyword"),
            ("tests/test_seed_admin_data.py", "Secret Keyword"),
            (
                "tests/test_seed_demo_account_preservation.py",
                "Secret Keyword",
            ),
            ("tests/test_seed_demo_messenger.py", "Secret Keyword"),
        }
    ),
    "synthetic_hmac_test_material": frozenset(
        {
            (
                "services/gateway/internal/handlers/handlers_identity_closure_test.go",
                "Secret Keyword",
            ),
            (
                "services/ws-hub/pkg/hub/replay_security_adversarial_test.go",
                "Secret Keyword",
            ),
            (
                "tests/integration/test_historical_attendance_sender_migrations_postgres.py",
                "Secret Keyword",
            ),
        }
    ),
    "synthetic_fakeredis_lease_token": frozenset(
        {
            ("tests/test_chat_command_failure_paths.py", "Secret Keyword"),
        }
    ),
    "domain_resource_contract_fixture": frozenset(
        {
            ("tests/test_live_stand_resource_guard.py", "Secret Keyword"),
        }
    ),
    "internal_demo_stand_account_fixture": frozenset(
        {
            ("frontend/tests/e2e-live/fixtures.ts", "Secret Keyword"),
        }
    ),
}
_FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS = {
    "internal_demo_stand_account_fixture": (
        "docs/superpowers/plans/MVP_MASTER_PLAN.md:37",
        "external operational status remains unverified",
    ),
}
_FALSE_POSITIVE_CATEGORIES = _FALSE_POSITIVE_HEX_CATEGORIES | frozenset(
    _FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES
)
_INDEPENDENT_CONTRACT_FINGERPRINT_PATH = (
    "tests/fixtures/full-backend-reusable-baseline.v3.yaml"
)
_FALSE_POSITIVE_IDENTITY_FIELDS = frozenset({"path", "type", "hashed_secret_bytes"})
_FALSE_POSITIVE_RECORD_FIELDS = frozenset(
    {
        "identity",
        "category",
        "evidence",
        "owner",
        "reviewed_on",
        "expires_on",
        "approval_status",
    }
)
_FALSE_POSITIVE_DOCUMENT_FIELDS = frozenset({"schema_version", "records"})
_FALSE_POSITIVE_POLICY_PATH = "quality/security-false-positive-dispositions.json"
_FALSE_POSITIVE_RECORD_LIMIT = 512
_FALSE_POSITIVE_EVIDENCE_LIMIT = 1000
_FALSE_POSITIVE_OWNER_LIMIT = 120
_FALSE_POSITIVE_PLACEHOLDER_OWNERS = frozenset(
    {"", "owner", "pending", "tbd", "unknown", "n/a", "todo"}
)
_DISPOSITION_WILDCARDS = frozenset("*?[]")


def _decode_git_quoted_path(value: str) -> str:
    """Decode Git's C-quoted pathname form without interpreting source text."""

    if not (value.startswith('"') and value.endswith('"')):
        return value

    escaped = value[1:-1]
    decoded = bytearray()
    simple_escapes = {
        '"': b'"',
        "\\": b"\\",
        "a": b"\a",
        "b": b"\b",
        "f": b"\f",
        "n": b"\n",
        "r": b"\r",
        "t": b"\t",
        "v": b"\v",
    }
    index = 0
    while index < len(escaped):
        character = escaped[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8", errors="surrogateescape"))
            index += 1
            continue

        index += 1
        if index >= len(escaped):
            raise SourceDeltaError("malformed quoted Git pathname")
        escape = escaped[index]
        if escape in simple_escapes:
            decoded.extend(simple_escapes[escape])
            index += 1
            continue
        if escape not in "01234567":
            raise SourceDeltaError("unsupported quoted Git pathname escape")

        digits = escape
        index += 1
        while index < len(escaped) and len(digits) < 3 and escaped[index] in "01234567":
            digits += escaped[index]
            index += 1
        decoded.append(int(digits, 8))

    return decoded.decode("utf-8", errors="surrogateescape")


def _path_from_added_file_header(header: str) -> str | None:
    # Git uses a literal tab after a quoted pathname as its header delimiter;
    # tabs inside a quoted pathname are escaped and are therefore preserved.
    raw_path = header[4:].split("\t", 1)[0]
    if raw_path == "/dev/null":
        return None
    if raw_path.startswith('"'):
        path = _decode_git_quoted_path(raw_path)
    else:
        path = raw_path
    if not path.startswith("b/"):
        raise SourceDeltaError("unexpected Git diff path prefix")
    return path[2:]


def _find_added_inline_secret_pragmas(diff_text: str) -> list[tuple[str, int]]:
    """Return only safe path/line identities for newly added marker lines."""

    findings: list[tuple[str, int]] = []
    current_path: str | None = None
    new_line_number: int | None = None

    lines = diff_text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line in lines:
        if line.startswith("diff --git "):
            current_path = None
            new_line_number = None
            continue

        if new_line_number is None and line.startswith("+++ "):
            current_path = _path_from_added_file_header(line)
            continue

        hunk = _DIFF_HUNK_PATTERN.match(line)
        if line.startswith("@@"):
            if hunk is None:
                raise SourceDeltaError("unrecognized Git diff hunk header")
            new_line_number = int(hunk.group(1))
            continue

        if new_line_number is None:
            if line.startswith("+") and not line.startswith("+++ "):
                raise SourceDeltaError("Git diff addition has no hunk header")
            continue

        if line.startswith("+"):
            if current_path is None:
                raise SourceDeltaError("Git diff addition has no destination path")
            if _INLINE_SECRET_ALLOWLIST_PATTERN.search(line[1:]) is not None:
                findings.append((current_path, new_line_number))
            new_line_number += 1
        elif line.startswith("-"):
            continue
        elif line.startswith(" "):
            new_line_number += 1
        elif line.startswith("\\ No newline at end of file"):
            continue
        else:
            raise SourceDeltaError("unrecognized Git diff hunk format")

    return findings


def find_new_inline_secret_pragmas(
    trusted_base_sha: str, *, repository_root: str | Path
) -> list[tuple[str, int]]:
    """Compare two immutable Git trees and find newly added suppression markers.

    The trusted base must be a full, nonzero commit SHA. Git diagnostics and
    source lines are never returned to the caller.
    """

    if (
        not isinstance(trusted_base_sha, str)
        or _SOURCE_SHA_PATTERN.fullmatch(trusted_base_sha) is None
        or trusted_base_sha == "0" * 40
    ):
        raise SourceDeltaError("trusted source base SHA is invalid")

    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceDeltaError("repository root is unavailable") from error

    git_executable = shutil.which("git")
    if git_executable is None:
        raise SourceDeltaError("Git source comparison could not run")
    try:
        git_executable = str(Path(git_executable).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceDeltaError("Git source comparison could not run") from error

    def run_git(*arguments: str) -> str:
        try:
            # Git arguments are fixed except for the already-validated full source SHA.
            # The executable is absolute and shell interpretation is disabled.
            result = subprocess.run(  # noqa: S603
                [git_executable, *arguments],
                cwd=root,
                capture_output=True,
                check=False,
                shell=False,
            )
        except (OSError, UnicodeError) as error:
            raise SourceDeltaError("Git source comparison could not run") from error
        if result.returncode != 0:
            raise SourceDeltaError("Git source comparison failed")
        try:
            return result.stdout.decode("utf-8", errors="surrogateescape")
        except UnicodeError as error:
            raise SourceDeltaError(
                "Git source comparison could not be decoded"
            ) from error

    run_git("cat-file", "-e", f"{trusted_base_sha}^{{commit}}")
    head_sha = run_git("rev-parse", "--verify", "HEAD^{commit}").strip()
    if _SOURCE_SHA_PATTERN.fullmatch(head_sha) is None:
        raise SourceDeltaError("current source commit is unavailable")

    diff_text = run_git(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--unified=0",
        "--no-renames",
        "--text",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        trusted_base_sha,
        head_sha,
        "--",
    )
    return _find_added_inline_secret_pragmas(diff_text)


@dataclass(frozen=True, slots=True)
class FindingIdentity:
    """Stable, non-secret identity used when comparing detector findings."""

    path: str
    finding_type: str
    hashed_secret: str
    # Detector line numbers are useful diagnostics but are not stable identity:
    # inserting an unrelated line must not require a baseline rewrite.
    line_number: int = field(compare=False, hash=False)

    def sort_key(self) -> tuple[str, int, str, str]:
        """Return a deterministic ordering without exposing the digest."""

        return (self.path, self.line_number, self.finding_type, self.hashed_secret)

    def display(self) -> str:
        """Return a safe diagnostic label (never the secret or its digest)."""

        return f"{self.path}:{self.line_number} ({self.finding_type})"


def canonical_path(value: str) -> str:
    """Return the repository path spelling shared by Windows and POSIX jobs.

    This small helper intentionally lives in the executable verifier as well
    as ``scripts.secrets_baseline``: invoking this file directly puts the
    ``scripts`` directory (rather than the repository root) on ``sys.path``.
    Keeping the verifier standalone avoids a fragile import-time path hack.
    """

    return "/".join(part for part in value.replace("\\", "/").split("/") if part)


def load_json(path: str | Path) -> Any:
    """Load JSON using an explicit encoding and fail closed on I/O errors."""

    try:
        with Path(path).open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        raise BaselineArtifactError(f"file not found: {error}") from error
    except json.JSONDecodeError as error:
        raise BaselineArtifactError(f"invalid JSON: {error}") from error
    except UnicodeError as error:
        raise BaselineArtifactError(f"invalid UTF-8: {error}") from error
    except OSError as error:
        raise BaselineArtifactError(f"unable to read artifact: {error}") from error


def _canonical_result_path(raw_path: object, *, artifact: str) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise BaselineArtifactError(
            f"{artifact}: result paths must be non-empty strings"
        )

    # Inspect the separator-normalised spelling before dropping duplicate
    # separators so absolute POSIX and UNC paths cannot be reinterpreted as
    # repository-relative paths by canonicalisation.
    normalised_raw_path = raw_path.replace("\\", "/")
    if normalised_raw_path.startswith("/") or re.match(
        r"^[A-Za-z]:", normalised_raw_path
    ):
        raise BaselineArtifactError(
            f"{artifact}: result path must be a normalised repository-relative path"
        )

    path = canonical_path(raw_path)
    # Artifacts are repository-relative.  Reject absolute paths, drive-letter
    # paths, and traversal segments rather than silently normalising them.
    if (
        not path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise BaselineArtifactError(
            f"{artifact}: result path must be a normalised repository-relative path"
        )
    return path


def _parse_finding(
    result_path: str,
    raw_finding: object,
    *,
    artifact: str,
    index: int,
) -> FindingIdentity:
    if not isinstance(raw_finding, dict):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] must be an object"
        )

    finding_type = raw_finding.get("type")
    if not isinstance(finding_type, str) or not finding_type.strip():
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid type"
        )

    hashed_secret = raw_finding.get("hashed_secret")
    if not isinstance(hashed_secret, str) or not hashed_secret.strip():
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid hashed_secret"
        )

    line_number = raw_finding.get("line_number")
    if (
        isinstance(line_number, bool)
        or not isinstance(line_number, int)
        or line_number < 1
    ):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid line_number"
        )

    filename = raw_finding.get("filename")
    if filename is not None:
        canonical_filename = _canonical_result_path(filename, artifact=artifact)
        if canonical_filename != result_path:
            raise BaselineArtifactError(
                f"{artifact}: finding {result_path}[{index}] filename does not match its result path"
            )

    verified = raw_finding.get("is_verified")
    if verified is not None and not isinstance(verified, bool):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid is_verified flag"
        )

    return FindingIdentity(result_path, finding_type, hashed_secret, line_number)


def extract_findings(document: object, *, artifact: str) -> set[FindingIdentity]:
    """Validate a detect-secrets document and return deduplicated identities."""

    if not isinstance(document, dict):
        raise BaselineArtifactError(
            f"{artifact}: top-level JSON value must be an object"
        )

    version = document.get("version")
    if not isinstance(version, str) or not version.strip():
        raise BaselineArtifactError(f"{artifact}: version must be a non-empty string")

    raw_results = document.get("results")
    if not isinstance(raw_results, dict):
        raise BaselineArtifactError(f"{artifact}: results must be an object")

    findings: set[FindingIdentity] = set()
    for raw_path, raw_findings in raw_results.items():
        result_path = _canonical_result_path(raw_path, artifact=artifact)
        if not isinstance(raw_findings, list):
            raise BaselineArtifactError(
                f"{artifact}: results for {result_path} must be a list"
            )
        for index, raw_finding in enumerate(raw_findings):
            findings.add(
                _parse_finding(
                    result_path,
                    raw_finding,
                    artifact=artifact,
                    index=index,
                )
            )
    return findings


def validate_baseline_triage(document: object) -> None:
    """Require an explicit false-positive decision for every baseline entry.

    A baseline entry is an allowlist record, not proof that a detector hit was
    reviewed.  ``detect-secrets audit`` records that decision in ``is_secret``;
    keeping the field explicit prevents an unknown finding from silently
    becoming a long-lived suppression.  A committed baseline may contain only
    findings confirmed to be non-secrets.  Real credentials must be removed or
    rotated instead of being labelled as acceptable repository content.
    """

    if not isinstance(document, dict):
        raise BaselineArtifactError("baseline: top-level JSON value must be an object")
    raw_results = document.get("results")
    if not isinstance(raw_results, dict):
        raise BaselineArtifactError("baseline: results must be an object")
    for raw_path, raw_findings in raw_results.items():
        result_path = _canonical_result_path(raw_path, artifact="baseline")
        if not isinstance(raw_findings, list):
            raise BaselineArtifactError(
                f"baseline: findings for {result_path} must be a list"
            )
        for index, raw_finding in enumerate(raw_findings):
            if not isinstance(raw_finding, dict):
                raise BaselineArtifactError(
                    f"baseline: finding {result_path}[{index}] must be an object"
                )
            decision = raw_finding.get("is_secret")
            if decision is not False:
                raise BaselineArtifactError(
                    f"baseline: finding {result_path}[{index}] requires explicit "
                    "is_secret=false triage"
                )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def validate_false_positive_dispositions(
    document: object, *, today: date | None = None
) -> set[FindingIdentity]:
    """Validate exact dispositions without claiming their source is trusted.

    Callers must select immutable trusted-base data by default. Candidate data
    is valid only after the explicit owner-authored update gate succeeds. The
    closed schema accepts reviewed identities with finite expiry metadata.
    """

    artifact = "false-positive dispositions"
    if (
        not isinstance(document, dict)
        or set(document) != _FALSE_POSITIVE_DOCUMENT_FIELDS
    ):
        raise BaselineArtifactError(f"{artifact}: document schema is invalid")
    version = document.get("schema_version")
    if type(version) is not int or version != 1:
        raise BaselineArtifactError(f"{artifact}: schema version is invalid")
    records = document.get("records")
    if not isinstance(records, list) or len(records) > _FALSE_POSITIVE_RECORD_LIMIT:
        raise BaselineArtifactError(f"{artifact}: record list is invalid")

    current_date = today or date.today()
    findings: set[FindingIdentity] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != _FALSE_POSITIVE_RECORD_FIELDS:
            raise BaselineArtifactError(f"{artifact}: record schema is invalid")
        identity = record.get("identity")
        if (
            not isinstance(identity, dict)
            or set(identity) != _FALSE_POSITIVE_IDENTITY_FIELDS
        ):
            raise BaselineArtifactError(f"{artifact}: identity schema is invalid")

        raw_path = identity.get("path")
        if (
            not isinstance(raw_path, str)
            or any(marker in raw_path for marker in _DISPOSITION_WILDCARDS)
            or any(
                ord(character) < 32 or ord(character) == 127 for character in raw_path
            )
        ):
            raise BaselineArtifactError(f"{artifact}: identity path is invalid")
        path = _canonical_result_path(raw_path, artifact=artifact)
        if path != raw_path:
            raise BaselineArtifactError(f"{artifact}: identity path is not canonical")

        finding_type = identity.get("type")
        raw_digest_bytes = identity.get("hashed_secret_bytes")
        if (
            not isinstance(finding_type, str)
            or not finding_type
            or not isinstance(raw_digest_bytes, list)
            or len(raw_digest_bytes) != 20
            or any(
                type(byte) is not int or not 0 <= byte <= 255
                for byte in raw_digest_bytes
            )
        ):
            raise BaselineArtifactError(f"{artifact}: identity is not supported")
        hashed_secret = bytes(raw_digest_bytes).hex()

        category = record.get("category")
        if not isinstance(category, str) or category not in _FALSE_POSITIVE_CATEGORIES:
            raise BaselineArtifactError(f"{artifact}: category is invalid")
        if category in _FALSE_POSITIVE_HEX_CATEGORIES:
            category_matches = finding_type == _FALSE_POSITIVE_ALLOWED_TYPE
            if category == "independent_contract_fingerprint":
                category_matches = category_matches and path == (
                    _INDEPENDENT_CONTRACT_FINGERPRINT_PATH
                )
        else:
            allowed_pairs = _FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES.get(
                category, frozenset()
            )
            category_matches = (path, finding_type) in allowed_pairs
        if not category_matches:
            raise BaselineArtifactError(
                f"{artifact}: category does not allow this path and detector type"
            )
        evidence = record.get("evidence")
        if (
            not isinstance(evidence, str)
            or not evidence.strip()
            or evidence != evidence.strip()
            or len(evidence) > _FALSE_POSITIVE_EVIDENCE_LIMIT
            or any(
                ord(character) < 32 or ord(character) == 127 for character in evidence
            )
        ):
            raise BaselineArtifactError(f"{artifact}: evidence is invalid")
        required_evidence = _FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS.get(category, ())
        if any(
            marker.casefold() not in evidence.casefold() for marker in required_evidence
        ):
            raise BaselineArtifactError(
                f"{artifact}: evidence does not resolve the category scope"
            )

        owner = record.get("owner")
        if (
            not isinstance(owner, str)
            or not owner.strip()
            or owner != owner.strip()
            or len(owner) > _FALSE_POSITIVE_OWNER_LIMIT
            or owner.casefold() in _FALSE_POSITIVE_PLACEHOLDER_OWNERS
            or any(ord(character) < 32 or ord(character) == 127 for character in owner)
        ):
            raise BaselineArtifactError(f"{artifact}: owner metadata is invalid")
        if record.get("approval_status") != "approved":
            raise BaselineArtifactError(f"{artifact}: record is not approved")

        raw_reviewed = record.get("reviewed_on")
        raw_expires = record.get("expires_on")
        if not isinstance(raw_reviewed, str) or not isinstance(raw_expires, str):
            raise BaselineArtifactError(f"{artifact}: date metadata is invalid")
        try:
            reviewed_on = date.fromisoformat(raw_reviewed)
            expires_on = date.fromisoformat(raw_expires)
        except ValueError as error:
            raise BaselineArtifactError(
                f"{artifact}: date metadata is invalid"
            ) from error
        if (
            reviewed_on.isoformat() != raw_reviewed
            or expires_on.isoformat() != raw_expires
            or reviewed_on > current_date
            or expires_on < current_date
            or expires_on <= reviewed_on
            or expires_on - reviewed_on > timedelta(days=90)
        ):
            raise BaselineArtifactError(f"{artifact}: date range is invalid")

        finding = FindingIdentity(path, finding_type, hashed_secret, 1)
        if finding in findings:
            raise BaselineArtifactError(f"{artifact}: duplicate identity")
        findings.add(finding)
    return findings


def load_trusted_base_false_positive_dispositions(
    trusted_base_sha: str,
    *,
    repository_root: str | Path,
    today: date | None = None,
) -> set[FindingIdentity]:
    """Load the optional disposition artifact exclusively from a trusted tree."""

    if (
        not isinstance(trusted_base_sha, str)
        or _SOURCE_SHA_PATTERN.fullmatch(trusted_base_sha) is None
        or trusted_base_sha == "0" * 40
    ):
        raise BaselineArtifactError("trusted source base SHA is invalid")
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise BaselineArtifactError("repository root is unavailable") from error

    git_executable = shutil.which("git")
    if git_executable is None:
        raise BaselineArtifactError("trusted disposition lookup could not run")
    try:
        git_executable = str(Path(git_executable).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise BaselineArtifactError(
            "trusted disposition lookup could not run"
        ) from error

    def run_git(*arguments: str) -> bytes:
        try:
            # The only variable arguments are the validated commit SHA and a
            # fixed repository-relative artifact path; shell parsing is off.
            result = subprocess.run(  # noqa: S603
                [git_executable, *arguments],
                cwd=root,
                capture_output=True,
                check=False,
                shell=False,
            )
        except (OSError, UnicodeError) as error:
            raise BaselineArtifactError(
                "trusted disposition lookup could not run"
            ) from error
        if result.returncode != 0:
            raise BaselineArtifactError("trusted disposition lookup failed")
        return result.stdout

    try:
        run_git("cat-file", "-e", f"{trusted_base_sha}^{{commit}}")
        tree_entries = (
            run_git(
                "ls-tree",
                "-r",
                "--full-tree",
                trusted_base_sha,
                "--",
                _FALSE_POSITIVE_POLICY_PATH,
            )
            .decode("utf-8")
            .splitlines()
        )
    except UnicodeError as error:
        raise BaselineArtifactError("trusted disposition tree is invalid") from error

    if not tree_entries:
        return set()
    if len(tree_entries) != 1 or "\t" not in tree_entries[0]:
        raise BaselineArtifactError("trusted disposition tree entry is invalid")
    metadata, path = tree_entries[0].rsplit("\t", 1)
    fields = metadata.split()
    if (
        path != _FALSE_POSITIVE_POLICY_PATH
        or len(fields) != 3
        or fields[:2] != ["100644", "blob"]
    ):
        raise BaselineArtifactError("trusted disposition tree entry is invalid")

    try:
        raw_document = run_git(
            "show", f"{trusted_base_sha}:{_FALSE_POSITIVE_POLICY_PATH}"
        )
        if len(raw_document) > 512 * 1024:
            raise BaselineArtifactError(
                "false-positive disposition artifact is too large"
            )
        document = json.loads(
            raw_document.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, BaselineArtifactError):
            raise
        raise BaselineArtifactError(
            "false-positive disposition artifact is invalid"
        ) from error
    return validate_false_positive_dispositions(document, today=today)


def load_owner_authored_candidate_false_positive_dispositions(
    *, repository_root: str | Path, today: date | None = None
) -> set[FindingIdentity]:
    """Load the candidate policy after the trusted workflow owner gate passes."""

    try:
        root = Path(repository_root).resolve(strict=True)
        policy_path = root.joinpath(*_FALSE_POSITIVE_POLICY_PATH.split("/"))
        resolved_policy_path = policy_path.resolve(strict=True)
        if (
            resolved_policy_path != policy_path
            or not resolved_policy_path.is_file()
            or resolved_policy_path.stat().st_size > 512 * 1024
        ):
            raise BaselineArtifactError("candidate disposition artifact is unavailable")
        raw_document = resolved_policy_path.read_bytes()
        document = json.loads(
            raw_document.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except BaselineArtifactError:
        raise
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        raise BaselineArtifactError(
            "candidate disposition artifact is invalid"
        ) from error
    return validate_false_positive_dispositions(document, today=today)


def _describe_findings(findings: set[FindingIdentity]) -> str:
    """Render bounded, deterministic diagnostics without secret material."""

    ordered = sorted(findings, key=FindingIdentity.sort_key)
    preview = ", ".join(finding.display() for finding in ordered[:20])
    if len(ordered) > 20:
        preview += f", ... (+{len(ordered) - 20} more)"
    return preview


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a detect-secrets baseline against a fresh scan."
    )
    parser.add_argument("baseline_path", help="committed detect-secrets baseline")
    parser.add_argument("current_scan_path", help="fresh detect-secrets scan")
    parser.add_argument(
        "--trusted-base-baseline",
        "--base-baseline",
        dest="trusted_base_baseline",
        help="trusted target-branch baseline used to detect new PR suppressions",
    )
    parser.add_argument(
        "--trusted-base-source-sha",
        help="immutable trusted source commit used to detect new inline suppressions",
    )
    parser.add_argument(
        "--trusted-disposition-source-sha",
        help="trusted commit whose false-positive disposition artifact is loaded",
    )
    parser.add_argument(
        "--owner-authored-disposition-update",
        action="store_true",
        help="use candidate dispositions only after the trusted owner-policy gate passes",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify baseline findings and return a shell-friendly status code."""

    try:
        arguments = _build_parser().parse_args(argv)
    except SystemExit as error:
        # Keep the function convenient for tests while retaining argparse's
        # normal CLI help/usage output and exit status.
        return int(error.code) if isinstance(error.code, int) else 2

    try:
        baseline_document = load_json(arguments.baseline_path)
        validate_baseline_triage(baseline_document)
        baseline_findings = extract_findings(baseline_document, artifact="baseline")
        current_findings = extract_findings(
            load_json(arguments.current_scan_path), artifact="current scan"
        )
        trusted_findings: set[FindingIdentity] | None = None
        if arguments.trusted_base_baseline is not None:
            trusted_findings = extract_findings(
                load_json(arguments.trusted_base_baseline), artifact="trusted base"
            )
    except BaselineArtifactError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    source_pragma_findings: list[tuple[str, int]] = []
    if arguments.trusted_base_source_sha is not None:
        try:
            source_pragma_findings = find_new_inline_secret_pragmas(
                arguments.trusted_base_source_sha,
                repository_root=Path(__file__).resolve().parents[1],
            )
        except SourceDeltaError:
            print(
                "ERROR: trusted source delta could not be verified.",
                file=sys.stderr,
            )
            return 2
    if (
        arguments.owner_authored_disposition_update
        and arguments.trusted_base_source_sha is None
    ):
        print(
            "ERROR: owner-authored disposition mode requires a trusted source base.",
            file=sys.stderr,
        )
        return 2
    if (
        arguments.trusted_disposition_source_sha is not None
        and arguments.trusted_base_source_sha is None
    ):
        print(
            "ERROR: trusted dispositions require a trusted source base.",
            file=sys.stderr,
        )
        return 2

    trusted_dispositions: set[FindingIdentity] = set()
    disposition_source_sha = (
        arguments.trusted_disposition_source_sha or arguments.trusted_base_source_sha
    )
    if disposition_source_sha is not None:
        try:
            if arguments.owner_authored_disposition_update:
                trusted_dispositions = (
                    load_owner_authored_candidate_false_positive_dispositions(
                        repository_root=Path(__file__).resolve().parents[1]
                    )
                )
            else:
                trusted_dispositions = load_trusted_base_false_positive_dispositions(
                    disposition_source_sha,
                    repository_root=Path(__file__).resolve().parents[1],
                )
        except BaselineArtifactError:
            print(
                "ERROR: trusted false-positive dispositions could not be verified.",
                file=sys.stderr,
            )
            return 2

    new_findings = current_findings - baseline_findings - trusted_dispositions
    stale_suppressions = baseline_findings - current_findings
    # Only a newly added baseline entry that actually suppresses a finding in
    # this scan changes security semantics.  New stale entries remain harmless
    # and retain the existing removal/refactoring behaviour.
    new_trusted_suppressions: set[FindingIdentity] = set()
    if trusted_findings is not None:
        new_trusted_suppressions = (
            baseline_findings - trusted_findings
        ) & current_findings

    if stale_suppressions:
        print(
            "INFO: .secrets.baseline contains "
            f"{len(stale_suppressions)} stale finding(s) "
            "(removed files or secrets are allowed)."
        )

    matched_dispositions = current_findings & trusted_dispositions
    if matched_dispositions:
        print(
            "INFO: trusted base reviewed "
            f"{len(matched_dispositions)} exact false-positive finding(s)."
        )

    if new_findings:
        print(
            "ERROR: current scan contains "
            f"{len(new_findings)} new finding(s) not present in the "
            "committed baseline: "
            f"{_describe_findings(new_findings)}",
            file=sys.stderr,
        )

    if new_trusted_suppressions:
        print(
            "ERROR: baseline introduces "
            f"{len(new_trusted_suppressions)} finding-level suppression(s) relative "
            "to the trusted base baseline: "
            f"{_describe_findings(new_trusted_suppressions)}",
            file=sys.stderr,
        )

    if source_pragma_findings:
        print(
            "ERROR: source delta adds "
            f"{len(source_pragma_findings)} inline secret-allowlist pragma line(s).",
            file=sys.stderr,
        )

    if new_findings or new_trusted_suppressions or source_pragma_findings:
        return 1

    baseline_paths = {finding.path for finding in baseline_findings}
    print(
        "OK: .secrets.baseline integrity check passed "
        f"({len(baseline_paths)} suppressed file(s), "
        f"{len(baseline_findings)} finding(s) verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
