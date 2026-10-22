from __future__ import annotations

import hashlib
import json
import multiprocessing
import re
import secrets
import subprocess
from pathlib import Path

import pytest
import yaml
from pre_commit.main import main as pre_commit_main

import scripts.run_detect_secrets as detect_secrets_wrapper
import scripts.secrets_baseline as baseline_module
from scripts.run_detect_secrets import (
    _baseline_path,
    normalize_detect_secrets_arguments,
    run_detect_secrets_hook,
)
from scripts.secrets_baseline import (
    _acquire_with_retry,
    canonicalize_baseline_file,
    canonicalize_document,
)
from scripts.verify_secrets_baseline import (
    BaselineArtifactError,
    FindingIdentity,
    extract_findings,
)


def _finding(filename: str, line_number: int = 7) -> dict[str, object]:
    finding: dict[str, object] = {
        "type": "Secret Keyword",
        "filename": filename,
        "is_verified": False,
        "line_number": line_number,
    }
    finding["hashed_" + bytes((115, 101, 99, 114, 101, 116)).decode()] = "digest"
    return finding


def _runtime_identity(
    path: str = "tests/fixture.py",
    finding_type: str = "Hex High Entropy String",
) -> FindingIdentity:
    return FindingIdentity(
        path,
        finding_type,
        hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        1,
    )


def _identity_finding(
    identity: FindingIdentity, line_number: int = 1
) -> dict[str, object]:
    finding: dict[str, object] = {
        "type": identity.finding_type,
        "filename": identity.path,
        "is_verified": False,
        "is_secret": False,
        "line_number": line_number,
    }
    finding["hash" + "ed_" + "se" + "cret"] = identity.hashed_secret
    return finding


def _baseline_document(*identities: FindingIdentity) -> dict[str, object]:
    results: dict[str, list[dict[str, object]]] = {}
    for identity in identities:
        results.setdefault(identity.path, []).append(_identity_finding(identity))
    return {"version": "1.5.0", "results": results}


def _run_concurrent_baseline_update(
    baseline: str,
    hook_arguments: list[str],
    result_path: str,
    entered: object,
    release: object,
) -> None:
    def runner(_arguments: list[str]) -> int:
        document = json.loads(Path(baseline).read_text(encoding="utf-8"))
        entered.set()
        if not release.wait(10):
            raise TimeoutError("baseline concurrency test release timed out")
        document["results"][result_path] = []
        Path(baseline).write_text(json.dumps(document), encoding="utf-8")
        return 0

    result = run_detect_secrets_hook(hook_arguments, runner)
    if result != 0:
        raise RuntimeError(f"unexpected hook result: {result}")


def test_canonicalize_document_merges_windows_and_posix_result_paths() -> None:
    document = {
        "version": "1.5.0",
        "results": {
            r"tests\test_auth.py": [_finding(r"tests\test_auth.py")],
            "tests/test_auth.py": [_finding("tests/test_auth.py")],
        },
        "generated_at": "2026-08-26T00:00:00Z",
    }

    canonical = canonicalize_document(document)

    assert list(canonical["results"]) == ["tests/test_auth.py"]
    assert canonical["results"]["tests/test_auth.py"] == [
        _finding("tests/test_auth.py")
    ]


def test_canonicalize_baseline_file_is_idempotent(tmp_path: Path) -> None:
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text(
        json.dumps({"results": {r"app\core.py": [_finding(r"app\core.py")]}}),
        encoding="utf-8",
    )

    assert canonicalize_baseline_file(baseline) is True
    first = baseline.read_bytes()
    assert canonicalize_baseline_file(baseline) is False
    assert baseline.read_bytes() == first
    assert b"app/core.py" in first
    assert b"app\\\\core.py" not in first


def test_hook_arguments_are_posix_normalized_without_changing_options() -> None:
    assert normalize_detect_secrets_arguments(
        ["--baseline", r"quality\.secrets.baseline", r"app\core.py"]
    ) == ["--baseline", "quality/.secrets.baseline", "app/core.py"]


