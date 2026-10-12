"""Focused contract tests for strict detect-secrets baseline verification."""

from __future__ import annotations

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
