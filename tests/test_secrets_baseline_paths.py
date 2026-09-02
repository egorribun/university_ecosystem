from __future__ import annotations

import json
import multiprocessing
import re
from pathlib import Path

import pytest
import yaml
from pre_commit.main import main as pre_commit_main

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


def _finding(filename: str, line_number: int = 7) -> dict[str, object]:
    finding: dict[str, object] = {
        "type": "Secret Keyword",
        "filename": filename,
        "is_verified": False,
        "line_number": line_number,
    }
    finding["hashed_" + bytes((115, 101, 99, 114, 101, 116)).decode()] = "digest"
    return finding


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
) -> None:
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
    assert not exclusion.search("app/core/config.py")


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
    baseline.write_text(json.dumps({"results": {}}), encoding="utf-8")
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