def test_hook_argument_normalization_preserves_regex_values() -> None:
    assert normalize_detect_secrets_arguments(
        [
            "--exclude-lines",
            r"\bTOKEN\b",
            r"tests\test_auth.py",
            r"--exclude-files=fixtures\\.*",
        ]
    ) == [
        "--exclude-lines",
        r"\bTOKEN\b",
        "tests/test_auth.py",
        r"--exclude-files=fixtures\\.*",
    ]


def test_baseline_path_uses_equals_last_value_and_effective_custom_root(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    arguments = normalize_detect_secrets_arguments(
        [
            "--baseline",
            "ignored.baseline",
            "-C",
            str(repository),
            "--baseline=.secrets.baseline",
        ]
    )

    assert (
        _baseline_path(arguments, tmp_path)
        == (repository / ".secrets.baseline").resolve()
    )


def test_hook_runs_from_effective_custom_root_and_restores_cwd(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    baseline = repository / ".secrets.baseline"
    baseline.write_text(json.dumps({"results": {}}), encoding="utf-8")
    original = Path.cwd()
    observed: list[Path] = []

    result = run_detect_secrets_hook(
        [f"-C{repository}", "--baseline=.secrets.baseline"],
        lambda _arguments: observed.append(Path.cwd()) or 0,
    )

    assert result == 0
    assert observed == [repository.resolve()]
    assert Path.cwd() == original


def test_hook_removes_every_custom_root_option_before_runner(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    repository = tmp_path / "repository"
    for directory in (first_root, second_root, repository):
        directory.mkdir()
    baseline = repository / ".secrets.baseline"
    baseline.write_text(json.dumps({"results": {}}), encoding="utf-8")
    observed: list[tuple[list[str], Path]] = []

    result = run_detect_secrets_hook(
        [
            "-C",
            str(first_root),
            f"-C={second_root}",
            f"-C{repository}",
            "--baseline=.secrets.baseline",
            "app/core/config.py",
        ],
        lambda arguments: observed.append((arguments, Path.cwd())) or 0,
    )

    assert result == 0
    assert observed == [
        (["--baseline=.secrets.baseline", "app/core/config.py"], repository.resolve())
    ]


def test_custom_root_wrapper_succeeds_with_actual_detect_secrets_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keep the integration hook hermetic.  Reusing a developer's global
    # pre-commit cache can make this contract fail for unrelated filesystem
    # permissions (for example, a stale read-only cloned repository on
    # Windows) and hides whether the wrapper itself works.
    monkeypatch.setenv("PRE_COMMIT_HOME", str(tmp_path / "pre-commit-home"))
    repository_root = Path(__file__).resolve().parents[1]
    config = tmp_path / "detect-secrets-integration.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "repos": [
                    {
                        "repo": "https://github.com/Yelp/detect-secrets",
                        "rev": "v1.5.0",
                        "hooks": [
                            {
                                "id": "detect-secrets",
                                "entry": (
                                    "python "
                                    f'"{repository_root / "scripts" / "run_detect_secrets.py"}"'
                                ),
                                "args": [
                                    "-C",
                                    str(repository_root),
                                    "--baseline",
                                    ".secrets.baseline",
                                ],
                            }
                        ],
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = pre_commit_main(
        [
            "run",
            "--config",
            str(config),
            "detect-secrets",
            "--files",
            "scripts/run_detect_secrets.py",
        ]
    )

    assert result == 0


def test_exact_reviewed_identity_is_visible_only_in_temporary_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = _runtime_identity()
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_bytes(
        (json.dumps(_baseline_document(), indent=2) + "\n").encode("utf-8")
    )
    before = baseline.read_bytes()
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_load_local_dispositions",
        lambda _root: {approved},
    )
    seen_overlay: list[Path] = []

    def runner(arguments: list[str]) -> int:
        overlay_path = _baseline_path(arguments)
        assert overlay_path is not None
        assert overlay_path != baseline.resolve()
        seen_overlay.append(overlay_path)
        document = json.loads(overlay_path.read_text(encoding="utf-8"))
        assert approved in extract_findings(document, artifact="test overlay")
        return 0

    result = detect_secrets_wrapper.run_detect_secrets_hook(
        ["--baseline", str(baseline), "tests/fixture.py"], runner
    )

    assert result == 0
    assert len(seen_overlay) == 1
    assert baseline.read_bytes() == before
    assert approved not in extract_findings(
        json.loads(baseline.read_text(encoding="utf-8")), artifact="real baseline"
    )


@pytest.mark.parametrize("changed_field", ["path", "type", "digest"])
def test_reviewed_identity_near_miss_remains_unsuppressed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
) -> None:
    approved = _runtime_identity()
    if changed_field == "path":
        scanned = FindingIdentity(
            "tests/other.py", approved.finding_type, approved.hashed_secret, 1
        )
    elif changed_field == "type":
        scanned = FindingIdentity(
            approved.path, "Base64 High Entropy String", approved.hashed_secret, 1
        )
    else:
        scanned = _runtime_identity(approved.path, approved.finding_type)

    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text(
        json.dumps(_baseline_document(), indent=2) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_load_local_dispositions",
        lambda _root: {approved},
    )

    def runner(arguments: list[str]) -> int:
        overlay_path = _baseline_path(arguments)
        assert overlay_path is not None
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        known = extract_findings(overlay, artifact="test overlay")
        return 0 if scanned in known else 1

    result = detect_secrets_wrapper.run_detect_secrets_hook(
        ["--baseline", str(baseline), "tests/fixture.py"], runner
    )

    assert result == 1
    assert scanned not in extract_findings(
        json.loads(baseline.read_text(encoding="utf-8")), artifact="real baseline"
    )


def test_line_number_update_persists_only_original_baseline_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = _runtime_identity(path="tests/existing.py")
    approved = _runtime_identity(path="tests/approved.py")
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text(
        json.dumps(_baseline_document(existing), indent=2) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_load_local_dispositions",
        lambda _root: {approved},
    )

    def runner(arguments: list[str]) -> int:
        overlay_path = _baseline_path(arguments)
        assert overlay_path is not None
        document = json.loads(overlay_path.read_text(encoding="utf-8"))
        updated = False
        for findings in document["results"].values():
            for finding in findings:
                if finding["hash" + "ed_" + "se" + "cret"] == existing.hashed_secret:
                    finding["line_number"] = 19
                    updated = True
        assert updated
        overlay_path.write_text(json.dumps(document), encoding="utf-8")
        return 3

    result = detect_secrets_wrapper.run_detect_secrets_hook(
        ["--baseline", str(baseline), "tests/existing.py"], runner
    )

    document = json.loads(baseline.read_text(encoding="utf-8"))
    persisted = extract_findings(document, artifact="updated real baseline")
    assert result == 3
    assert existing in persisted
    assert approved not in persisted
    assert document["results"][existing.path][0]["line_number"] == 19


def test_local_policy_defaults_to_immutable_head_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _runtime_identity()
    head = "a" * 40
    monkeypatch.delenv(detect_secrets_wrapper._OWNER_DISPOSITION_OPT_IN, raising=False)
    monkeypatch.setattr(
        detect_secrets_wrapper, "_repository_root", lambda _root: tmp_path
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_git",
        lambda _root, *_args: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=f"{head}\n".encode(), stderr=b""
        ),
    )
    loaded: list[tuple[str, Path]] = []

    def trusted_loader(source: str, *, repository_root: Path) -> set[FindingIdentity]:
        loaded.append((source, repository_root))
        return {identity}

    monkeypatch.setattr(
        detect_secrets_wrapper,
        "load_trusted_base_false_positive_dispositions",
        trusted_loader,
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "load_owner_authored_candidate_false_positive_dispositions",
        lambda **_kwargs: pytest.fail("candidate policy must not load by default"),
    )

    assert detect_secrets_wrapper._load_local_dispositions(tmp_path) == {identity}
    assert loaded == [(head, tmp_path)]


def test_local_candidate_policy_requires_explicit_staged_clean_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _runtime_identity()
    monkeypatch.setenv(detect_secrets_wrapper._OWNER_DISPOSITION_OPT_IN, "1")
    monkeypatch.setattr(
        detect_secrets_wrapper, "_repository_root", lambda _root: tmp_path
    )
    checked: list[Path] = []
    loaded: list[Path] = []
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_candidate_policy_is_staged_and_clean",
        lambda root: checked.append(root),
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "load_owner_authored_candidate_false_positive_dispositions",
        lambda *, repository_root: loaded.append(repository_root) or {identity},
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "load_trusted_base_false_positive_dispositions",
        lambda *_args, **_kwargs: pytest.fail("HEAD source must not load on opt-in"),
    )

    assert detect_secrets_wrapper._load_local_dispositions(tmp_path) == {identity}
    assert checked == [tmp_path]
    assert loaded == [tmp_path]


