"""Exercise the bounded, source-free Trivy tracked-change diagnostic."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-security-audit.yml"
REDIS = "charts/university-ecosystem/charts/redis-0.1.0.tgz"
PRIVATE_PATH = "PRIVATE_PATH_CANARY.txt"
PRIVATE_CONTENT = "PRIVATE_CONTENT_CANARY"
PREFIX = "TRIVY_FS_TRACKED_DIFF "
REJECTION = (
    "Trivy metadata diagnostic rejected its input "
    "(stage=identity-before; identity-check=tracked-clean); "
    "original security gates remain authoritative."
)


def _diagnostic() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    source = workflow.split("python3 -I -B - <<'TRIVY_METADATA'\n", 1)[1]
    source = source.split("          TRIVY_METADATA\n", 1)[0]
    return textwrap.dedent(source)


def _function(name: str, tmp_path: Path):
    source = _diagnostic().split('\nstage = "self-checks"', 1)[0]
    module_path = tmp_path / "trivy_workflow.py"
    module_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("trivy_workflow", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, name), f"{name} is missing from the tracked-diff diagnostic"
    return getattr(module, name)


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None):
    async def invoke():
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        return subprocess.CompletedProcess(
            command, process.returncode, stdout.decode(), stderr.decode()
        )

    return asyncio.run(invoke())


def _git(repo: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    assert executable is not None
    result = _run([executable, *arguments], repo)
    result.check_returncode()
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.name", "Trivy test")
    _git(root, "config", "user.email", "trivy-test@example.invalid")
    _git(root, "config", "core.autocrlf", "false")
    archive = root / REDIS
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"original-archive")
    (root / PRIVATE_PATH).write_text("original", encoding="utf-8")
    workflow = root / ".github" / "workflows" / "reusable-security-audit.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("fixture", encoding="utf-8")
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "-m", "fixture")
    return root


def _run_diagnostic(
    repo: Path, source: str | None = None, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # GitHub runs on Linux. Point the extracted workflow at the same real Git
    # binary available on the test host, including Windows developer machines.
    executable = shutil.which("git")
    assert executable is not None
    source = (source or _diagnostic()).replace('"/usr/bin/git"', repr(executable))
    if os.name == "nt":
        # Windows lacks these Linux-only open flags; these tests cover the
        # identity guards, not the production report-file protection.
        source = source.replace(
            "os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK", "os.O_RDONLY | os.O_BINARY"
        )
    head = _git(repo, "rev-parse", "HEAD")
    env = {
        **os.environ,
        "GITHUB_SHA": head,
        "EXPECTED_SOURCE_SHA": head,
        "GITHUB_WORKSPACE": str(repo),
        "GITHUB_RUN_ID": "42",
        "GITHUB_RUN_ATTEMPT": "1",
        "TRIVY_FS_OUTCOME": "failure",
        **(overrides or {}),
    }
    return _run([sys.executable, "-I", "-B", "-c", source], repo, env)


@pytest.mark.parametrize(
    ("change", "known", "unknown", "total"),
    [
        ("redis", True, 0, 1),
        ("unknown", False, 1, 1),
        ("both", True, 1, 2),
        ("deleted", False, 1, 1),
        ("rename", False, 2, 2),
        ("staged", True, 0, 1),
    ],
)
def test_dirty_checkout_is_classified_without_disclosing_paths_or_content(
    repo: Path, change: str, known: bool, unknown: int, total: int
) -> None:
    if change in {"redis", "both", "staged"}:
        (repo / REDIS).write_text(PRIVATE_CONTENT, encoding="utf-8")
    if change in {"unknown", "both"}:
        (repo / PRIVATE_PATH).write_text(PRIVATE_CONTENT, encoding="utf-8")
    if change == "deleted":
        (repo / REDIS).unlink()
    if change == "rename":
        _git(repo, "mv", REDIS, "PRIVATE_RENAMED_CANARY.tgz")
    if change == "staged":
        _git(repo, "add", REDIS)

    result = _run_diagnostic(repo)

    assert result.returncode == 1
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(PREFIX)
    assert json.loads(lines[0].removeprefix(PREFIX)) == {
        "knownRedisTgzModified": known,
        "unknownPathCount": unknown,
        "changedCount": total,
    }
    assert lines[1] == REJECTION
    assert PRIVATE_PATH not in result.stderr
    assert PRIVATE_CONTENT not in result.stderr
    assert "PRIVATE_RENAMED_CANARY" not in result.stderr
    assert REDIS not in result.stderr


def test_nul_classification_treats_unusual_paths_as_opaque_bytes(
    tmp_path: Path,
) -> None:
    classify = _function("classify_tracked_changes", tmp_path)
    raw = b"M\0" + REDIS.encode() + b"\0D\0PRIVATE\n\t\xff_CANARY\0"
    assert classify(raw) == {
        "knownRedisTgzModified": True,
        "unknownPathCount": 1,
        "changedCount": 2,
    }


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"M\0unclosed",
        b"M\0\0",
        b"R100\0old\0new\0",
        b"M\0same\0M\0same\0",
        b"M\0" + b"x" * 262144 + b"\0",
        b"".join(b"M\0path-" + str(i).encode() + b"\0" for i in range(4097)),
    ],
    ids=[
        "empty",
        "unterminated",
        "empty-path",
        "rename",
        "duplicate",
        "bytes",
        "count",
    ],
)
def test_classifier_rejects_malformed_or_oversized_diffs(
    raw: bytes, tmp_path: Path
) -> None:
    classify = _function("classify_tracked_changes", tmp_path)
    with pytest.raises(ValueError):
        classify(raw)


def test_diff_reader_enforces_a_hard_byte_limit_on_real_subprocess_output(
    tmp_path: Path,
) -> None:
    read = _function("bounded_process_output", tmp_path)
    program = "import sys; sys.stdout.buffer.write(b'x' * int(sys.argv[1]))"
    command = [sys.executable, "-I", "-B", "-c", program]
    assert len(read([*command, "262144"])) == 262144
    with pytest.raises(ValueError):
        read([*command, "262145"])


def _event_wait_command() -> list[str]:
    return [
        sys.executable,
        "-I",
        "-B",
        "-c",
        "from threading import Event; print('READY', flush=True); Event().wait()",
    ]


def test_timeout_fixture_signals_readiness_then_blocks_until_reaped() -> None:
    async def exercise() -> None:
        process = await asyncio.create_subprocess_exec(
            *_event_wait_command(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert process.stdout is not None
            ready = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert ready.rstrip(b"\r\n") == b"READY"
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=0.2)
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
        assert process.returncode is not None and process.returncode != 0

    asyncio.run(exercise())


def test_diff_reader_rejects_failure_and_timeout(tmp_path: Path) -> None:
    read = _function("bounded_process_output", tmp_path)
    with pytest.raises(ValueError):
        read([sys.executable, "-I", "-B", "-c", "raise SystemExit(2)"])
    with pytest.raises(subprocess.TimeoutExpired):
        read(_event_wait_command(), timeout=0.2)


@pytest.mark.parametrize("exception", ["ValueError", "RuntimeError"])
def test_diagnostic_failure_still_rejects_without_exposing_its_input(
    repo: Path, exception: str
) -> None:
    (repo / PRIVATE_PATH).write_text(PRIVATE_CONTENT, encoding="utf-8")
    original = _diagnostic()
    source = original.replace(
        "diff = bounded_tracked_diff()", f'raise {exception}("PRIVATE_ERROR_CANARY")', 1
    )
    assert source != original
    result = _run_diagnostic(repo, source)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == REJECTION


def test_checkout_identity_failure_never_classifies_changes(repo: Path) -> None:
    (repo / PRIVATE_PATH).write_text(PRIVATE_CONTENT, encoding="utf-8")
    result = _run_diagnostic(repo, overrides={"GITHUB_SHA": "0" * 40})
    assert result.returncode == 1
    assert result.stdout == ""
    assert PREFIX not in result.stderr
    assert "stage=identity-before; identity-check=checkout-head" in result.stderr
    assert PRIVATE_PATH not in result.stderr
    assert PRIVATE_CONTENT not in result.stderr


def test_clean_checkout_does_not_emit_tracked_change_diagnostic(repo: Path) -> None:
    result = _run_diagnostic(repo)
    assert result.returncode == 1
    assert result.stdout == ""
    assert PREFIX not in result.stderr
    assert "stage=read-before; identity-check=not-applicable" in result.stderr


def test_identity_after_rejection_does_not_emit_tracked_change_diagnostic(
    repo: Path,
) -> None:
    (repo / "trivy-fs.sarif").write_text(
        json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {"driver": {"name": "Trivy", "version": "0.75.0"}},
                        "results": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = _diagnostic().replace(
        '    stage = "identity-after"\n',
        '    Path("PRIVATE_PATH_CANARY.txt").write_text("changed")\n'
        '    stage = "identity-after"\n',
        1,
    )
    result = _run_diagnostic(repo, source)
    assert result.returncode == 1
    assert result.stdout == ""
    assert PREFIX not in result.stderr
    assert "stage=identity-after; identity-check=tracked-clean" in result.stderr
