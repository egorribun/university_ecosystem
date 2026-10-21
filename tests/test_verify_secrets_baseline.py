"""Focused contract tests for strict detect-secrets baseline verification."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import verify_secrets_baseline as verifier

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
    assert len(verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES) == 27
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
    assert len(verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES) == 15
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