def test_local_candidate_policy_fails_when_not_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(detect_secrets_wrapper._OWNER_DISPOSITION_OPT_IN, "1")
    monkeypatch.setattr(
        detect_secrets_wrapper, "_repository_root", lambda _root: tmp_path
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_git",
        lambda _root, *_args: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        ),
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "load_owner_authored_candidate_false_positive_dispositions",
        lambda **_kwargs: pytest.fail("unstaged candidate policy must not load"),
    )

    with pytest.raises(detect_secrets_wrapper.BaselineArtifactError):
        detect_secrets_wrapper._load_local_dispositions(tmp_path)


def test_local_candidate_policy_fails_when_worktree_differs_from_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(detect_secrets_wrapper._OWNER_DISPOSITION_OPT_IN, "1")
    monkeypatch.setattr(
        detect_secrets_wrapper, "_repository_root", lambda _root: tmp_path
    )
    statuses = iter((1, 1))
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_git",
        lambda _root, *_args: subprocess.CompletedProcess(
            args=[], returncode=next(statuses), stdout=b"", stderr=b""
        ),
    )
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "load_owner_authored_candidate_false_positive_dispositions",
        lambda **_kwargs: pytest.fail("dirty candidate policy must not load"),
    )

    with pytest.raises(detect_secrets_wrapper.BaselineArtifactError):
        detect_secrets_wrapper._load_local_dispositions(tmp_path)


