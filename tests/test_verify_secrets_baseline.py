"""Focused contract tests for strict detect-secrets baseline verification."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

_VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "verify_secrets_baseline.py"
)
_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "aud495_v4_verify_secrets_baseline", _VALIDATOR_PATH
)
if _VALIDATOR_SPEC is None or _VALIDATOR_SPEC.loader is None:
    raise ImportError(f"cannot load v4 validator from {_VALIDATOR_PATH}")
verifier = importlib.util.module_from_spec(_VALIDATOR_SPEC)
sys.modules[_VALIDATOR_SPEC.name] = verifier
_VALIDATOR_SPEC.loader.exec_module(verifier)

Finding = tuple[str, str, str, int]
_FINDING_TYPE = "Secret" + " Keyword"
_HASHED_FIELD = "hash" + "ed_" + "se" + "cret"


def _document(*findings: Finding) -> dict[str, Any]:
    results: dict[str, list[dict[str, Any]]] = {}
    for path, finding_type, digest, line_number in findings:
        results.setdefault(path, []).append(
            {
                "type": finding_type,
                "filename": path,
                _HASHED_FIELD: digest,
                "is_verified": False,
                "is_secret": False,
                "line_number": line_number,
            }
        )
    return {"version": "1.5.0", "results": results}


def _write(path: Path, document: Any) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _verify(
    tmp_path: Path,
    baseline: Any,
    current: Any,
    *,
    trusted_base: Any | None = None,
    trusted_base_name: str = "trusted-baseline.json",
) -> int:
    baseline_path = _write(tmp_path / "baseline.json", baseline)
    current_path = _write(tmp_path / "current.json", current)
    argv = [str(baseline_path), str(current_path)]
    if trusted_base is not None:
        trusted_path = _write(tmp_path / trusted_base_name, trusted_base)
        argv.extend(["--trusted-base-baseline", str(trusted_path)])
    return verifier.main(argv)


def _inline_pragma_marker() -> str:
    return "pragma:" + " allowlist" + " secret"


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        pytest.fail("Git executable is required for source-delta tests")
    return str(Path(executable).resolve(strict=True))


def _git_fixture(repository: Path, *arguments: str) -> str:
    git_executable = _git_executable()
    # The temporary repository and fixture command are test-controlled; no shell.
    result = subprocess.run(  # noqa: S603
        [git_executable, "-C", str(repository), *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        text=True,
        shell=False,
    )
    assert result.returncode == 0, "temporary Git fixture command failed"
    return result.stdout.strip()


def _commit_git_fixture(repository: Path, message: str) -> str:
    _git_fixture(repository, "add", "--all")
    git_executable = _git_executable()
    # The temporary repository and fixture command are test-controlled; no shell.
    result = subprocess.run(  # noqa: S603
        [
            git_executable,
            "-C",
            str(repository),
            "-c",
            "user.name=Policy Fixture",
            "-c",
            "user.email=policy-fixture@example.invalid",
            "-c",
            f"core.hooksPath={repository / '.disabled-hooks'}",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            message,
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        text=True,
        shell=False,
    )
    assert result.returncode == 0, "temporary Git fixture commit failed"
    return _git_fixture(repository, "rev-parse", "HEAD")


def _new_git_fixture(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "source repository"
    repository.mkdir()
    (repository / ".disabled-hooks").mkdir()
    empty_template = repository / ".empty-template"
    empty_template.mkdir()
    _git_fixture(
        repository,
        "init",
        "--quiet",
        f"--template={empty_template}",
    )
    _git_fixture(repository, "config", "core.quotePath", "true")
    (repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    return repository, _commit_git_fixture(repository, "trusted base")


def _reviewed_disposition(
    *,
    path: str = "src/known.py",
    finding_type: str = "Hex High Entropy String",
    digest: str = "a" * 40,
    category: str = "documented_crypto_test_vector",
) -> dict[str, Any]:
    return {
        "identity": {
            "path": path,
            "type": finding_type,
            "hashed_secret_bytes": list(bytes.fromhex(digest)),
        },
        "category": category,
        "evidence": "Published test vector documented in docs/security/test-vectors.md",
        "owner": "Security Maintainers",
        "reviewed_on": "2026-10-12",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    }


def _disposition_document(*records: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "records": list(records)}


def _reviewed_exact_disposition(
    path: str,
    finding_type: str,
    digest_bytes: tuple[int, ...],
    category: str,
) -> dict[str, Any]:
    record = _reviewed_disposition(
        path=path,
        finding_type=finding_type,
        digest=bytes(digest_bytes).hex(),
        category=category,
    )
    if category == "external_kubernetes_secret_reference":
        record["evidence"] = (
            "Kubernetes external Secret object name or key reference; "
            "not credential material."
        )
    return record


def _commit_dispositions(repository: Path, records: list[dict[str, Any]]) -> str:
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(_disposition_document(*records)), encoding="utf-8"
    )
    return _commit_git_fixture(repository, "add reviewed test dispositions")


def test_source_delta_rejects_added_marker_in_quoted_path(tmp_path: Path) -> None:
    repository, base_sha = _new_git_fixture(tmp_path)
    relative_path = Path("folder with spaces") / "marker-é-quoted.py"
    added_path = repository / relative_path
    added_path.parent.mkdir()
    added_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    _commit_git_fixture(repository, "add marker")

    findings = verifier.find_new_inline_secret_pragmas(
        base_sha, repository_root=repository
    )

    assert findings == [(relative_path.as_posix(), 1)]


def test_source_delta_parses_forced_text_binary_hunk_with_unicode_separators(
    tmp_path: Path,
) -> None:
    repository, base_sha = _new_git_fixture(tmp_path)
    binary_path = repository / "opaque.bin"
    payload = ("prefix\u0085middle\u2028# " + _inline_pragma_marker() + "\n").encode(
        "utf-8"
    )
    binary_path.write_bytes(b"\x00" + payload)
    _commit_git_fixture(repository, "add forced-text binary marker")

    assert verifier.find_new_inline_secret_pragmas(
        base_sha, repository_root=repository
    ) == [("opaque.bin", 1)]


def test_source_delta_rejects_a_moved_legacy_marker(tmp_path: Path) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    old_path = repository / "legacy.py"
    old_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    base_sha = _commit_git_fixture(repository, "add legacy marker")
    moved_path = repository / "renamed folder" / "moved-é-marker.py"
    moved_path.parent.mkdir()
    old_path.rename(moved_path)
    _commit_git_fixture(repository, "move legacy marker")

    findings = verifier.find_new_inline_secret_pragmas(
        base_sha, repository_root=repository
    )

    assert findings == [("renamed folder/moved-é-marker.py", 1)]


def test_source_delta_allows_unchanged_and_removed_legacy_markers(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    legacy_path = repository / "legacy.py"
    legacy_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    base_sha = _commit_git_fixture(repository, "add existing marker")

    (repository / "unrelated.py").write_text("value = 1\n", encoding="utf-8")
    _commit_git_fixture(repository, "change unrelated source")
    assert (
        verifier.find_new_inline_secret_pragmas(base_sha, repository_root=repository)
        == []
    )

    legacy_path.write_text("value = 'synthetic'\n", encoding="utf-8")
    _commit_git_fixture(repository, "remove existing marker")
    assert (
        verifier.find_new_inline_secret_pragmas(base_sha, repository_root=repository)
        == []
    )


def test_source_delta_fails_closed_when_git_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: None)

    with pytest.raises(
        verifier.SourceDeltaError, match="Git source comparison could not run"
    ):
        verifier.find_new_inline_secret_pragmas("1" * 40, repository_root=repository)


def test_source_delta_fails_closed_on_malformed_git_diff() -> None:
    malformed_diff = (
        "@@ malformed header\n+value = 'synthetic' # " + _inline_pragma_marker()
    )

    with pytest.raises(verifier.SourceDeltaError):
        verifier._find_added_inline_secret_pragmas(malformed_diff)


def test_source_delta_rejects_invalid_or_unavailable_base(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    for base_sha in ("0" * 40, "not-a-commit", "f" * 40):
        with pytest.raises(verifier.SourceDeltaError):
            verifier.find_new_inline_secret_pragmas(
                base_sha, repository_root=repository
            )


def test_source_delta_does_not_surface_git_error_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    def failed_git(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=128,
            stdout="",
            stderr="synthetic private diagnostic",
        )

    monkeypatch.setattr(verifier.subprocess, "run", failed_git)
    with pytest.raises(verifier.SourceDeltaError) as error:
        verifier.find_new_inline_secret_pragmas("1" * 40, repository_root=repository)

    assert "synthetic private diagnostic" not in str(error.value)


def test_source_delta_diagnostic_reports_count_without_untrusted_paths(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        verifier,
        "load_trusted_base_false_positive_dispositions",
        lambda *_args, **_kwargs: set(),
    )
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document())
    sensitive_path = "synthetic-private-secret-derived-path.py"
    monkeypatch.setattr(
        verifier,
        "find_new_inline_secret_pragmas",
        lambda *_args, **_kwargs: [(sensitive_path, 91)],
    )

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            "1" * 40,
        ]
    )

    diagnostic = capsys.readouterr().err
    assert result == 1
    assert "1 inline secret-allowlist pragma line(s)" in diagnostic
    assert sensitive_path not in diagnostic
    assert ":91" not in diagnostic


def test_security_workflow_passes_source_base_for_supported_events() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (
        repository_root / ".github" / "workflows" / "reusable-security-audit.yml"
    ).read_text(encoding="utf-8")

    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "PUSH_BEFORE_SHA: ${{ github.event.before }}" in workflow
    assert workflow.count('--trusted-base-source-sha "$SOURCE_BASE_SHA"') == 2
    assert 'pull_request) SOURCE_BASE_SHA="$PR_BASE_SHA" ;;' in workflow
    assert 'push) SOURCE_BASE_SHA="$PUSH_BEFORE_SHA" ;;' in workflow
    assert "unsupported event for trusted source comparison" in workflow


def test_matching_findings_allow_stale_removals(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    stale = ("docs/removed.md", "Secret Keyword", "digest-stale", 4)

    result = _verify(tmp_path, _document(finding, stale), _document(finding))

    assert result == 0
    output = capsys.readouterr().out
    assert "stale" in output.lower()
    assert "integrity check passed" in output


def test_new_finding_in_existing_file_is_rejected(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_detected = ("src/a.py", "Secret Keyword", "digest-b", 11)

    result = _verify(tmp_path, _document(existing), _document(existing, newly_detected))

    assert result == 1
    error = capsys.readouterr().err.lower()
    assert "new finding" in error
    assert "digest-b" not in error


def test_line_number_drift_does_not_create_a_new_finding(tmp_path: Path) -> None:
    baseline_finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    current_finding = ("src/a.py", "Secret Keyword", "digest-a", 27)

    assert (
        _verify(tmp_path, _document(baseline_finding), _document(current_finding)) == 0
    )


def test_trusted_base_rejects_new_baseline_suppression(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_suppressed = ("src/a.py", "Secret Keyword", "digest-b", 11)

    result = _verify(
        tmp_path,
        _document(existing, newly_suppressed),
        _document(existing, newly_suppressed),
        trusted_base=_document(existing),
    )

    assert result == 1
    error = capsys.readouterr().err
    assert "trusted base" in error.lower()
    assert "src/a.py:11" in error
    assert "Secret Keyword" in error
    assert "digest-b" not in error


def test_trusted_base_stale_addition_preserves_removal_semantics(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    stale = ("docs/removed.md", "Secret Keyword", "digest-stale", 4)

    result = _verify(
        tmp_path,
        _document(existing, stale),
        _document(existing),
        trusted_base=_document(existing),
    )

    assert result == 0
    assert "stale" in capsys.readouterr().out.lower()


def test_empty_current_results_are_valid_and_mark_baseline_stale(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)

    result = _verify(tmp_path, _document(finding), _document())

    assert result == 0
    assert "stale" in capsys.readouterr().out.lower()


def test_path_separators_are_compared_canonically(tmp_path: Path) -> None:
    baseline = _document(("src\\a.py", "Secret Keyword", "digest-a", 10))
    current = _document(("src/a.py", "Secret Keyword", "digest-a", 10))

    assert _verify(tmp_path, baseline, current) == 0


@pytest.mark.parametrize(
    "malformed",
    [
        [],
        {"results": []},
        {"results": {"src/a.py": {}}},
        {"results": {"src/a.py": [{"type": _FINDING_TYPE}]}},
        {"results": {"src/a.py": [{"type": _FINDING_TYPE, _HASHED_FIELD: "digest-a"}]}},
        {
            "results": {
                "../outside.txt": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "/etc/passwd": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "\\\\server\\share\\secret.txt": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "src/a.py": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 0,
                    }
                ]
            }
        },
        {
            "version": "1.5.0",
            "results": {
                "src/a.py": [
                    {
                        "filename": "src/other.py",
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            },
        },
        {
            "version": "1.5.0",
            "results": {
                "src/a.py": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                        "is_verified": "false",
                    }
                ]
            },
        },
    ],
)
def test_malformed_artifacts_fail_closed(malformed: Any, tmp_path: Path) -> None:
    valid = _document(("src/a.py", "Secret Keyword", "digest-a", 10))

    assert _verify(tmp_path, malformed, valid) == 2


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    baseline_path = _write(
        tmp_path / "baseline.json",
        _document(("src/a.py", "Secret Keyword", "digest-a", 10)),
    )

    assert verifier.main([str(baseline_path), str(tmp_path / "missing.json")]) == 2


def test_baseline_requires_explicit_false_positive_triage(
    tmp_path: Path,
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline = _document(finding)
    baseline["results"]["src/a.py"][0].pop("is_secret")
    current = _document(finding)
    assert _verify(tmp_path, baseline, current) == 2


def test_baseline_rejects_a_committed_secret_decision(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline = _document(finding)
    baseline["results"]["src/a.py"][0]["is_secret"] = True
    assert _verify(tmp_path, baseline, _document(finding)) == 2


def test_invalid_json_fails_closed(tmp_path: Path) -> None:
    baseline_path = _write(
        tmp_path / "baseline.json",
        _document(("src/a.py", "Secret Keyword", "digest-a", 10)),
    )
    current_path = tmp_path / "current.json"
    current_path.write_text("not json", encoding="utf-8")

    assert verifier.main([str(baseline_path), str(current_path)]) == 2


def test_malformed_trusted_base_fails_closed(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)

    assert (
        _verify(
            tmp_path,
            _document(finding),
            _document(finding),
            trusted_base={"results": []},
        )
        == 2
    )


def test_cli_usage_error_is_fail_closed(capsys: pytest.CaptureFixture[str]) -> None:
    assert verifier.main([]) == 2
    assert "usage:" in capsys.readouterr().err.lower()


def test_empty_trusted_base_path_fails_closed(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline_path = _write(tmp_path / "baseline.json", _document(finding))
    current_path = _write(tmp_path / "current.json", _document(finding))

    assert (
        verifier.main(
            [
                str(baseline_path),
                str(current_path),
                "--trusted-base-baseline",
                "",
            ]
        )
        == 2
    )


def test_base_baseline_alias_is_supported(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_suppressed = ("src/a.py", "Secret Keyword", "digest-b", 11)
    baseline_path = _write(
        tmp_path / "baseline.json", _document(existing, newly_suppressed)
    )
    current_path = _write(
        tmp_path / "current.json", _document(existing, newly_suppressed)
    )
    trusted_path = _write(tmp_path / "trusted.json", _document(existing))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--base-baseline",
            str(trusted_path),
        ]
    )

    assert result == 1
    assert "trusted base" in capsys.readouterr().err.lower()


def test_reviewed_false_positive_disposition_matches_exact_identity() -> None:
    identity = verifier.FindingIdentity(
        "src/known.py", "Hex High Entropy String", "a" * 40, 1
    )

    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(_reviewed_disposition()),
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {identity}


def test_exact_new_identity_allowlists_remain_finite_and_path_scoped() -> None:
    assert len(verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES) == 31
    assert len(verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES) == 27
    assert {
        path for path, _, _ in verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES
    } == {"tests/fixtures/full-backend-reusable-baseline.v4.yaml"}
    assert {
        path for path, _, _ in verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
    } == {
        "charts/redis-compat/values.yaml",
        "charts/revocation-store/values.yaml",
        "charts/university-ecosystem/values-staging.yaml",
        "tests/test_docker_startup_contracts.py",
        "tests/test_helm_staging_contract.py",
        "tests/test_mfa_helm_contract.py",
        "tests/test_revocation_store_security_contract.py",
        "security/trivy-university-values.yaml",
    }


def test_source_contract_identifier_category_is_finite_and_evidence_bound() -> None:
    category = "source_contract_identifier"
    assert len(verifier._C6_CODE_FRAGMENT_IDENTITIES) == 9
    assert len(verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES) == 17
    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    paths = {path for path, _, _ in verifier._C6_CODE_FRAGMENT_IDENTITIES}
    assert paths == {
        "services/file-processor/internal/config/secret_files_test.go",
        "services/file-processor/internal/config/secret_open_portable.go",
        "services/file-processor/internal/config/secret_open_unix.go",
        "services/gateway/internal/config/secret_files_test.go",
        "services/gateway/internal/config/secret_open_portable.go",
        "services/gateway/internal/config/secret_open_unix.go",
        "services/ws-hub/pkg/config/secret_files_test.go",
        "services/ws-hub/pkg/config/secret_open_portable.go",
        "services/ws-hub/pkg/config/secret_open_unix.go",
    }

    for path, finding_type, digest_bytes in sorted(
        verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES
    ):
        record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
        record["evidence"] = evidence
        assert verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 16),
        ) == {
            verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
        }


def test_page_title_route_identifier_candidates_are_exact_and_finite() -> None:
    category = "source_contract_identifier"
    expected = {
        (
            "frontend/src/components/ui/PageRouteSEO.tsx",
            "Secret Keyword",
            (
                246,
                11,
                35,
                176,
                57,
                187,
                96,
                181,
                93,
                29,
                195,
                205,
                161,
                83,
                22,
                254,
                236,
                136,
                40,
                118,
            ),
        ),
        (
            "frontend/src/components/ui/PageRouteSEO.tsx",
            "Secret Keyword",
            (
                13,
                39,
                13,
                74,
                47,
                213,
                87,
                245,
                102,
                242,
                14,
                180,
                169,
                34,
                53,
                125,
                169,
                142,
                149,
                34,
            ),
        ),
    }
    assert verifier._PAGE_TITLE_ROUTE_IDENTIFIER_IDENTITIES == expected
    assert expected <= verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES

    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    for path, finding_type, digest_bytes in expected:
        approved = _reviewed_exact_disposition(
            path, finding_type, digest_bytes, category
        )
        approved["evidence"] = evidence
        approved["reviewed_on"] = "2026-10-23"
        approved["expires_on"] = "2027-01-10"
        pending = {**approved, "approval_status": "pending"}
        with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
            verifier.validate_false_positive_dispositions(
                _disposition_document(pending),
                today=verifier.date(2026, 10, 23),
            )

        identity = approved["identity"]
        assert verifier.validate_false_positive_dispositions(
            _disposition_document(approved),
            today=verifier.date(2026, 10, 23),
        ) == {
            verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
        }

        changed_records = (
            {**approved, "identity": {**identity, "path": path + ".changed"}},
            {
                **approved,
                "identity": {**identity, "type": "Basic Auth Credentials"},
            },
            {
                **approved,
                "identity": {
                    **identity,
                    "hashed_secret_bytes": [
                        (digest_bytes[0] + 1) % 256,
                        *digest_bytes[1:],
                    ],
                },
            },
            {**approved, "category": "auth_validation_ui_copy"},
            {**approved, "expires_on": "2027-01-11"},
        )
        for changed in changed_records:
            with pytest.raises(verifier.BaselineArtifactError):
                verifier.validate_false_positive_dispositions(
                    _disposition_document(changed),
                    today=verifier.date(2026, 10, 23),
                )


def test_c6_source_contract_records_require_explicit_approval() -> None:
    repository = Path(__file__).resolve().parents[1]
    assert Path(verifier.__file__).resolve() == (
        repository / "scripts/verify_secrets_baseline.py"
    )
    policy = json.loads(
        (repository / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    records = [
        record
        for record in policy["records"]
        if record["category"] == "source_contract_identifier"
        and record["reviewed_on"] == "2026-10-16"
    ]
    identities = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in records
    }
    assert len(records) == 9
    assert identities == verifier._C6_CODE_FRAGMENT_IDENTITIES

    for record in records:
        assert record["owner"] == "egorribun"
        assert record["expires_on"] == "2027-01-10"
        assert "function-symbol hook" in record["evidence"]
        pending = {**record, "approval_status": "pending"}
        with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
            verifier.validate_false_positive_dispositions(
                _disposition_document(pending),
                today=verifier.date(2026, 10, 16),
            )
        approved = {**record, "approval_status": "approved"}
        identity = approved["identity"]
        assert verifier.validate_false_positive_dispositions(
            _disposition_document(approved),
            today=verifier.date(2026, 10, 16),
        ) == {
            verifier.FindingIdentity(
                identity["path"],
                identity["type"],
                bytes(identity["hashed_secret_bytes"]).hex(),
                1,
            )
        }


def test_c6_source_contract_records_reject_mutated_identity_or_category() -> None:
    category = "source_contract_identifier"
    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    for path, finding_type, digest_bytes in sorted(
        verifier._C6_CODE_FRAGMENT_IDENTITIES
    ):
        record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
        record["evidence"] = evidence
        changes = (
            {"identity": {**record["identity"], "path": path + ".changed"}},
            {"identity": {**record["identity"], "type": "Basic Auth Credentials"}},
            {
                "identity": {
                    **record["identity"],
                    "hashed_secret_bytes": [
                        (digest_bytes[0] + 1) % 256,
                        *digest_bytes[1:],
                    ],
                }
            },
            {"category": "public_code_fragment"},
            {"category": "ci_test_contract_sentinel"},
        )
        for change in changes:
            changed = {**record, **change}
            with pytest.raises(verifier.BaselineArtifactError):
                verifier.validate_false_positive_dispositions(
                    _disposition_document(changed),
                    today=verifier.date(2026, 10, 16),
                )


@pytest.mark.parametrize(
    ("path", "finding_type", "digest_bytes"),
    sorted(verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES),
)
def test_v4_independent_contract_fingerprints_match_exact_identities(
    path: str, finding_type: str, digest_bytes: tuple[int, ...]
) -> None:
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "independent_contract_fingerprint",
    )

    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 15),
    )

    assert dispositions == {
        verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
    }


@pytest.mark.parametrize(
    ("path", "finding_type", "digest_bytes"),
    sorted(verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES),
)
def test_external_kubernetes_secret_references_match_exact_identities(
    path: str, finding_type: str, digest_bytes: tuple[int, ...]
) -> None:
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "external_kubernetes_secret_reference",
    )

    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 15),
    )

    assert dispositions == {
        verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
    }


def test_trivy_university_secret_reference_is_exact_and_requires_approval() -> None:
    path = "security/trivy-university-values.yaml"
    finding_type = "Secret Keyword"
    digest_bytes = bytes(
        (
            227,
            206,
            244,
            201,
            253,
            191,
            204,
            143,
            195,
            74,
            35,
            39,
            210,
            43,
            64,
            145,
            65,
            224,
            73,
            206,
        )
    )
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        tuple(digest_bytes),
        "external_kubernetes_secret_reference",
    )
    record["reviewed_on"] = "2026-10-16"
    expected = verifier.FindingIdentity(path, finding_type, digest_bytes.hex(), 1)

    assert verifier.validate_false_positive_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 16),
    ) == {expected}

    record["approval_status"] = "pending"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 16),
        )


@pytest.mark.parametrize(
    ("category", "identity"),
    [
        ("independent_contract_fingerprint", identity)
        for identity in sorted(verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES)
    ]
    + [
        ("external_kubernetes_secret_reference", identity)
        for identity in sorted(
            verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
        )
    ],
)
def test_new_exact_disposition_categories_reject_mutated_identities(
    category: str,
    identity: tuple[str, str, tuple[int, ...]],
) -> None:
    path, finding_type, digest_bytes = identity
    mutations = (
        (path + ".changed", finding_type, digest_bytes),
        (
            path,
            "Secret Keyword"
            if finding_type == "Hex High Entropy String"
            else "Basic Auth Credentials",
            digest_bytes,
        ),
        (
            path,
            finding_type,
            ((digest_bytes[0] + 1) % 256, *digest_bytes[1:]),
        ),
    )

    for changed_path, changed_type, changed_digest in mutations:
        record = _reviewed_exact_disposition(
            changed_path,
            changed_type,
            changed_digest,
            category,
        )
        with pytest.raises(verifier.BaselineArtifactError):
            verifier.validate_false_positive_dispositions(
                _disposition_document(record),
                today=verifier.date(2026, 10, 15),
            )


def test_mfa_helm_secret_reference_is_exact_and_requires_approval() -> None:
    path = "tests/test_mfa_helm_contract.py"
    finding_type = "Secret Keyword"
    digest_bytes = bytes(
        (
            123,
            77,
            125,
            47,
            161,
            133,
            114,
            12,
            211,
            156,
            161,
            83,
            218,
            176,
            239,
            161,
            33,
            63,
            175,
            3,
        )
    )
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        tuple(digest_bytes),
        "external_kubernetes_secret_reference",
    )
    record["reviewed_on"] = "2026-10-16"
    record["evidence"] = (
        "Kubernetes external Secret object name or key reference; not credential material. "
        "The referenced value is a public synthetic object name in an MFA Helm contract test."
    )
    expected = verifier.FindingIdentity(path, finding_type, digest_bytes.hex(), 1)

    assert verifier.validate_false_positive_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 16),
    ) == {expected}

    record["approval_status"] = "pending"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 16),
        )


def test_external_secret_reference_requires_semantic_evidence_markers() -> None:
    path, finding_type, digest_bytes = sorted(
        verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
    )[0]
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "external_kubernetes_secret_reference",
    )
    record["evidence"] = "Exact detector identity was reviewed."

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 15),
        )


def test_external_secret_reference_still_requires_unexpired_review() -> None:
    path, finding_type, digest_bytes = sorted(
        verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
    )[0]
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "external_kubernetes_secret_reference",
    )
    record["expires_on"] = "2026-10-14"

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 15),
        )


def test_independent_contract_fingerprint_category_remains_exact() -> None:
    record = _reviewed_disposition(
        path="tests/fixtures/full-backend-reusable-baseline.v3.yaml",
        category="independent_contract_fingerprint",
    )

    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {
        verifier.FindingIdentity(
            "tests/fixtures/full-backend-reusable-baseline.v3.yaml",
            "Hex High Entropy String",
            "a" * 40,
            1,
        )
    }


@pytest.mark.parametrize(
    ("category", "path", "finding_type"),
    [
        (
            "ci_test_contract_sentinel",
            ".github/workflows/ci.yml",
            "Basic Auth Credentials",
        ),
        (
            "ci_test_contract_sentinel",
            ".github/workflows/ci.yml",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            ".github/workflows/nightly-full-gate.yml",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            "frontend/scripts/frontend-quality-contract.test.mjs",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            "frontend/src/api/hooks/__tests__/campusConfig.test.ts",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            "tests/test_live_stand_resource_guard.py",
            "Base64 High Entropy String",
        ),
        (
            "ci_test_contract_sentinel",
            "tests/test_start_docker_orphan_ownership.py",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/stryker-inventory.test.mjs",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/generate-activity-pdf-font.py",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/src/assets/fonts/inter-latin-cyrillic-400.provenance.json",
            "Base64 High Entropy String",
        ),
        (
            "public_totp_algorithm_alphabet",
            "frontend/tests/e2e-live/totp-recovery.live.spec.ts",
            "Base64 High Entropy String",
        ),
        (
            "documented_dummy_password_hash",
            "app/auth/security.py",
            "Secret Keyword",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_seed_admin_data.py",
            "Secret Keyword",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_seed_demo_account_preservation.py",
            "Secret Keyword",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_seed_demo_messenger.py",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "services/gateway/internal/handlers/handlers_identity_closure_test.go",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "services/ws-hub/pkg/hub/replay_security_adversarial_test.go",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "tests/integration/test_historical_attendance_sender_migrations_postgres.py",
            "Secret Keyword",
        ),
        (
            "synthetic_fakeredis_lease_token",
            "tests/test_chat_command_failure_paths.py",
            "Secret Keyword",
        ),
        (
            "domain_resource_contract_fixture",
            "tests/test_live_stand_resource_guard.py",
            "Secret Keyword",
        ),
        (
            "internal_demo_stand_account_fixture",
            "frontend/tests/e2e-live/fixtures.ts",
            "Secret Keyword",
        ),
    ],
)
def test_non_hex_dispositions_are_scoped_to_reviewed_path_and_type(
    category: str, path: str, finding_type: str
) -> None:
    record = _reviewed_disposition(
        path=path,
        finding_type=finding_type,
        digest="c" * 40,
        category=category,
    )
    if category == "internal_demo_stand_account_fixture":
        record["evidence"] = (
            "Owner decision at docs/superpowers/plans/MVP_MASTER_PLAN.md:37 "
            "states internal-demo accounts are synthetic; external operational "
            "status remains unverified."
        )

    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {verifier.FindingIdentity(path, finding_type, "c" * 40, 1)}


@pytest.mark.parametrize(
    ("category", "path", "finding_type"),
    [
        (
            "ci_test_contract_sentinel",
            "tests/test_auth_review_regressions.py",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            ".github/workflows/ci.yml",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/stryker-inventory.test.mjs",
            "Secret Keyword",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/generate-activity-pdf-font.py",
            "Secret Keyword",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/src/assets/fonts/inter-latin-cyrillic-400.provenance.json",
            "Hex High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/src/assets/fonts/unreviewed.provenance.json",
            "Base64 High Entropy String",
        ),
        (
            "public_totp_algorithm_alphabet",
            "frontend/tests/e2e-live/totp-recovery.live.spec.ts",
            "Basic Auth Credentials",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_auth_review_regressions.py",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "app/auth/security.py",
            "Secret Keyword",
        ),
        (
            "synthetic_fakeredis_lease_token",
            "tests/test_auth_review_regressions.py",
            "Secret Keyword",
        ),
        (
            "synthetic_fakeredis_lease_token",
            "tests/test_chat_command_failure_paths.py",
            "Base64 High Entropy String",
        ),
        (
            "domain_resource_contract_fixture",
            "tests/test_live_stand_resource_guard.py",
            "Base64 High Entropy String",
        ),
        (
            "internal_demo_stand_account_fixture",
            "frontend/tests/e2e-live/fixtures.ts",
            "Base64 High Entropy String",
        ),
    ],
)
def test_non_hex_dispositions_reject_wrong_source_or_type(
    category: str, path: str, finding_type: str
) -> None:
    record = _reviewed_disposition(
        path=path,
        finding_type=finding_type,
        category=category,
    )

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 12),
        )


@pytest.mark.parametrize(
    "evidence",
    [
        "Internal demo fixture, external operational status remains unverified.",
        "Owner decision at docs/superpowers/plans/MVP_MASTER_PLAN.md:37.",
    ],
)
def test_internal_demo_account_requires_both_owner_evidence_markers(
    evidence: str,
) -> None:
    record = _reviewed_disposition(
        path="frontend/tests/e2e-live/fixtures.ts",
        finding_type="Secret Keyword",
        category="internal_demo_stand_account_fixture",
    )
    record["evidence"] = evidence

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 12),
        )


def test_internal_demo_account_category_does_not_approve_pending_record() -> None:
    record = _reviewed_disposition(
        path="frontend/tests/e2e-live/fixtures.ts",
        finding_type="Secret Keyword",
        category="internal_demo_stand_account_fixture",
    )
    record["approval_status"] = "pending"
    record["evidence"] = (
        "Owner decision at docs/superpowers/plans/MVP_MASTER_PLAN.md:37 "
        "states internal-demo accounts are synthetic; external operational "
        "status remains unverified."
    )

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 12),
        )


@pytest.mark.parametrize(
    ("candidate_path", "candidate_type", "candidate_digest"),
    [
        ("src/other.py", "Hex High Entropy String", "a" * 40),
        ("src/known.py", "Hex High Entropy String", "b" * 40),
    ],
)
def test_reviewed_disposition_does_not_match_other_path_or_digest(
    candidate_path: str, candidate_type: str, candidate_digest: str
) -> None:
    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(_reviewed_disposition()),
        today=verifier.date(2026, 10, 12),
    )

    assert (
        verifier.FindingIdentity(candidate_path, candidate_type, candidate_digest, 1)
        not in dispositions
    )


def test_reviewed_disposition_rejects_unapproved_finding_type() -> None:
    record = _reviewed_disposition(finding_type="AWS Access Key")

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


@pytest.mark.parametrize(
    "change",
    [
        lambda record: record.update(category="unreviewed_category"),
        lambda record: record.update(approval_status="pending"),
        lambda record: record.update(expires_on="2026-10-11"),
        lambda record: record.update(reviewed_on="2026-10-13"),
        lambda record: record.update(expires_on="2027-01-11"),
        lambda record: record.pop("owner"),
        lambda record: record.pop("evidence"),
        lambda record: record.pop("reviewed_on"),
    ],
    ids=(
        "unknown-category",
        "pending",
        "expired",
        "future-review",
        "expiry-over-90-days",
        "missing-owner",
        "missing-evidence",
        "missing-review-date",
    ),
)
def test_reviewed_disposition_requires_approved_owner_and_finite_dates(
    change: Any,
) -> None:
    record = _reviewed_disposition()
    change(record)

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


@pytest.mark.parametrize(
    "invalid_path",
    ["src/*.py", "../src/known.py", "src//known.py", "src\\known.py"],
)
def test_reviewed_disposition_rejects_non_exact_paths(invalid_path: str) -> None:
    record = _reviewed_disposition(path=invalid_path)

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


def test_reviewed_disposition_rejects_duplicate_identities() -> None:
    record = _reviewed_disposition()

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record, _reviewed_disposition()),
            today=verifier.date(2026, 10, 12),
        )


def test_reviewed_disposition_rejects_unknown_fields_and_bad_digest() -> None:
    record = _reviewed_disposition()
    record["identity"]["unreviewed"] = False

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


@pytest.mark.parametrize(
    "invalid_bytes",
    [[0] * 19, [0] * 19 + [-1], [0] * 19 + [256], [0] * 19 + [True]],
)
def test_reviewed_disposition_rejects_malformed_digest_bytes(
    invalid_bytes: list[int],
) -> None:
    record = _reviewed_disposition()
    record["identity"]["hashed_secret_bytes"] = invalid_bytes

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


def test_reviewed_disposition_does_not_cover_an_unrelated_finding() -> None:
    unrelated = verifier.FindingIdentity(
        "src/known.py", "Hex High Entropy String", "b" * 40, 7
    )
    dispositions = verifier.validate_false_positive_dispositions(
        _disposition_document(_reviewed_disposition()),
        today=verifier.date(2026, 10, 12),
    )

    assert unrelated not in dispositions


def test_trusted_disposition_loader_uses_base_tree_not_worktree(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    record = _reviewed_disposition()
    trusted_sha = _commit_dispositions(repository, [record])
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.write_text(
        json.dumps(_disposition_document({**record, "approval_status": "pending"})),
        encoding="utf-8",
    )

    dispositions = verifier.load_trusted_base_false_positive_dispositions(
        trusted_sha,
        repository_root=repository,
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {
        verifier.FindingIdentity("src/known.py", "Hex High Entropy String", "a" * 40, 1)
    }


def test_trusted_disposition_loader_ignores_candidate_only_artifact(
    tmp_path: Path,
) -> None:
    repository, trusted_sha = _new_git_fixture(tmp_path)
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(_disposition_document(_reviewed_disposition())), encoding="utf-8"
    )

    dispositions = verifier.load_trusted_base_false_positive_dispositions(
        trusted_sha,
        repository_root=repository,
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == set()


def test_trusted_disposition_loader_rejects_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        '{"schema_version":1,"schema_version":1,"records":[]}', encoding="utf-8"
    )
    trusted_sha = _commit_git_fixture(repository, "add malformed disposition file")

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_trusted_base_false_positive_dispositions(
            trusted_sha,
            repository_root=repository,
            today=verifier.date(2026, 10, 12),
        )


def test_main_uses_trusted_exact_dispositions(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )

    assert result == 0
    assert "1 exact false-positive finding(s)" in capsys.readouterr().out


def test_owner_authored_candidate_disposition_is_explicit_opt_in(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, trusted_sha = _new_git_fixture(tmp_path)
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(_disposition_document(_reviewed_disposition())), encoding="utf-8"
    )
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    without_owner_gate = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )
    with_owner_gate = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
            "--owner-authored-disposition-update",
        ]
    )

    assert without_owner_gate == 1
    assert with_owner_gate == 0
    assert "new finding" in capsys.readouterr().err


def test_candidate_disposition_tamper_expiry_fails_closed(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    expired = _reviewed_disposition()
    expired["expires_on"] = "2026-10-11"
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(_disposition_document(expired)), encoding="utf-8")

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository,
            today=verifier.date(2026, 10, 12),
        )


def test_push_can_use_accepted_head_policy_while_source_diff_uses_before_sha(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, before_sha = _new_git_fixture(tmp_path)
    current_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            before_sha,
            "--trusted-disposition-source-sha",
            current_sha,
        ]
    )

    assert result == 0
    assert "exact false-positive" in capsys.readouterr().out


def test_trusted_disposition_does_not_allow_new_baseline_suppression(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document(finding))
    current_path = _write(tmp_path / "current.json", _document(finding))
    trusted_path = _write(tmp_path / "trusted.json", _document())

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-baseline",
            str(trusted_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )

    assert result == 1
    assert "trusted base" in capsys.readouterr().err.lower()


def test_trusted_disposition_does_not_allow_added_inline_pragma(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    marker_path = repository / "new_source.py"
    marker_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    _commit_git_fixture(repository, "add inline marker")
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )

    assert result == 1
    assert "inline secret-allowlist pragma" in capsys.readouterr().err


def test_disposition_file_is_protected_by_existing_owner_policy_gates() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    protected_path = "quality/security-false-positive-dispositions.json"
    workflow_paths = (
        ".github/workflows/codeql.yml",
        ".github/workflows/checkov.yml",
        ".github/workflows/dependency-review.yml",
        ".github/workflows/gitleaks.yml",
        ".github/workflows/reusable-security-audit.yml",
        ".github/workflows/zizmor.yml",
    )

    for relative_path in workflow_paths:
        workflow = (repository_root / relative_path).read_text(encoding="utf-8")
        assert f'"{protected_path}"' in workflow
        assert 'if [[ "$PR_AUTHOR" != "egorribun" ]]' in workflow

    policy_integrity = (
        repository_root / ".github" / "workflows" / "security-policy-integrity.yml"
    ).read_text(encoding="utf-8")
    assert "quality/*" in policy_integrity
    assert 'if [[ "$PR_AUTHOR" != "egorribun" ]]' in policy_integrity

    security_audit = (
        repository_root / ".github" / "workflows" / "reusable-security-audit.yml"
    ).read_text(encoding="utf-8")
    assert '"$PR_AUTHOR" == "egorribun"' in security_audit
    assert (
        'if [[ "$EVENT_NAME" == "pull_request" && "$PR_AUTHOR" == "egorribun" ]]'
        in security_audit
    )
    assert (
        'git diff --quiet "$SOURCE_BASE_SHA" -- '
        "quality/security-false-positive-dispositions.json" in security_audit
    )
    assert "--owner-authored-disposition-update" in security_audit
    assert '--trusted-disposition-source-sha "$HEAD_SHA"' in security_audit


def _public_compose_sentinel_record() -> dict[str, Any]:
    record = _reviewed_exact_disposition(
        "tests/test_live_nats_transport.py",
        "Secret Keyword",
        (
            *(74, 70, 48, 200, 151, 59, 103, 95, 251, 150),
            *(7, 200, 234, 230, 69, 166, 253, 9, 215, 53),
        ),
        "public_compose_inspection_test_sentinel",
    )
    record["reviewed_on"] = "2026-10-20"
    record["evidence"] = (
        "Public Compose inspection test sentinel "
        "live-stand-inspection-placeholder in LIVE_VAPID_PRIVATE_KEY; "
        "no-I/O request expectation; not credential material."
    )
    return record


@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 10, 20), verifier.date(2027, 1, 10)],
)
def test_public_compose_sentinel_matches_only_approved_identity(
    today: verifier.date,
) -> None:
    record = _public_compose_sentinel_record()
    identity = record["identity"]

    assert verifier.validate_false_positive_dispositions(
        _disposition_document(record), today=today
    ) == {
        verifier.FindingIdentity(
            identity["path"],
            identity["type"],
            bytes(identity["hashed_secret_bytes"]).hex(),
            1,
        )
    }


@pytest.mark.parametrize(
    "change",
    [
        "path",
        "type",
        "value",
        "category",
        "evidence",
        "approval",
        "extended-expiry",
    ],
)
def test_public_compose_sentinel_refuses_scope_mutation(change: str) -> None:
    record = _public_compose_sentinel_record()
    if change == "path":
        record["identity"]["path"] = "tests/other.py"
    elif change == "type":
        record["identity"]["type"] = "Basic Auth Credentials"
    elif change == "value":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif change == "category":
        record["category"] = "ci_test_contract_sentinel"
    elif change == "evidence":
        record["evidence"] = "Reviewed public fixture."
    elif change == "approval":
        record["approval_status"] = "pending"
    else:
        record["expires_on"] = "2027-01-11"

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 20),
        )


def test_public_compose_sentinel_expires_after_approved_date() -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(_public_compose_sentinel_record()),
            today=verifier.date(2027, 1, 11),
        )


@pytest.mark.parametrize(
    "marker",
    [
        "public Compose inspection test sentinel",
        "live-stand-inspection-placeholder",
        "LIVE_VAPID_PRIVATE_KEY",
        "no-I/O request expectation",
        "not credential material",
    ],
)
def test_public_compose_sentinel_requires_each_semantic_marker(marker: str) -> None:
    record = _public_compose_sentinel_record()
    evidence = record["evidence"]
    start = evidence.casefold().index(marker.casefold())
    record["evidence"] = evidence[:start] + evidence[start + len(marker) :]

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 20),
        )


def test_public_compose_sentinel_identity_matches_fixed_source_literal() -> None:
    record = _public_compose_sentinel_record()
    source_path = Path(__file__).resolve().parents[1] / record["identity"]["path"]
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    values = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and key.value == "LIVE_VAPID_PRIVATE_KEY"
    ]
    assert len(values) == 1
    value = values[0]
    assert isinstance(value, ast.Constant)
    assert value.value == "live-stand-inspection-placeholder"
    digest = hashlib.sha1(value.value.encode("utf-8"), usedforsecurity=False).digest()
    assert digest == bytes(record["identity"]["hashed_secret_bytes"])


def test_approved_go_image_disposition_binds_exact_source_checksum() -> None:
    root = Path(__file__).resolve().parents[1]
    path = "tests/test_docker_startup_contracts.py"
    expected_digest = bytes(
        (
            246,
            29,
            95,
            9,
            239,
            28,
            164,
            164,
            87,
            181,
            67,
            85,
            104,
            249,
            102,
            110,
            149,
            79,
            94,
            167,
        )
    )
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    records = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == path
        and record["identity"]["type"] == "Hex High Entropy String"
        and bytes(record["identity"]["hashed_secret_bytes"]) == expected_digest
    ]
    assert len(records) == 1
    record = records[0]
    assert record["category"] == "public_integrity_digest"
    assert record["owner"] == "egorribun"
    assert record["reviewed_on"] == "2026-10-21"
    assert record["expires_on"] == "2027-01-10"
    assert record["approval_status"] == "approved"

    source = ast.parse((root / path).read_text(encoding="utf-8"))
    prefix = "golang:1.26.10-alpine3.24@sha256:"
    values = {
        node.value.removeprefix(prefix)
        for node in ast.walk(source)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(prefix)
        and len(node.value) == len(prefix) + 64
    }
    assert len(values) == 1
    value = values.pop()
    actual_digest = hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest()
    assert actual_digest == expected_digest
    assert verifier.validate_false_positive_dispositions(
        _disposition_document(record), today=verifier.date(2026, 10, 21)
    ) == {
        verifier.FindingIdentity(
            path,
            "Hex High Entropy String",
            expected_digest.hex(),
            1,
        )
    }


def test_approved_benchmark_helper_pins_bind_ten_exact_public_identities() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = (
        "scripts/quality/benchmark_capture_activation.py",
        "tests/test_benchmark_capture_activation_workflow.py",
    )
    expected_digests = {
        bytes(
            (
                *(189, 150, 35, 69, 216, 63, 138, 226, 98, 138),
                *(68, 74, 85, 25, 150, 191, 96, 188, 12, 244),
            )
        ),
        bytes(
            (
                *(221, 15, 186, 27, 178, 116, 134, 111, 122, 164),
                *(212, 230, 250, 42, 89, 161, 192, 23, 163, 47),
            )
        ),
        bytes(
            (
                *(100, 220, 73, 83, 214, 135, 25, 219, 155, 67),
                *(136, 52, 53, 47, 201, 166, 188, 247, 162, 64),
            )
        ),
        bytes(
            (
                *(170, 211, 241, 2, 217, 140, 162, 48, 192, 237),
                *(158, 191, 80, 65, 79, 179, 86, 161, 66, 112),
            )
        ),
        bytes(
            (
                *(96, 116, 161, 36, 68, 56, 120, 27, 21, 234),
                *(138, 37, 0, 104, 147, 166, 166, 83, 205, 184),
            )
        ),
    }
    assert len(expected_digests) == 5
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(policy["records"]) == 329
    records = [
        record
        for record in policy["records"]
        if record["identity"]["path"] in paths and record["reviewed_on"] == "2026-10-21"
    ]
    expected = {
        (path, "Hex High Entropy String", digest)
        for path in paths
        for digest in expected_digests
    }
    assert len(records) == 10
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            bytes(record["identity"]["hashed_secret_bytes"]),
        )
        for record in records
    } == expected

    for record in records:
        assert record["category"] == "public_integrity_digest"
        assert record["owner"] == "egorribun"
        assert record["reviewed_on"] == "2026-10-21"
        assert record["expires_on"] == "2027-01-10"
        assert record["approval_status"] == "approved"

    for path in paths:
        source = ast.parse((root / path).read_text(encoding="utf-8"))
        actual = {
            hashlib.sha1(node.value.encode("utf-8"), usedforsecurity=False).digest()
            for node in ast.walk(source)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert expected_digests <= actual, path

    assert verifier.validate_false_positive_dispositions(
        {"schema_version": 1, "records": records},
        today=verifier.date(2026, 10, 21),
    ) == {
        verifier.FindingIdentity(path, finding_type, digest.hex(), 1)
        for path, finding_type, digest in expected
    }


def _achievement_url_fixture_record() -> dict[str, Any]:
    record = _reviewed_exact_disposition(
        "frontend/src/components/profile/__tests__/profileUtils.closure.test.ts",
        "Basic Auth Credentials",
        (
            *(157, 78, 30, 35, 189, 91, 114, 112, 70, 169),
            *(227, 180, 183, 219, 87, 189, 141, 110, 230, 132),
        ),
        "synthetic_achievement_url_test_fixture",
    )
    record["owner"] = "egorribun"
    record["reviewed_on"] = "2026-10-22"
    record["evidence"] = (
        "Synthetic profile achievement URL test fixture on reserved example.test host; "
        "embedded-auth rejection coverage; not credential material. "
        "Owner approved this exact path, detector type and digest on 2026-10-22; "
        "no network request or operational login is performed."
    )
    return record


@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 10, 22), verifier.date(2027, 1, 10)],
)
def test_achievement_url_fixture_is_one_exact_approved_identity(
    today: verifier.date,
) -> None:
    record = _achievement_url_fixture_record()
    identity = record["identity"]
    expected = (
        identity["path"],
        identity["type"],
        tuple(identity["hashed_secret_bytes"]),
    )
    assert verifier._SYNTHETIC_ACHIEVEMENT_URL_TEST_FIXTURE_IDENTITIES == {expected}
    assert verifier.validate_false_positive_dispositions(
        _disposition_document(record), today=today
    ) == {
        verifier.FindingIdentity(
            identity["path"],
            identity["type"],
            bytes(identity["hashed_secret_bytes"]).hex(),
            1,
        )
    }


@pytest.mark.parametrize(
    "change",
    ["path", "type", "value", "evidence", "approval", "missing-approval", "expiry"],
)
def test_achievement_url_fixture_refuses_scope_mutation(change: str) -> None:
    record = _achievement_url_fixture_record()
    if change == "path":
        record["identity"]["path"] = "frontend/src/other.test.ts"
    elif change == "type":
        record["identity"]["type"] = "Secret Keyword"
    elif change == "value":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif change == "evidence":
        record["evidence"] = "Reviewed fixture."
    elif change == "approval":
        record["approval_status"] = "pending"
    elif change == "missing-approval":
        del record["approval_status"]
    else:
        record["expires_on"] = "2027-01-11"

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 22)
        )


@pytest.mark.parametrize(
    "category",
    sorted(
        verifier._FALSE_POSITIVE_CATEGORIES - {"synthetic_achievement_url_test_fixture"}
    ),
)
def test_achievement_url_fixture_cannot_be_reclassified(category: str) -> None:
    record = _achievement_url_fixture_record()
    record["category"] = category
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 22)
        )


@pytest.mark.parametrize(
    "marker",
    [
        "synthetic profile achievement URL test fixture",
        "reserved example.test host",
        "embedded-auth rejection coverage",
        "not credential material",
    ],
)
def test_achievement_url_fixture_requires_each_semantic_marker(marker: str) -> None:
    record = _achievement_url_fixture_record()
    evidence = record["evidence"]
    start = evidence.casefold().index(marker.casefold())
    record["evidence"] = evidence[:start] + evidence[start + len(marker) :]
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 22)
        )


def test_achievement_url_fixture_expires_after_owner_approved_date() -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(_achievement_url_fixture_record()),
            today=verifier.date(2027, 1, 11),
        )


def test_achievement_url_fixture_binds_the_actual_source_and_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _achievement_url_fixture_record()
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    matching = [
        entry
        for entry in policy["records"]
        if entry["category"] == "synthetic_achievement_url_test_fixture"
    ]
    assert matching == [record]

    source = (root / record["identity"]["path"]).read_text(encoding="utf-8")
    urls = [
        urlsplit(json.loads(line.strip().removesuffix(",")))
        for line in source.splitlines()
        if line.strip().startswith('"https://') and "@" in line
    ]
    credentialed = [url for url in urls if url.password is not None]
    assert len(credentialed) == 1
    parsed = credentialed[0]
    assert parsed.scheme == "https"
    assert parsed.hostname == "example.test"
    assert parsed.path == "/award"
    assert parsed.username == "user"
    assert parsed.password is not None
    digest = hashlib.sha1(
        parsed.password.encode("utf-8"), usedforsecurity=False
    ).digest()
    assert digest == bytes(record["identity"]["hashed_secret_bytes"])


_AUTH_VALIDATION_UI_COPY_PATH = "frontend/src/i18n/locales/en/auth.json"
_AUTH_VALIDATION_UI_COPY_CATEGORY = "auth_validation_ui_copy"
_AUTH_VALIDATION_UI_COPY_DIGEST_BYTES = (
    bytes(
        (
            62,
            125,
            86,
            169,
            88,
            4,
            255,
            60,
            50,
            43,
            151,
            167,
            231,
            205,
            186,
            37,
            220,
            146,
            9,
            87,
        )
    ),
    bytes(
        (
            81,
            214,
            154,
            230,
            4,
            109,
            42,
            59,
            226,
            69,
            68,
            157,
            91,
            56,
            22,
            93,
            93,
            120,
            222,
            245,
        )
    ),
    bytes(
        (
            214,
            156,
            59,
            26,
            197,
            75,
            231,
            218,
            54,
            102,
            217,
            147,
            123,
            156,
            120,
            231,
            195,
            9,
            214,
            232,
        )
    ),
)


def _auth_validation_candidate_policy() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    policy["records"] = policy["records"][:315]
    return policy


def test_auth_validation_ui_copy_accepts_only_three_exact_identities() -> None:
    policy = _auth_validation_candidate_policy()
    records = [
        record
        for record in policy["records"]
        if record["category"] == _AUTH_VALIDATION_UI_COPY_CATEGORY
    ]
    assert len(records) == 3
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            bytes(record["identity"]["hashed_secret_bytes"]).hex(),
        )
        for record in records
    } == {
        (_AUTH_VALIDATION_UI_COPY_PATH, "Secret Keyword", digest.hex())
        for digest in _AUTH_VALIDATION_UI_COPY_DIGEST_BYTES
    }
    assert verifier.validate_false_positive_dispositions(
        policy, today=verifier.date(2026, 10, 23)
    ) >= {
        verifier.FindingIdentity(
            _AUTH_VALIDATION_UI_COPY_PATH, "Secret Keyword", digest.hex(), 1
        )
        for digest in _AUTH_VALIDATION_UI_COPY_DIGEST_BYTES
    }


def test_auth_validation_ui_copy_rejects_identity_or_category_transfer() -> None:
    original = _auth_validation_candidate_policy()
    invalid_mutations = (
        lambda record: record["identity"].update(
            path="frontend/src/i18n/locales/en/auth-copy.json"
        ),
        lambda record: record["identity"].update(type="Basic Auth Credentials"),
        lambda record: record["identity"]["hashed_secret_bytes"].__setitem__(
            0, (record["identity"]["hashed_secret_bytes"][0] + 1) % 256
        ),
        lambda record: record.update(category="source_contract_identifier"),
        lambda record: record.update(expires_on="2027-01-11"),
        lambda record: record.update(
            evidence="English auth validation UI copy; not credential material."
        ),
    )
    for mutate in invalid_mutations:
        policy = copy.deepcopy(original)
        record = next(
            row
            for row in policy["records"]
            if row["category"] == _AUTH_VALIDATION_UI_COPY_CATEGORY
        )
        mutate(record)
        with pytest.raises(verifier.BaselineArtifactError):
            verifier.validate_false_positive_dispositions(
                policy, today=verifier.date(2026, 10, 23)
            )


def test_auth_validation_ui_copy_expires_at_the_finite_cap() -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _auth_validation_candidate_policy(), today=verifier.date(2027, 1, 11)
        )


def test_auth_validation_ui_copy_preserves_existing_298_records() -> None:
    policy = _auth_validation_candidate_policy()
    records = policy["records"]
    proposed = [
        record
        for record in records
        if record["category"] == _AUTH_VALIDATION_UI_COPY_CATEGORY
    ]
    existing = [
        record
        for record in records
        if record["category"] != _AUTH_VALIDATION_UI_COPY_CATEGORY
    ]
    assert len(records) == 315
    assert len(existing) == 312
    assert records[:298] == existing[:298]
    assert records[298:301] == proposed
    assert records[301:] == existing[298:]
    assert len(proposed) == 3


_AUD253_DISPOSITION_CATEGORY = "aud253_private_env_mode_test_fixture"
_AUD253_DISPOSITION_EXPIRY = "2027-01-10"
_TRIVY_DISPOSITION_PATH = "scripts/quality/validate_trivy_kyverno_fixture.py"
_TRIVY_DISPOSITION_EXPIRY = "2026-11-22"
_PRIOR_301_RECORDS_SHA256_BYTES = (
    96,
    123,
    56,
    7,
    89,
    203,
    93,
    254,
    158,
    177,
    160,
    18,
    255,
    82,
    60,
    102,
    196,
    38,
    90,
    151,
    51,
    197,
    65,
    95,
    160,
    54,
    204,
    127,
    55,
    154,
    8,
    140,
)
_AUTHORIZED_310_RECORDS_SHA256_BYTES = (
    108,
    60,
    61,
    59,
    80,
    160,
    171,
    13,
    95,
    7,
    68,
    56,
    156,
    213,
    52,
    179,
    6,
    82,
    27,
    22,
    85,
    54,
    49,
    37,
    152,
    32,
    214,
    120,
    166,
    81,
    86,
    43,
)


def _owner_review_candidate_policy() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    policy["records"] = policy["records"][:315]
    return policy


def _owner_review_record(
    policy: dict[str, Any], identity: tuple[str, str, tuple[int, ...]]
) -> dict[str, Any]:
    path, finding_type, digest_bytes = identity
    matches = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == path
        and record["identity"]["type"] == finding_type
        and tuple(record["identity"]["hashed_secret_bytes"]) == digest_bytes
    ]
    assert len(matches) == 1
    return matches[0]


def test_aud253_and_trivy_candidate_records_are_exact_and_finite() -> None:
    policy = _owner_review_candidate_policy()
    aud253 = [
        record
        for record in policy["records"]
        if record["category"] == _AUD253_DISPOSITION_CATEGORY
    ]
    trivy = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == _TRIVY_DISPOSITION_PATH
    ]
    assert len(policy["records"]) == 315
    assert len(aud253) == 5
    assert len(trivy) == 2
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in aud253
    } == verifier._AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in trivy
    } == verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
    for record in aud253:
        assert record["expires_on"] == _AUD253_DISPOSITION_EXPIRY
    for record in trivy:
        assert record["category"] == "public_integrity_digest"
        assert record["expires_on"] == _TRIVY_DISPOSITION_EXPIRY
    assert verifier.validate_false_positive_dispositions(
        policy, today=verifier.date(2026, 10, 23)
    )


def test_aud253_candidate_rejects_identity_category_evidence_and_expiry_changes() -> (
    None
):
    policy = _owner_review_candidate_policy()
    identity = next(iter(verifier._AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES))
    mutations = (
        lambda row: row["identity"].update(path="tests/other_fixture.py"),
        lambda row: row["identity"].update(type="Hex High Entropy String"),
        lambda row: row["identity"]["hashed_secret_bytes"].__setitem__(
            0, (row["identity"]["hashed_secret_bytes"][0] + 1) % 256
        ),
        lambda row: row.update(category="public_integrity_digest"),
        lambda row: row.update(expires_on="2027-01-11"),
        lambda row: row.update(
            evidence="synthetic test fixture; not credential material."
        ),
    )
    for mutate in mutations:
        candidate = copy.deepcopy(policy)
        mutate(_owner_review_record(candidate, identity))
        with pytest.raises(verifier.BaselineArtifactError):
            verifier.validate_false_positive_dispositions(
                candidate, today=verifier.date(2026, 10, 23)
            )


def test_trivy_candidate_stays_exact_in_public_integrity_category() -> None:
    policy = _owner_review_candidate_policy()
    identity = next(iter(verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES))
    mutations = (
        lambda row: row["identity"].update(path="scripts/quality/other_validator.py"),
        lambda row: row["identity"].update(type="Base64 High Entropy String"),
        lambda row: row["identity"]["hashed_secret_bytes"].__setitem__(
            0, (row["identity"]["hashed_secret_bytes"][0] + 1) % 256
        ),
        lambda row: row.update(category="documented_crypto_test_vector"),
        lambda row: row.update(expires_on="2026-11-23"),
        lambda row: row.update(
            evidence="Public integrity checksum; not credential material."
        ),
    )
    for mutate in mutations:
        candidate = copy.deepcopy(policy)
        mutate(_owner_review_record(candidate, identity))
        with pytest.raises(verifier.BaselineArtifactError):
            verifier.validate_false_positive_dispositions(
                candidate, today=verifier.date(2026, 10, 23)
            )


def test_aud253_fixture_digests_are_bound_to_embedded_powershell_literals() -> None:
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse(
        (root / "tests/test_aud253_private_env_files.py").read_text(encoding="utf-8")
    )
    values = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "POWERSHELL_HARNESS"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert len(values) == 1
    literal_pattern = re.compile("'((?:[^']|'')*)'|\"((?:[^\"`]|`.)*)\"")
    observed = set()
    for match in literal_pattern.finditer(values[0]):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        value = value.replace("''", "'")
        observed.add(
            hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest()
        )
    assert {
        bytes(identity[2])
        for identity in verifier._AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
    } <= observed


def test_trivy_checksum_digests_are_bound_to_validator_constants() -> None:
    root = Path(__file__).resolve().parents[1]
    source = ast.parse((root / _TRIVY_DISPOSITION_PATH).read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for node in ast.walk(source):
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if names & {"EXPECTED_FIXTURE_SHA256", "EXPECTED_IGNORE_POLICY_SHA256"}:
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            for name in names:
                if name in {"EXPECTED_FIXTURE_SHA256", "EXPECTED_IGNORE_POLICY_SHA256"}:
                    values[name] = value
    assert set(values) == {"EXPECTED_FIXTURE_SHA256", "EXPECTED_IGNORE_POLICY_SHA256"}
    actual = {
        hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest()
        for value in values.values()
    }
    assert actual == {
        bytes(identity[2])
        for identity in verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
    }


def test_owner_review_preserves_the_previous_301_records_byte_for_byte() -> None:
    policy = _owner_review_candidate_policy()
    prior = policy["records"][:301]
    encoded = json.dumps(
        prior, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded).digest() == bytes(_PRIOR_301_RECORDS_SHA256_BYTES)
    assert len(policy["records"]) == 315


def test_workflow_owner_review_candidate_records_are_exact_and_finite() -> None:
    policy = _owner_review_candidate_policy()
    records = policy["records"][310:]
    expected = [
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                143,
                120,
                48,
                192,
                43,
                11,
                20,
                246,
                31,
                253,
                204,
                224,
                203,
                218,
                179,
                79,
                187,
                212,
                10,
                41,
            ),
            "public_integrity_digest",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                85,
                158,
                8,
                17,
                13,
                217,
                219,
                104,
                145,
                111,
                194,
                19,
                60,
                251,
                92,
                240,
                212,
                85,
                113,
                116,
            ),
            "independent_contract_fingerprint",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                94,
                40,
                155,
                35,
                12,
                205,
                36,
                191,
                27,
                93,
                89,
                252,
                6,
                36,
                193,
                174,
                240,
                78,
                30,
                64,
            ),
            "independent_contract_fingerprint",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                228,
                251,
                163,
                207,
                40,
                164,
                144,
                11,
                26,
                225,
                79,
                240,
                197,
                199,
                12,
                121,
                37,
                113,
                215,
                216,
            ),
            "independent_contract_fingerprint",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                109,
                237,
                50,
                137,
                135,
                161,
                1,
                220,
                60,
                104,
                144,
                173,
                229,
                20,
                90,
                76,
                18,
                192,
                224,
                154,
            ),
            "independent_contract_fingerprint",
        ),
    ]
    actual = [
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
            record["category"],
        )
        for record in records
    ]
    assert actual == expected
    assert all(record["owner"] == "egorribun" for record in records)
    assert all(record["reviewed_on"] == "2026-10-23" for record in records)
    assert all(record["expires_on"] == "2027-01-10" for record in records)
    assert all(record["approval_status"] == "approved" for record in records)


def test_workflow_owner_review_candidate_preserves_authorized_310_prefix() -> None:
    policy = _owner_review_candidate_policy()
    prior = policy["records"][:310]
    encoded = json.dumps(
        prior, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded).digest() == bytes(
        _AUTHORIZED_310_RECORDS_SHA256_BYTES
    )
    assert len(policy["records"]) == 315


_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY = (
    "aud495_cache_key_redaction_test_fixture"
)
_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH = "tests/test_cache_object_keys_aud495.py"
_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES = {
    (
        _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH,
        "Secret Keyword",
        tuple(bytes.fromhex("9e601bae9cd4e3075d55858bed83ff4e4bfdff10")),
    ),
    (
        _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH,
        "Secret Keyword",
        tuple(bytes.fromhex("cee0221af84e16fa6180f0600ea14be1cd97c48f")),
    ),
}


def _assert_aud495_cache_canary_uses_runtime_secret(
    function: ast.AsyncFunctionDef,
) -> None:
    assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "secret_key"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    value = assignments[0].value
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Attribute)
    assert isinstance(value.func.value, ast.Name)
    assert value.func.value.id == "secrets"
    assert value.func.attr == "token_urlsafe"
    assert len(value.args) == 1
    assert isinstance(value.args[0], ast.Constant) and value.args[0].value == 32
    assert not value.keywords


def _aud495_cache_key_historical_fixture_identities() -> set[
    tuple[str, str, tuple[int, ...]]
]:
    path = _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH
    source_text = (Path(__file__).resolve().parents[1] / path).read_text(
        encoding="utf-8"
    )
    source = ast.parse(source_text)
    target_functions = {
        "test_backend_error_logs_do_not_emit_cache_key_or_exception_text",
        "test_invalid_payload_logs_redact_cache_key",
    }
    function_sources: dict[str, str] = {}
    for function in source.body:
        if (
            not isinstance(function, ast.AsyncFunctionDef)
            or function.name not in target_functions
        ):
            continue
        _assert_aud495_cache_canary_uses_runtime_secret(function)
        function_source = ast.get_source_segment(source_text, function)
        assert function_source is not None
        function_sources[function.name] = function_source
    assert set(function_sources) == target_functions
    assert all(
        "secret_key not in repr(call)" in function_source
        for function_source in function_sources.values()
    )
    assert (
        'call.kwargs.get("exc_info")'
        in function_sources[
            "test_backend_error_logs_do_not_emit_cache_key_or_exception_text"
        ]
    )
    assert (
        'keyed_fake.get.await_args.args[0] == (\n            f"aud495-key-derived-from-object:{secret_key}"\n        )'
        in function_sources[
            "test_backend_error_logs_do_not_emit_cache_key_or_exception_text"
        ]
    )
    assert len(_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES) == 2
    return set(_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES)


def test_aud495_cache_key_fixture_binds_historical_records_and_runtime_source() -> None:
    expected = _aud495_cache_key_historical_fixture_identities()
    assert verifier._AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES == expected
    assert (
        verifier._FALSE_POSITIVE_EXACT_CATEGORY_IDENTITIES[
            _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
        ]
        == expected
    )
    assert verifier._AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_DIGESTS == {
        identity[2] for identity in expected
    }


def test_aud495_cache_key_fixture_rejects_literal_secret_mutation() -> None:
    path = _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH
    source_text = (Path(__file__).resolve().parents[1] / path).read_text(
        encoding="utf-8"
    )
    source = ast.parse(source_text)
    function = next(
        node
        for node in source.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name
        == "test_backend_error_logs_do_not_emit_cache_key_or_exception_text"
    )
    assignment = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "secret_key"
            for target in node.targets
        )
    )
    assignment.value = ast.Constant(value="literal fixture")
    with pytest.raises(AssertionError):
        _assert_aud495_cache_canary_uses_runtime_secret(function)


def test_aud495_cache_key_fixture_candidate_is_exact_and_requires_owner_approval() -> (
    None
):
    category = _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
    identities = _aud495_cache_key_historical_fixture_identities()
    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    approved_records = []
    for path, finding_type, digest_bytes in sorted(identities):
        record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
        record["evidence"] = evidence
        record["reviewed_on"] = "2026-10-23"
        record["expires_on"] = "2027-01-10"
        approved_records.append(record)

    expected_findings = {
        verifier.FindingIdentity(path, finding_type, bytes(digest).hex(), 1)
        for path, finding_type, digest in identities
    }
    assert (
        verifier.validate_false_positive_dispositions(
            _disposition_document(*approved_records),
            today=verifier.date(2026, 10, 23),
        )
        == expected_findings
    )

    pending = copy.deepcopy(approved_records)
    pending[0]["approval_status"] = "pending_owner_review"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        verifier.validate_false_positive_dispositions(
            _disposition_document(*pending), today=verifier.date(2026, 10, 23)
        )

    for mutation in (
        lambda row: row["identity"].update(path="tests/other.py"),
        lambda row: row["identity"].update(type="Hex High Entropy String"),
        lambda row: row["identity"].update(
            hashed_secret_bytes=[
                (row["identity"]["hashed_secret_bytes"][0] + 1) % 256,
                *row["identity"]["hashed_secret_bytes"][1:],
            ]
        ),
        lambda row: row.update(category="source_contract_identifier"),
        lambda row: row.update(evidence="synthetic fixture; not credential material"),
        lambda row: row.update(expires_on="2027-01-11"),
    ):
        changed = copy.deepcopy(approved_records)
        mutation(changed[0])
        with pytest.raises(verifier.BaselineArtifactError):
            verifier.validate_false_positive_dispositions(
                _disposition_document(*changed), today=verifier.date(2026, 10, 23)
            )


_AUD495_IMMUTABLE_315_PREFIX_SHA256 = (
    "16330df8c10ee81bab39b51ab54917605d1e589b1d443f0c93862a179e69e653"
)
_AUD495_TEST_ONLY_OWNER_MARKER = "TEST_FIXTURE_ONLY"
_AUD495_TEST_ONLY_EVIDENCE_MARKER = "HYPOTHETICAL_TEST_FIXTURE_ONLY_NOT_OWNER_APPROVAL"


def test_aud495_318_policy_preserves_exact_315_prefix_and_finite_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    records = policy["records"]
    assert len(records) == 329
    prefix = records[:315]
    encoded_prefix = json.dumps(
        prefix, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).hexdigest() == (
        _AUD495_IMMUTABLE_315_PREFIX_SHA256
    )

    suffix = records[315:317]
    expected_identities = _aud495_cache_key_historical_fixture_identities()
    actual_identities = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in suffix
    }
    assert actual_identities == expected_identities
    assert all(
        record["category"] == _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
        for record in suffix
    )
    assert all(
        record["expires_on"] <= "2027-01-10" and record["approval_status"] == "approved"
        for record in suffix
    )

    test_only_rows = [
        record for record in suffix if record["owner"] == _AUD495_TEST_ONLY_OWNER_MARKER
    ]
    if test_only_rows:
        assert len(test_only_rows) == 2
        assert all(
            _AUD495_TEST_ONLY_EVIDENCE_MARKER in record["evidence"]
            for record in test_only_rows
        )

    digest_identity = _public_integrity_digest_source_identity()
    digest_record = records[317]
    assert (
        digest_record["identity"]["path"],
        digest_record["identity"]["type"],
        tuple(digest_record["identity"]["hashed_secret_bytes"]),
    ) == digest_identity
    assert digest_record["category"] == "public_integrity_digest"
    assert digest_record["expires_on"] <= "2027-01-10"
    assert digest_record["approval_status"] == "approved"

    expected_findings = {
        verifier.FindingIdentity(path, finding_type, bytes(digest).hex(), 1)
        for path, finding_type, digest in expected_identities
    }
    validated = verifier.validate_false_positive_dispositions(
        policy, today=verifier.date(2026, 10, 24)
    )
    assert expected_findings <= validated
    assert (
        verifier.FindingIdentity(
            digest_identity[0], digest_identity[1], bytes(digest_identity[2]).hex(), 1
        )
        in validated
    )

    pending = copy.deepcopy(policy)
    for record in pending["records"][315:]:
        record["approval_status"] = "pending_owner_review"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        verifier.validate_false_positive_dispositions(
            pending, today=verifier.date(2026, 10, 24)
        )


def _public_integrity_digest_source_identity() -> tuple[str, str, tuple[int, ...]]:
    source_path = Path(__file__).resolve()
    source = ast.parse(source_path.read_text(encoding="utf-8"))
    assignments = [
        node
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_AUD495_IMMUTABLE_315_PREFIX_SHA256"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    public_digest = ast.literal_eval(assignments[0].value)
    assert isinstance(public_digest, str)
    assert len(public_digest) == 64
    assert all(character in "0123456789abcdef" for character in public_digest)
    detector_digest = hashlib.sha1(
        public_digest.encode("ascii"), usedforsecurity=False
    ).digest()
    return (
        "tests/test_verify_secrets_baseline.py",
        "Hex High Entropy String",
        tuple(detector_digest),
    )


def test_public_integrity_digest_candidate_is_one_exact_source_identity() -> None:
    # The record below is an in-memory validator fixture, not owner approval.
    identity = _public_integrity_digest_source_identity()
    assert verifier._PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITIES == {identity}
    path, finding_type, digest_bytes = identity
    category = "public_integrity_digest"
    record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
    record["evidence"] = (
        "Public SHA-256 integrity digest of immutable 315-record disposition prefix; "
        "source-contract test guard in tests/test_verify_secrets_baseline.py; "
        "not credential material."
    )
    identity_finding = verifier.FindingIdentity(
        path, finding_type, bytes(digest_bytes).hex(), 1
    )
    assert verifier.validate_false_positive_dispositions(
        _disposition_document(record), today=verifier.date(2026, 10, 23)
    ) == {identity_finding}

    mutations = []
    changed_path = copy.deepcopy(record)
    changed_path["identity"]["path"] = "tests/test_other_policy.py"
    mutations.append(changed_path)
    changed_digest = copy.deepcopy(record)
    changed_bytes = list(digest_bytes)
    changed_bytes[0] ^= 1
    changed_digest["identity"]["hashed_secret_bytes"] = changed_bytes
    mutations.append(changed_digest)
    changed_category = copy.deepcopy(record)
    changed_category["category"] = "documented_crypto_test_vector"
    mutations.append(changed_category)
    excessive_expiry = copy.deepcopy(record)
    excessive_expiry["expires_on"] = "2027-01-11"
    mutations.append(excessive_expiry)
    missing_evidence = copy.deepcopy(record)
    missing_evidence["evidence"] = "not credential material"
    mutations.append(missing_evidence)
    for changed in mutations:
        with pytest.raises(verifier.BaselineArtifactError):
            verifier.validate_false_positive_dispositions(
                _disposition_document(changed),
                today=verifier.date(2026, 10, 23),
            )


_OCT24_APPROVED_PUBLIC_DIGEST_RECORDS = [
    {
        "identity": {
            "path": "tests/integration/test_aud350_stored_event_timestamp_migration.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                75,
                241,
                247,
                240,
                201,
                124,
                150,
                116,
                118,
                155,
                103,
                137,
                228,
                223,
                153,
                93,
                208,
                224,
                145,
                58,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public SHA-256 integrity digest of the frozen AUD-350 migration "
            "fixture; independent source-contract guard in "
            "tests/integration/test_aud350_stored_event_timestamp_migration.py; "
            "not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                200,
                36,
                105,
                58,
                159,
                122,
                4,
                140,
                251,
                170,
                213,
                164,
                38,
                210,
                200,
                58,
                142,
                211,
                129,
                137,
            ],
        },
        "category": "independent_contract_fingerprint",
        "evidence": (
            "Public detect-secrets SHA-1 identity of the first historical "
            "AUD-495 cache-key canary; independent source-contract guard in "
            "tests/test_verify_secrets_baseline.py; original canary record "
            "retains its aud495_cache_key_redaction_test_fixture category; not "
            "credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                73,
                167,
                128,
                111,
                78,
                205,
                84,
                128,
                139,
                99,
                249,
                165,
                3,
                236,
                79,
                56,
                147,
                246,
                140,
                151,
            ],
        },
        "category": "independent_contract_fingerprint",
        "evidence": (
            "Public detect-secrets SHA-1 identity of the second historical "
            "AUD-495 cache-key canary; independent source-contract guard in "
            "tests/test_verify_secrets_baseline.py; original canary record "
            "retains its aud495_cache_key_redaction_test_fixture category; not "
            "credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
]

_OCT24_ORIGINAL_SUFFIX = [
    {
        "identity": {
            "path": "tests/test_cache_object_keys_aud495.py",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                158,
                96,
                27,
                174,
                156,
                212,
                227,
                7,
                93,
                85,
                133,
                139,
                237,
                131,
                255,
                78,
                75,
                253,
                255,
                16,
            ],
        },
        "category": "aud495_cache_key_redaction_test_fixture",
        "evidence": (
            "AUD-495 cache-key log-redaction test fixture; synthetic canary "
            "used only by mocked backend tests; tests assert logger output "
            "omits the canary; not credential material"
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-23",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_cache_object_keys_aud495.py",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                206,
                224,
                34,
                26,
                248,
                78,
                22,
                250,
                97,
                128,
                240,
                96,
                14,
                161,
                75,
                225,
                205,
                151,
                196,
                143,
            ],
        },
        "category": "aud495_cache_key_redaction_test_fixture",
        "evidence": (
            "AUD-495 cache-key log-redaction test fixture; synthetic canary "
            "used only by mocked backend tests; tests assert logger output "
            "omits the canary; not credential material"
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-23",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                121,
                18,
                205,
                213,
                192,
                120,
                136,
                208,
                61,
                126,
                251,
                249,
                119,
                59,
                133,
                113,
                22,
                198,
                10,
                132,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public SHA-256 integrity digest of immutable 315-record "
            "disposition prefix; source-contract test guard in "
            "tests/test_verify_secrets_baseline.py; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
]


def test_oct24_public_digest_policy_preserves_all_318_prior_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    records = policy["records"]
    encoded_prefix = json.dumps(
        records[:315], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).hexdigest() == (
        _AUD495_IMMUTABLE_315_PREFIX_SHA256
    )
    assert records[315:318] == _OCT24_ORIGINAL_SUFFIX
    assert len(records) == 329
    assert records[318:321] == _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS


def test_oct24_public_digest_identities_are_bound_to_unchanged_source() -> None:
    root = Path(__file__).resolve().parents[1]
    migration_path = _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[0]["identity"]["path"]
    migration_source = ast.parse((root / migration_path).read_text(encoding="utf-8"))
    checksum_nodes = [
        node
        for node in migration_source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "BASELINE_MIGRATION_SHA256"
            for target in node.targets
        )
    ]
    assert len(checksum_nodes) == 1
    checksum = ast.literal_eval(checksum_nodes[0].value)
    assert isinstance(checksum, str)
    frozen_fixture = (
        root
        / "tests/fixtures/migrations/aud350"
        / "202603280001_reconcile_post_uuid_migration_drift_baseline.py.txt"
    )
    assert hashlib.sha256(frozen_fixture.read_bytes()).hexdigest() == checksum
    assert (
        list(hashlib.sha1(checksum.encode("ascii"), usedforsecurity=False).digest())
        == _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[0]["identity"]["hashed_secret_bytes"]
    )

    source = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    historical_nodes = [
        node
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES"
            for target in node.targets
        )
    ]
    assert len(historical_nodes) == 1
    fingerprints = [
        node.args[0].value
        for node in ast.walk(historical_nodes[0].value)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "bytes"
        and node.func.attr == "fromhex"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    assert len(fingerprints) == 2
    assert {tuple(bytes.fromhex(value)) for value in fingerprints} == {
        tuple(row["identity"]["hashed_secret_bytes"])
        for row in _OCT24_ORIGINAL_SUFFIX[:2]
    }
    assert {
        tuple(hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest())
        for value in fingerprints
    } == {
        tuple(row["identity"]["hashed_secret_bytes"])
        for row in _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[1:]
    }


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS)
def test_oct24_public_digest_validator_accepts_only_reviewed_identity(
    record: dict[str, Any],
) -> None:
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert verifier.validate_false_positive_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_oct24_public_digest_validator_rejects_scope_or_approval_change(
    record: dict[str, Any],
    mutation: str,
) -> None:
    changed = copy.deepcopy(record)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_public_digest.py"
    elif mutation == "detector":
        changed["identity"]["type"] = "Secret Keyword"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public value; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS)
def test_oct24_public_digest_validator_rejects_expired_disposition(
    record: dict[str, Any],
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )


@pytest.mark.parametrize(
    "category",
    ["public_integrity_digest", "independent_contract_fingerprint"],
)
def test_oct24_public_digest_reserved_test_path_still_rejects_unlisted_values(
    category: str,
) -> None:
    changed = copy.deepcopy(_OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[1])
    changed["category"] = category
    changed["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[1:])
def test_oct24_public_fingerprint_cannot_move_to_legacy_allowed_path(
    record: dict[str, Any],
) -> None:
    changed = copy.deepcopy(record)
    changed["identity"]["path"] = (
        "tests/fixtures/full-backend-reusable-baseline.v3.yaml"
    )
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


_PUBLIC_GIT_BLOB_APPROVED_RECORDS = json.loads(
    (
        Path(__file__).resolve().parent
        / "fixtures"
        / "public-git-blob-dispositions.json"
    ).read_text(encoding="utf-8")
)["records"]


def test_public_git_blob_policy_preserves_all_321_prior_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    # These existing independent guards compose the immutable 321-record prefix.
    test_oct24_public_digest_policy_preserves_all_318_prior_records()
    assert len(policy["records"]) == 329
    assert policy["records"][321:323] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:2]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS) == 6


def test_public_git_blob_rebind_policy_preserves_all_323_prior_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    test_public_git_blob_policy_preserves_all_321_prior_records()
    assert policy["records"][323:325] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]) == 2
    assert [
        record["identity"]["path"] for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:2]
    ] == [
        record["identity"]["path"] for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]
    ]
    assert {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:2]
    }.isdisjoint(
        {
            tuple(record["identity"]["hashed_secret_bytes"])
            for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]
        }
    )


def _public_git_blob_source_identity(
    consumer: str, assignment_name: str, source: bytes
) -> tuple[int, ...]:
    assignments = [
        node
        for node in ast.parse(consumer).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == assignment_name
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    value = ast.literal_eval(assignments[0].value)
    assert isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
    header = f"blob {len(source)}\0".encode("ascii")
    expected = hashlib.sha1(header + source, usedforsecurity=False).hexdigest()
    assert value == expected
    return tuple(hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest())


@pytest.mark.parametrize(
    ("record", "assignment_name", "source_path"),
    [
        (
            _PUBLIC_GIT_BLOB_APPROVED_RECORDS[0],
            "SOURCE_GIT_BLOB",
            "alembic/versions/148642dd1207_fix_missing_tables.py",
        ),
        (
            _PUBLIC_GIT_BLOB_APPROVED_RECORDS[1],
            "HISTORICAL_ORCHESTRATOR_BLOB",
            "tests/test_migration_148642dd1207_orchestrator.py",
        ),
    ],
)
def test_public_git_blob_current_pin_has_an_exact_approved_identity(
    record: dict[str, Any], assignment_name: str, source_path: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    consumer = root / record["identity"]["path"]
    if not consumer.exists():
        # Removed consumers may leave valid historical records, as with baseline.
        return
    # The fixture row supplies only the stable consumer path here: the current
    # literal may match any separately approved historical or rebound identity.
    digest = _public_git_blob_source_identity(
        consumer.read_text(encoding="utf-8"),
        assignment_name,
        (root / source_path).read_bytes(),
    )
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        row["identity"]
        == {
            "path": record["identity"]["path"],
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": list(digest),
        }
        and row["category"] == "public_integrity_digest"
        for row in policy["records"]
    )


def test_public_git_blob_binding_rejects_source_literal_or_assignment_drift() -> None:
    source = b"reviewed source\n"
    header = f"blob {len(source)}\0".encode("ascii")
    value = hashlib.sha1(header + source, usedforsecurity=False).hexdigest()
    consumer = f"SOURCE = {value!r}\n"
    expected = tuple(
        hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest()
    )
    assert _public_git_blob_source_identity(consumer, "SOURCE", source) == expected
    changed_value = ("0" if value[0] != "0" else "1") + value[1:]
    for changed_consumer, changed_source in (
        (consumer, source + b"# drift\n"),
        (f"SOURCE = {changed_value!r}\n", source),
        (consumer + consumer, source),
        (consumer.replace("SOURCE", "OTHER"), source),
    ):
        with pytest.raises(AssertionError):
            _public_git_blob_source_identity(changed_consumer, "SOURCE", changed_source)


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
def test_public_git_blob_validator_accepts_exact_historical_record_without_source(
    record: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert verifier.validate_false_positive_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "path_swap",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_public_git_blob_validator_rejects_changed_scope_or_metadata(
    record: dict[str, Any], mutation: str
) -> None:
    changed = copy.deepcopy(record)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_public_digest.py"
    elif mutation == "path_swap":
        changed["identity"]["path"] = next(
            row["identity"]["path"]
            for row in _PUBLIC_GIT_BLOB_APPROVED_RECORDS
            if row["identity"]["path"] != record["identity"]["path"]
        )
    elif mutation == "detector":
        changed["identity"]["type"] = "Secret Keyword"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public value; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
def test_public_git_blob_validator_rejects_expired_or_duplicate_record(
    record: dict[str, Any],
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 24),
        )


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
def test_public_git_blob_reserved_path_rejects_other_fingerprint(
    record: dict[str, Any],
) -> None:
    changed = copy.deepcopy(record)
    changed["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


_OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS = [
    {
        "identity": {
            "path": "frontend/scripts/generate-zod-root-lock-candidate.mjs",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                93,
                153,
                98,
                228,
                62,
                95,
                145,
                81,
                122,
                89,
                127,
                149,
                156,
                66,
                233,
                25,
                253,
                139,
                106,
                91,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public upstream Git commit identifier for colinhacks/zod v4.6.7; "
            "EXPECTED_ZOD_SOURCE_SHA in "
            "frontend/scripts/generate-zod-root-lock-candidate.mjs; official Git "
            "tag and hosted mature registry metadata agree; used for exact "
            "registry source-identity comparison; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_logging_pii_redaction_contract.py",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                241,
                119,
                30,
                46,
                101,
                173,
                30,
                82,
                73,
                135,
                104,
                15,
                34,
                136,
                138,
                34,
                211,
                106,
                94,
                148,
            ],
        },
        "category": "source_contract_identifier",
        "evidence": (
            "Public signing-key name csrf-signing-key in the secret_name metadata "
            "field of "
            "tests/test_logging_pii_redaction_contract.py::"
            "test_sensitive_field_matching_preserves_related_nonsecret_metadata; "
            "negative control requires this identifier to survive real log "
            "redaction; secret-related source identifier or required key-list "
            "expression; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
]


def test_observed_public_metadata_policy_preserves_all_325_prior_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    test_public_git_blob_rebind_policy_preserves_all_323_prior_records()
    assert len(policy["records"]) == 329
    assert policy["records"][325:327] == _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS
    assert len(_OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS) == 2


def _zod_public_source_fingerprint(source: str) -> tuple[int, ...]:
    values = re.findall(
        r'^const EXPECTED_ZOD_SOURCE_SHA = "([0-9a-f]{40})"$',
        source,
        flags=re.MULTILINE,
    )
    assert len(values) == 1
    # Default-argument and comparison behavior is exercised by the required
    # Node helper guards; this Python check binds the scanner literal identity.
    return tuple(
        hashlib.sha1(values[0].encode("ascii"), usedforsecurity=False).digest()
    )


def _public_metadata_label_from_source(source: str) -> str:
    functions = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name
        == "test_sensitive_field_matching_preserves_related_nonsecret_metadata"
    ]
    assert len(functions) == 1
    assignments = [
        node
        for node in functions[0].body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "event"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    event = ast.literal_eval(assignments[0].value)
    assert isinstance(event, dict) and "secret_name" in event
    assertions = [
        node.test
        for node in functions[0].body
        if isinstance(node, ast.Assert)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Call)
        and isinstance(node.test.left.func, ast.Name)
        and node.test.left.func.id == "_redact_pii"
    ]
    assert len(assertions) == 1
    comparison = assertions[0]
    assert len(comparison.ops) == 1 and isinstance(comparison.ops[0], ast.Eq)
    assert len(comparison.comparators) == 1
    expected = ast.literal_eval(comparison.comparators[0])
    call = comparison.left
    assert len(call.args) == 3 and not call.keywords
    assert isinstance(call.args[0], ast.Constant) and call.args[0].value is None
    assert isinstance(call.args[1], ast.Constant) and call.args[1].value == "info"
    assert isinstance(call.args[2], ast.Name) and call.args[2].id == "event"
    assert event == expected
    value = event["secret_name"]
    assert isinstance(value, str) and value
    return value


def _public_metadata_label_fingerprint(source: str) -> tuple[int, ...]:
    value = _public_metadata_label_from_source(source)
    return tuple(hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest())


@pytest.mark.parametrize(
    ("record", "fingerprint"),
    [
        (_OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[0], _zod_public_source_fingerprint),
        (
            _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[1],
            _public_metadata_label_fingerprint,
        ),
    ],
)
def test_observed_public_metadata_current_source_has_an_exact_approved_identity(
    record: dict[str, Any], fingerprint: Any
) -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / record["identity"]["path"]
    if not path.exists():
        # Historical dispositions may become stale when a consumer is removed.
        return
    digest = fingerprint(path.read_text(encoding="utf-8"))
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        row["identity"]
        == {
            "path": record["identity"]["path"],
            "type": record["identity"]["type"],
            "hashed_secret_bytes": list(digest),
        }
        and row["category"] == record["category"]
        for row in policy["records"]
    )


def test_zod_public_source_binding_rejects_changed_or_duplicate_pin() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[0]
    path = root / record["identity"]["path"]
    if not path.exists():
        return
    source = path.read_text(encoding="utf-8")
    original = _zod_public_source_fingerprint(source)
    value = re.findall(
        r'^const EXPECTED_ZOD_SOURCE_SHA = "([0-9a-f]{40})"$',
        source,
        flags=re.MULTILINE,
    )[0]
    changed = source.replace(value, "0" * len(value), 1)
    assert _zod_public_source_fingerprint(changed) != original
    declaration = next(
        line for line in source.splitlines() if line.startswith("const EXPECTED_")
    )
    with pytest.raises(AssertionError):
        _zod_public_source_fingerprint(source + "\n" + declaration + "\n")


def test_public_metadata_label_binding_rejects_changed_value_or_lost_control() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[1]
    path = root / record["identity"]["path"]
    if not path.exists():
        return
    source = path.read_text(encoding="utf-8")
    label = _public_metadata_label_from_source(source)
    original = _public_metadata_label_fingerprint(source)
    changed = source.replace(label, "different-public-label")
    assert _public_metadata_label_fingerprint(changed) != original
    for changed in (
        source.replace(label, "different-public-label", 1),
        source.replace('"secret_name"', '"csrf_hmac_secret"'),
        source.replace(
            'assert _redact_pii(None, "info", event) ==',
            "assert event ==",
        ),
    ):
        with pytest.raises(AssertionError):
            _public_metadata_label_from_source(changed)


@pytest.mark.parametrize("record", _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS)
def test_observed_public_metadata_accepts_exact_record_without_source(
    record: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert verifier.validate_false_positive_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize("record", _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "path_swap",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_observed_public_metadata_rejects_changed_scope_or_approval(
    record: dict[str, Any], mutation: str
) -> None:
    changed = copy.deepcopy(record)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_public_metadata.py"
    elif mutation == "path_swap":
        changed["identity"]["path"] = next(
            row["identity"]["path"]
            for row in _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS
            if row["identity"]["path"] != record["identity"]["path"]
        )
    elif mutation == "detector":
        changed["identity"]["type"] = "Base64 High Entropy String"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public metadata; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS)
def test_observed_public_metadata_rejects_expiry_duplicate_and_extra_identity(
    record: dict[str, Any],
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 24),
        )
    extra = copy.deepcopy(record)
    extra["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.validate_false_positive_dispositions(
            _disposition_document(copy.deepcopy(record), extra),
            today=verifier.date(2026, 10, 24),
        )


def test_public_git_blob_catalog_proof_preserves_all_327_prior_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    test_observed_public_metadata_policy_preserves_all_325_prior_records()
    assert len(policy["records"]) == 329
    assert policy["records"][327:328] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[4:5]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[4:5]) == 1
    rebound = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[4]
    assert rebound["identity"]["path"] == (
        "tests/helpers/migration_148642dd1207_trace.py"
    )
    assert tuple(rebound["identity"]["hashed_secret_bytes"]) not in {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:4]
    }


def test_public_git_blob_fixture_rebind_preserves_all_328_prior_records() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    test_public_git_blob_catalog_proof_preserves_all_327_prior_records()
    assert len(policy["records"]) == 329
    assert policy["records"][328:] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[5:]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[5:]) == 1
    rebound = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[5]
    assert (
        rebound["identity"]["path"]
        == (_PUBLIC_GIT_BLOB_APPROVED_RECORDS[1]["identity"]["path"])
    )
    assert tuple(rebound["identity"]["hashed_secret_bytes"]) not in {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:5]
    }