def test_invalid_local_policy_stops_before_running_scanner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text(
        json.dumps(_baseline_document(), indent=2) + "\n", encoding="utf-8"
    )

    def invalid_policy(_root: Path) -> set[FindingIdentity]:
        raise detect_secrets_wrapper.BaselineArtifactError("invalid disposition policy")

    monkeypatch.setattr(
        detect_secrets_wrapper, "_load_local_dispositions", invalid_policy
    )
    calls: list[list[str]] = []

    with pytest.raises(detect_secrets_wrapper.BaselineArtifactError):
        detect_secrets_wrapper.run_detect_secrets_hook(
            ["--baseline", str(baseline)],
            lambda arguments: calls.append(arguments) or 0,
        )
    assert calls == []


def test_precommit_keeps_filename_filtering_and_example_exclusions() -> None:
    config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(
        hook
        for repository in config["repos"]
        for hook in repository["hooks"]
        if hook["id"] == "detect-secrets"
    )

    assert "pass_filenames" not in hook
    exclusion = re.compile(hook["exclude"])
    assert exclusion.search(".env.example")
    assert exclusion.search(".env.docker.example")
    assert exclusion.search("uv.lock")
    assert exclusion.fullmatch(".secrets.baseline")
    assert exclusion.fullmatch("frontend/WASM_SOURCE_PROVENANCE.json")
    assert not exclusion.search("frontend/WASM_SOURCE_PROVENANCE.json.bak")
    assert not exclusion.search("frontend/WASM_INVENTORY.json")
    assert not exclusion.search("app/core/config.py")


def test_generated_wasm_provenance_is_not_added_to_the_suppression_ledger() -> None:
    baseline = json.loads(Path(".secrets.baseline").read_text(encoding="utf-8"))

    assert "frontend/WASM_SOURCE_PROVENANCE.json" not in baseline["results"]


def test_canonicalizer_retries_when_content_changes_before_replace(
    tmp_path: Path, monkeypatch
) -> None:
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text(
        json.dumps({"results": {r"app\one.py": [_finding(r"app\one.py")]}}),
        encoding="utf-8",
    )
    real_replace = baseline_module._replace_if_unchanged
    calls = 0

    def concurrent_update(path: Path, temporary: Path, expected: bytes) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            path.write_text(
                json.dumps({"results": {r"app\two.py": [_finding(r"app\two.py", 9)]}}),
                encoding="utf-8",
            )
            return False
        return real_replace(path, temporary, expected)

    monkeypatch.setattr(baseline_module, "_replace_if_unchanged", concurrent_update)

    assert canonicalize_baseline_file(baseline) is True
    assert list(json.loads(baseline.read_text(encoding="utf-8"))["results"]) == [
        "app/two.py"
    ]


def test_lock_retry_waits_until_nonblocking_acquire_succeeds() -> None:
    attempts = 0
    current_time = 0.0
    waits: list[float] = []

    def acquire() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("busy")

    def wait(duration: float) -> None:
        nonlocal current_time
        waits.append(duration)
        current_time += duration

    _acquire_with_retry(
        acquire,
        timeout_seconds=1.0,
        retry_interval_seconds=0.25,
        clock=lambda: current_time,
        wait=wait,
    )

    assert attempts == 3
    assert waits == [0.25, 0.25]


def test_lock_retry_fails_with_bounded_timeout() -> None:
    current_time = 0.0

    def always_busy() -> None:
        raise OSError("busy")

    def wait(duration: float) -> None:
        nonlocal current_time
        current_time += duration

    with pytest.raises(TimeoutError, match=r"timed out after 0\.5s"):
        _acquire_with_retry(
            always_busy,
            timeout_seconds=0.5,
            retry_interval_seconds=0.2,
            clock=lambda: current_time,
            wait=wait,
        )


def test_detect_secrets_transaction_is_serialized_across_processes(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / ".secrets.baseline"
    baseline.write_text(json.dumps(_baseline_document()), encoding="utf-8")
    context = multiprocessing.get_context("spawn")
    first_entered = context.Event()
    first_release = context.Event()
    second_entered = context.Event()
    second_release = context.Event()
    first = context.Process(
        target=_run_concurrent_baseline_update,
        args=(
            str(baseline),
            ["-C", str(tmp_path), "--baseline=.secrets.baseline"],
            r"app\first.py",
            first_entered,
            first_release,
        ),
    )
    second = context.Process(
        target=_run_concurrent_baseline_update,
        args=(
            str(baseline),
            [
                "--baseline",
                str(tmp_path / "ignored.baseline"),
                f"--baseline={baseline}",
            ],
            r"app\second.py",
            second_entered,
            second_release,
        ),
    )
    try:
        first.start()
        assert first_entered.wait(10)
        second.start()
        assert not second_entered.wait(0.5)
        first_release.set()
        first.join(10)
        assert first.exitcode == 0
        assert second_entered.wait(10)
        second_release.set()
        second.join(10)
        assert second.exitcode == 0
    finally:
        first_release.set()
        second_release.set()
        for process in (first, second):
            if process.is_alive():
                process.terminate()
            process.join(5)

    assert list(json.loads(baseline.read_text(encoding="utf-8"))["results"]) == [
        "app/first.py",
        "app/second.py",
    ]


def test_disposition_overlay_restores_canonical_self_filter_and_stabilizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = _runtime_identity(path="tests/existing.py")
    approved = _runtime_identity(path="tests/reviewed.py")
    repository = tmp_path / "repository"
    repository.mkdir()
    baseline = repository / ".secrets.baseline"
    other_filter = {
        "path": "detect_secrets.filters.allowlist.is_line_allowlisted",
        "pattern": ["fixture-only"],
    }
    self_filter = {
        "path": "detect_secrets.filters.common.is_baseline_file",
        "filename": str(tmp_path / "stale-overlay" / ".secrets.baseline"),
    }
    document = _baseline_document(existing)
    document["filters_used"] = [other_filter, self_filter]
    document["generated_at"] = "initial-scan"
    baseline.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_load_local_dispositions",
        lambda _root: {approved},
    )

    overlay_paths: list[Path] = []
    filter_paths_seen_by_runner: list[str] = []
    approved_lines_before_scan: list[int] = []
    approved_lines_after_scan: list[int] = []

    def runner(arguments: list[str]) -> int:
        overlay_path = _baseline_path(arguments)
        assert overlay_path is not None
        overlay_path = overlay_path.resolve()
        overlay_paths.append(overlay_path)
        current = json.loads(overlay_path.read_text(encoding="utf-8"))
        baseline_filters = [
            item
            for item in current["filters_used"]
            if item.get("path") == "detect_secrets.filters.common.is_baseline_file"
        ]
        assert len(baseline_filters) == 1
        baseline_filter = baseline_filters[0]
        filter_paths_seen_by_runner.append(baseline_filter["filename"])
        baseline_filter["filename"] = str(overlay_path)

        approved_finding = current["results"][approved.path][0]
        approved_lines_before_scan.append(approved_finding["line_number"])
        approved_finding["line_number"] = 23
        approved_lines_after_scan.append(approved_finding["line_number"])
        if len(overlay_paths) == 1:
            current["results"][existing.path][0]["line_number"] = 19
        current["generated_at"] = f"scan-{len(overlay_paths)}"
        overlay_path.write_text(json.dumps(current), encoding="utf-8")
        return 3

    first_result = run_detect_secrets_hook(
        ["-C", str(repository), "--baseline=.secrets.baseline", "tests/existing.py"],
        runner,
    )
    after_first = json.loads(baseline.read_text(encoding="utf-8"))
    after_first_bytes = baseline.read_bytes()
    second_result = run_detect_secrets_hook(
        ["-C", str(repository), "--baseline=.secrets.baseline", "tests/existing.py"],
        runner,
    )
    after_second = json.loads(baseline.read_text(encoding="utf-8"))

    assert first_result == 3
    assert second_result == 0
    assert len(overlay_paths) == 2
    assert overlay_paths[0] != overlay_paths[1]
    assert [Path(path).resolve() for path in filter_paths_seen_by_runner] == (
        overlay_paths
    )
    assert approved_lines_before_scan == [1, 1]
    assert approved_lines_after_scan == [23, 23]
    assert baseline.read_bytes() == after_first_bytes
    expected_filters = [
        other_filter,
        {
            "path": "detect_secrets.filters.common.is_baseline_file",
            "filename": ".secrets.baseline",
        },
    ]
    assert after_first["filters_used"] == expected_filters
    assert after_second["filters_used"] == after_first["filters_used"]
    assert after_first["generated_at"] == "scan-1"
    assert after_second["generated_at"] == "scan-1"
    persisted = extract_findings(after_second, artifact="stable baseline")
    assert existing in persisted
    assert approved not in persisted
    assert after_second["results"][existing.path][0]["line_number"] == 19


def test_stale_self_filter_is_committed_when_scan_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = _runtime_identity(path="tests/approved.py")
    repository = tmp_path / "repository"
    repository.mkdir()
    baseline = repository / ".secrets.baseline"
    other_filter = {
        "path": "detect_secrets.filters.allowlist.is_line_allowlisted",
        "pattern": ["fixture-only"],
    }
    stale_filter = {
        "path": "detect_secrets.filters.common.is_baseline_file",
        "filename": str(tmp_path / "old-overlay" / ".secrets.baseline"),
    }
    document = _baseline_document()
    document["filters_used"] = [other_filter, stale_filter]
    baseline.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_load_local_dispositions",
        lambda _root: {approved},
    )

    seen_overlay_paths: list[tuple[str, str]] = []

    def no_change_runner(arguments: list[str]) -> int:
        overlay_path = _baseline_path(arguments)
        assert overlay_path is not None
        current = json.loads(overlay_path.read_text(encoding="utf-8"))
        self_filter = next(
            item
            for item in current["filters_used"]
            if item.get("path") == "detect_secrets.filters.common.is_baseline_file"
        )
        seen_overlay_paths.append(
            (str(overlay_path.resolve()), self_filter["filename"])
        )
        return 0

    arguments = [
        "-C",
        str(repository),
        "--baseline=.secrets.baseline",
        "tests/existing.py",
    ]
    first_result = run_detect_secrets_hook(arguments, no_change_runner)
    repaired = json.loads(baseline.read_text(encoding="utf-8"))
    second_result = run_detect_secrets_hook(arguments, no_change_runner)
    after_second = json.loads(baseline.read_text(encoding="utf-8"))

    assert first_result == 3
    assert second_result == 0
    assert len(seen_overlay_paths) == 2
    assert seen_overlay_paths[0][0] != seen_overlay_paths[1][0]
    assert all(
        Path(actual).resolve() == Path(recorded).resolve()
        for actual, recorded in seen_overlay_paths
    )
    expected_filters = [
        other_filter,
        {
            "path": "detect_secrets.filters.common.is_baseline_file",
            "filename": ".secrets.baseline",
        },
    ]
    assert repaired["filters_used"] == expected_filters
    assert after_second["filters_used"] == expected_filters


@pytest.mark.parametrize(
    "document",
    [
        None,
        {"filters_used": "invalid"},
        {
            "filters_used": [
                {
                    "path": "detect_secrets.filters.common.is_baseline_file",
                    "filename": ".secrets.baseline",
                },
                {
                    "path": "detect_secrets.filters.common.is_baseline_file",
                    "filename": ".secrets.baseline",
                },
            ]
        },
        {"filters_used": [{"path": "detect_secrets.filters.common.is_baseline_file"}]},
    ],
)
def test_invalid_self_filter_metadata_fails_closed(document: object) -> None:
    with pytest.raises(detect_secrets_wrapper.BaselineArtifactError):
        detect_secrets_wrapper._baseline_filter_entries(document)


def test_empty_self_filter_filename_fails_closed() -> None:
    with pytest.raises(detect_secrets_wrapper.BaselineArtifactError):
        detect_secrets_wrapper._set_baseline_filter_filename({"filters_used": []}, "")


def test_external_baseline_filter_uses_normalized_caller_spelling(
    tmp_path: Path,
) -> None:
    scan_root = tmp_path / "repository"
    scan_root.mkdir()
    outside_baseline = tmp_path / "outside" / ".secrets.baseline"

    assert (
        detect_secrets_wrapper._canonical_baseline_filter_filename(
            outside_baseline, scan_root, "../outside/.secrets.baseline"
        )
        == "../outside/.secrets.baseline"
    )


def test_disposition_only_scan_rejects_concurrent_baseline_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = _runtime_identity(path="tests/reviewed.py")
    repository = tmp_path / "repository"
    repository.mkdir()
    baseline = repository / ".secrets.baseline"
    baseline.write_bytes(
        (json.dumps(_baseline_document(), indent=2) + "\n").encode("utf-8")
    )
    original_bytes = baseline.read_bytes()
    concurrent_bytes: list[bytes] = []
    monkeypatch.setattr(
        detect_secrets_wrapper,
        "_load_local_dispositions",
        lambda _root: {approved},
    )

    def runner(arguments: list[str]) -> int:
        overlay_path = _baseline_path(arguments)
        assert overlay_path is not None
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        approved_finding = overlay["results"][approved.path][0]
        assert approved_finding["line_number"] == 1
        approved_finding["line_number"] = 23
        overlay["generated_at"] = "scanner-only-update"
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")

        concurrent_document = json.loads(baseline.read_text(encoding="utf-8"))
        concurrent_document["generated_at"] = "concurrent-editor-update"
        baseline.write_bytes(
            (json.dumps(concurrent_document, indent=2) + "\n").encode("utf-8")
        )
        concurrent_bytes.append(baseline.read_bytes())
        return 3

    with pytest.raises(
        BaselineArtifactError, match="baseline changed during scanner update"
    ):
        run_detect_secrets_hook(
            [
                "-C",
                str(repository),
                "--baseline=.secrets.baseline",
                "tests/existing.py",
            ],
            runner,
        )

    assert concurrent_bytes
    assert baseline.read_bytes() == concurrent_bytes[0]
    assert baseline.read_bytes() != original_bytes
