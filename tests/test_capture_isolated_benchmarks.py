import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality.capture_isolated_benchmarks import (
    CAPTURE_SIDE_WORKERS,
    CONTAINER_HOME,
    DOCKER_BINARY,
    GO_IMAGE,
    PAIR_COUNT,
    TIMEOUT_BINARY,
    TRUSTED_GO_BENCHMARK_BLOB,
    TRUSTED_GO_BENCHMARK_COMMIT,
    TRUSTED_GO_BENCHMARK_CONTAINER_PATH,
    TRUSTED_GO_BENCHMARK_PARENT,
    TRUSTED_GO_BENCHMARK_PATH,
    TRUSTED_GO_BENCHMARK_SHA256,
    TRUSTED_GO_BENCHMARK_TREE,
    CaptureArguments,
    CaptureError,
    TrustedGoBenchmarkOverlay,
    _build_rust_image,
    _capture_pair_sides_concurrently,
    _container_tool_output,
    _copy_limited_stream,
    _create_private_volume,
    _docker_server_version,
    _force_remove_container,
    _go_environment,
    _go_prefetch_environment,
    _go_program,
    _is_symlink_or_junction,
    _prepare_trusted_go_benchmark_overlay,
    _remove_image,
    _remove_trusted_go_benchmark_overlay,
    _remove_volume,
    _rust_environment,
    _rust_prefetch_program,
    _safe_capture,
    _start_cache_holder,
    _timeout_command,
    _validate_distinct_worktrees,
    _validate_image_content_id,
    _write_toolchain,
    build_container_command,
    capture,
    prepare_artifact_root,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_container_command_has_an_explicit_non_privileged_boundary(
    tmp_path: Path,
) -> None:
    """Candidate code must not receive host evidence, tokens, or a writable source."""

    source = tmp_path / "candidate-source"
    source.mkdir()
    command = build_container_command(
        image="example.invalid/performance@sha256:" + "a" * 64,
        source_worktree=source,
        cache_volume="private-candidate-cache",
        container_name="quality-benchmark-" + "a" * 32,
        workdir="/src/services/ws-hub",
        network="none",
        environment={
            "GOCACHE": "/cache/go-build",
            "GOMODCACHE": "/cache/go-mod",
            "GOPATH": "/cache/go-path",
            "HOME": CONTAINER_HOME,
        },
        program=("go", "test", "-mod=readonly", "-bench=.", "./..."),
    )
    command_text = "\n".join(command)

    for required_fragment in (
        "--name",
        "quality-benchmark-" + "a" * 32,
        "--init",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        "--read-only",
        "--log-driver",
        "local",
        "--log-opt",
        "max-size=16m",
        "max-file=1",
        "compress=false",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--memory",
        "6g",
        "--memory-swap",
        "6g",
        "--cpus",
        "2.0",
        "--pids-limit",
        "512",
        "--user",
        "10001:10001",
        "type=bind,src=" + str(source.resolve()) + ",dst=/src,readonly",
        "type=volume,src=private-candidate-cache,dst=/cache",
    ):
        assert required_fragment in command_text

    assert "docker.sock" not in command_text
    assert "GITHUB_" not in command_text
    assert "RUNNER_" not in command_text
    assert "/artifacts" not in command_text
    assert command.count("--mount") == 2
    assert command.count("--log-opt") == 3

    def has_docker_option(option: str) -> bool:
        return any(
            token == option or token.startswith(option + "=") for token in command
        )

    for forbidden_option in (
        "--privileged",
        "--pid",
        "--ipc",
        "--uts",
        "--userns",
        "--device",
    ):
        assert not has_docker_option(forbidden_option)
    assert "seccomp=unconfined" not in command_text
    assert "--rm" not in command
    assert command[-5:] == [
        "go",
        "test",
        "-mod=readonly",
        "-bench=.",
        "./...",
    ]


def test_container_command_mounts_the_trusted_go_benchmark_as_a_read_only_overlay(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate-source"
    source.mkdir()
    source_target = source / TRUSTED_GO_BENCHMARK_PATH
    source_target.parent.mkdir(parents=True)
    source_target.write_text("package hub\n", encoding="utf-8")
    overlay = tmp_path / "trusted-hub-bench_test.go"
    overlay.write_text("package hub\n", encoding="utf-8")

    command = build_container_command(
        image="example.invalid/performance@sha256:" + "a" * 64,
        source_worktree=source,
        cache_volume="private-candidate-cache",
        container_name="quality-benchmark-" + "a" * 32,
        workdir="/src/services/ws-hub",
        network="none",
        environment={"HOME": CONTAINER_HOME},
        program=("go", "test", "-run=^$", "./..."),
        trusted_go_benchmark=overlay,
    )

    mounts = [
        command[index + 1]
        for index, token in enumerate(command[:-1])
        if token == "--mount"
    ]
    assert mounts == [
        f"type=bind,src={source.resolve()},dst=/src,readonly",
        "type=bind,src="
        + str(overlay.resolve())
        + ",dst="
        + TRUSTED_GO_BENCHMARK_CONTAINER_PATH
        + ",readonly",
        "type=volume,src=private-candidate-cache,dst=/cache",
    ]

    with pytest.raises(CaptureError, match="only for Go capture"):
        build_container_command(
            image="example.invalid/performance@sha256:" + "a" * 64,
            source_worktree=source,
            cache_volume="private-candidate-cache",
            container_name="quality-benchmark-" + "b" * 32,
            workdir="/src",
            network="none",
            environment={"HOME": CONTAINER_HOME},
            program=("cargo", "bench"),
            trusted_go_benchmark=overlay,
        )


def _trusted_git_command_stub(
    monkeypatch: pytest.MonkeyPatch, content: bytes
) -> tuple[str, str, str, str]:
    import scripts.quality.capture_isolated_benchmarks as capture_module

    commit = "1" * 40
    parent = "2" * 40
    tree = "3" * 40
    blob = "4" * 40
    content_sha256 = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(capture_module, "TRUSTED_GO_BENCHMARK_COMMIT", commit)
    monkeypatch.setattr(capture_module, "TRUSTED_GO_BENCHMARK_PARENT", parent)
    monkeypatch.setattr(capture_module, "TRUSTED_GO_BENCHMARK_TREE", tree)
    monkeypatch.setattr(capture_module, "TRUSTED_GO_BENCHMARK_BLOB", blob)
    monkeypatch.setattr(capture_module, "TRUSTED_GO_BENCHMARK_SHA256", content_sha256)

    def fake_run_checked(
        command: tuple[str, ...], _description: str
    ) -> SimpleNamespace:
        git_args = command[3:]
        if git_args[:2] == ("rev-parse", "--verify"):
            object_spec = git_args[2]
            if object_spec.endswith("^{commit}"):
                return SimpleNamespace(stdout=f"{commit}\n")
            if object_spec.endswith("^{tree}"):
                return SimpleNamespace(stdout=f"{tree}\n")
            if object_spec == f"{commit}:{TRUSTED_GO_BENCHMARK_PATH}":
                return SimpleNamespace(stdout=f"{blob}\n")
        if git_args[:5] == ("rev-list", "--parents", "-n", "1", commit):
            return SimpleNamespace(stdout=f"{commit} {parent}\n")
        if git_args[:3] == ("cat-file", "-s", blob):
            return SimpleNamespace(stdout=f"{len(content)}\n")
        if git_args[:2] == ("cat-file", "blob") and git_args[2] == blob:
            return SimpleNamespace(stdout=content.decode("utf-8"))
        raise AssertionError("Unexpected trusted Git command")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._run_checked",
        fake_run_checked,
    )
    return commit, parent, tree, content_sha256


def test_trusted_go_benchmark_overlay_is_pinned_and_materialized_outside_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    runner_temp = tmp_path / "runner-temp"
    repo.mkdir()
    runner_temp.mkdir()
    content = b"package hub\n\nfunc BenchmarkTrusted(b *testing.B) {}\n"
    commit, parent, tree, content_sha256 = _trusted_git_command_stub(
        monkeypatch, content
    )

    overlay = _prepare_trusted_go_benchmark_overlay(
        repo_worktree=repo,
        runner_temp=runner_temp,
    )

    assert overlay.path.read_bytes() == content
    assert overlay.path.parent.parent.resolve() == runner_temp.resolve()
    assert overlay.commit == commit
    assert overlay.parent == parent
    assert overlay.tree == tree
    assert overlay.blob != ""
    assert overlay.sha256 == content_sha256
    assert overlay.size_bytes == len(content)
    _remove_trusted_go_benchmark_overlay(overlay, runner_temp)
    assert list(runner_temp.iterdir()) == []


def test_trusted_go_benchmark_bootstrap_provenance_is_explicit() -> None:
    assert (
        TRUSTED_GO_BENCHMARK_COMMIT
        == "6a1d1a78a5a78e793b0df32fc6dea1f192b0732f"  # pragma: allowlist secret -- public Git/SHA-256 provenance
    )
    assert (
        TRUSTED_GO_BENCHMARK_PARENT
        == "7fe9b621af3091ad88701c08c0f6441deecf8c26"  # pragma: allowlist secret -- public Git/SHA-256 provenance
    )
    assert (
        TRUSTED_GO_BENCHMARK_TREE
        == "9040080eb32793c6abf8964814e1bab3514593a8"  # pragma: allowlist secret -- public Git/SHA-256 provenance
    )
    assert TRUSTED_GO_BENCHMARK_PATH == "services/ws-hub/pkg/hub/hub_bench_test.go"
    assert (
        TRUSTED_GO_BENCHMARK_BLOB
        == "02659ee9e5b86c832f9afda1e938e9e10da3d613"  # pragma: allowlist secret -- public Git/SHA-256 provenance
    )
    assert (
        TRUSTED_GO_BENCHMARK_SHA256
        == (
            "a3f340ebaad4ac8248f52e8a0989a2e97e2616c3481e9f7785ac9c90ceaf1018"  # pragma: allowlist secret -- public Git/SHA-256 provenance
        )
    )


def test_trusted_go_benchmark_overlay_rejects_tree_pin_mismatch_before_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import scripts.quality.capture_isolated_benchmarks as capture_module

    repo = tmp_path / "repo"
    runner_temp = tmp_path / "runner-temp"
    repo.mkdir()
    runner_temp.mkdir()
    _trusted_git_command_stub(monkeypatch, b"package hub\n")

    original_run_checked = capture_module._run_checked

    def wrong_tree(command: tuple[str, ...], description: str) -> SimpleNamespace:
        result = original_run_checked(command, description)
        if description == "verify trusted benchmark commit tree":
            return SimpleNamespace(stdout="4" * 40 + "\n")
        return result

    monkeypatch.setattr(capture_module, "_run_checked", wrong_tree)
    with pytest.raises(CaptureError, match="tree does not match its pin"):
        _prepare_trusted_go_benchmark_overlay(
            repo_worktree=repo,
            runner_temp=runner_temp,
        )
    assert list(runner_temp.iterdir()) == []


def test_trusted_go_benchmark_overlay_rejects_content_digest_mismatch_before_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import scripts.quality.capture_isolated_benchmarks as capture_module

    repo = tmp_path / "repo"
    runner_temp = tmp_path / "runner-temp"
    repo.mkdir()
    runner_temp.mkdir()
    _trusted_git_command_stub(monkeypatch, b"package hub\n")
    monkeypatch.setattr(capture_module, "TRUSTED_GO_BENCHMARK_SHA256", "f" * 64)

    with pytest.raises(CaptureError, match="digest does not match its pin"):
        _prepare_trusted_go_benchmark_overlay(
            repo_worktree=repo,
            runner_temp=runner_temp,
        )
    assert list(runner_temp.iterdir()) == []


def test_container_command_allows_the_read_only_source_mount_root(
    tmp_path: Path,
) -> None:
    """Rust cargo commands run from the workspace mount root."""

    source = tmp_path / "candidate-source"
    source.mkdir()
    command = build_container_command(
        image="example.invalid/performance@sha256:" + "a" * 64,
        source_worktree=source,
        cache_volume="private-candidate-cache",
        container_name="quality-benchmark-" + "a" * 32,
        workdir="/src",
        network="none",
        environment={"HOME": CONTAINER_HOME},
        program=("cargo", "fetch", "--locked"),
    )

    assert command[command.index("--workdir") + 1] == "/src"


def test_container_command_reuses_a_persistent_cache_holder(
    tmp_path: Path,
) -> None:
    """Short-lived benchmark runs attach to the side's persistent cache holder."""

    source = tmp_path / "candidate-source"
    source.mkdir()
    holder = "quality-benchmark-" + "b" * 32
    command = build_container_command(
        image="example.invalid/performance@sha256:" + "a" * 64,
        source_worktree=source,
        cache_volume="private-candidate-cache",
        cache_holder=holder,
        container_name="quality-benchmark-" + "a" * 32,
        workdir="/src/services/ws-hub",
        network="none",
        environment={"HOME": CONTAINER_HOME},
        program=("go", "test", "-mod=readonly", "-bench=.", "./..."),
    )

    assert command[command.index("--volumes-from") + 1] == holder
    assert "type=volume,src=private-candidate-cache,dst=/cache" not in command


def test_limited_capture_stops_writing_before_an_untrusted_stream_can_fill_disk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stream limit is enforced during, not after, output capture."""

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.MAX_OUTPUT_BYTES", 8
    )
    destination = BytesIO()

    assert _copy_limited_stream(BytesIO(b"12345678"), destination) is False
    assert destination.getvalue() == b"12345678"

    destination = BytesIO()
    assert _copy_limited_stream(BytesIO(b"123456789"), destination) is True
    assert destination.getvalue() == b"12345678"


def test_rust_prefetch_selects_the_workspace_manifest() -> None:
    """`cargo fetch` runs from /src, so it must target the nested Rust manifest."""

    assert _rust_prefetch_program() == (
        "cargo",
        "fetch",
        "--locked",
        "--manifest-path",
        "native/rust_ext/Cargo.toml",
    )


def test_go_prefetch_is_read_only_workspace_safe() -> None:
    """Go dependency setup must not attempt to rewrite go.work.sum."""

    environment = _go_prefetch_environment()

    assert environment["GOWORK"] == "off"
    assert environment["GOFLAGS"] == "-mod=readonly -buildvcs=false"


@pytest.mark.parametrize("offline", [False, True])
def test_go_capture_never_uses_the_read_only_workspace_file(offline: bool) -> None:
    """Both dependency setup and benchmark runs use the module's go.mod graph."""

    environment = _go_environment(offline=offline)

    assert environment["GOWORK"] == "off"
    assert environment["GOFLAGS"] == "-mod=readonly -buildvcs=false"


def test_isolated_capture_rejects_a_single_checkout_for_both_sides(
    tmp_path: Path,
) -> None:
    """A wiring error must not compare a worktree with itself."""

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    with pytest.raises(CaptureError, match="different directories"):
        _validate_distinct_worktrees(worktree, worktree)


def test_capture_rejects_a_mismatched_worktree_head_before_benchmark_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Declared evidence revisions must match the commits actually mounted."""

    base_worktree = tmp_path / "base"
    candidate_worktree = tmp_path / "candidate"
    runner_temp = tmp_path / "runner-temp"
    for directory in (base_worktree, candidate_worktree, runner_temp):
        directory.mkdir()
    docker_binary = tmp_path / "docker"
    timeout_binary = tmp_path / "timeout"
    docker_binary.touch()
    timeout_binary.touch()
    arguments = CaptureArguments(
        format_name="go",
        base_worktree=base_worktree,
        candidate_worktree=candidate_worktree,
        artifact_root=runner_temp / "artifacts",
        runner_temp=runner_temp,
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        rust_dockerfile=None,
    )
    observed_commands: list[list[str]] = []
    benchmark_setup: list[str] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        observed_commands.append(command)
        worktree = Path(command[command.index("-C") + 1])
        revision = "c" * 40 if worktree == base_worktree else "b" * 40
        return SimpleNamespace(returncode=0, stdout=f"{revision}\n", stderr="")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.DOCKER_BINARY", docker_binary
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.TIMEOUT_BINARY", timeout_binary
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._create_private_volume",
        lambda *_args: benchmark_setup.append("volume"),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._prefetch",
        lambda **_kwargs: benchmark_setup.append("prefetch"),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._start_cache_holder",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._capture_pair",
        lambda **_kwargs: benchmark_setup.append("capture"),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._write_toolchain",
        lambda **_kwargs: benchmark_setup.append("toolchain"),
    )

    with pytest.raises(CaptureError, match="does not match declared base revision"):
        capture(arguments)

    assert observed_commands == [
        [
            "git",
            "-C",
            str(base_worktree),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
        [
            "git",
            "-C",
            str(candidate_worktree),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
    ]
    assert benchmark_setup == []


def test_capture_accepts_worktrees_with_matching_declared_heads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Matching Git commits proceed into the bounded paired capture sequence."""

    base_worktree = tmp_path / "base"
    candidate_worktree = tmp_path / "candidate"
    runner_temp = tmp_path / "runner-temp"
    for directory in (base_worktree, candidate_worktree, runner_temp):
        directory.mkdir()
    for worktree in (base_worktree, candidate_worktree):
        target = worktree / TRUSTED_GO_BENCHMARK_PATH
        target.parent.mkdir(parents=True)
        target.write_text("package hub\n", encoding="utf-8")
    docker_binary = tmp_path / "docker"
    timeout_binary = tmp_path / "timeout"
    docker_binary.touch()
    timeout_binary.touch()
    arguments = CaptureArguments(
        format_name="go",
        base_worktree=base_worktree,
        candidate_worktree=candidate_worktree,
        artifact_root=runner_temp / "artifacts",
        runner_temp=runner_temp,
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        rust_dockerfile=None,
    )
    observed_commands: list[list[str]] = []
    captured_descriptions: list[str] = []
    captured_harnesses: list[Path | None] = []
    reported_harnesses: list[TrustedGoBenchmarkOverlay | None] = []
    overlay_path = tmp_path / "trusted" / "hub_bench_test.go"
    overlay_path.parent.mkdir()
    overlay_path.write_text("package hub\n", encoding="utf-8")
    overlay = TrustedGoBenchmarkOverlay(
        path=overlay_path,
        commit=TRUSTED_GO_BENCHMARK_COMMIT,
        parent=TRUSTED_GO_BENCHMARK_PARENT,
        tree=TRUSTED_GO_BENCHMARK_TREE,
        blob=TRUSTED_GO_BENCHMARK_BLOB,
        sha256=TRUSTED_GO_BENCHMARK_SHA256,
        size_bytes=overlay_path.stat().st_size,
    )

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        observed_commands.append(command)
        worktree = Path(command[command.index("-C") + 1])
        revision = "a" * 40 if worktree == base_worktree else "b" * 40
        return SimpleNamespace(returncode=0, stdout=f"{revision}\n", stderr="")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.DOCKER_BINARY", docker_binary
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.TIMEOUT_BINARY", timeout_binary
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._prepare_trusted_go_benchmark_overlay",
        lambda **_kwargs: overlay,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._remove_trusted_go_benchmark_overlay",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._create_private_volume",
        lambda _image, _artifact_root, side: f"{side}-volume",
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._prefetch", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._start_cache_holder",
        lambda **_kwargs: None,
    )

    def fake_capture_pair(**kwargs: object) -> None:
        captured_descriptions.append(str(kwargs["description"]))
        benchmark = kwargs.get("trusted_go_benchmark")
        assert isinstance(benchmark, Path)
        captured_harnesses.append(benchmark)

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._capture_pair",
        fake_capture_pair,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._write_toolchain",
        lambda **kwargs: reported_harnesses.append(kwargs.get("trusted_go_benchmark")),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._remove_volume",
        lambda _volume: None,
    )

    capture(arguments)

    assert observed_commands == [
        [
            "git",
            "-C",
            str(base_worktree),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
        [
            "git",
            "-C",
            str(candidate_worktree),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
    ]
    assert captured_descriptions[:2] == [
        "warm base benchmark build",
        "warm candidate benchmark build",
    ]
    expected_pair_descriptions = {
        f"capture {side} benchmark pair {pair:02d}"
        for pair in range(1, PAIR_COUNT + 1)
        for side in ("base", "candidate")
    }
    assert set(captured_descriptions[2:]) == expected_pair_descriptions
    assert len(captured_harnesses) == 2 + (PAIR_COUNT * 2)
    assert set(captured_harnesses) == {overlay_path}
    assert reported_harnesses == [overlay]
    assert len(captured_descriptions[2:]) == PAIR_COUNT * CAPTURE_SIDE_WORKERS


def test_capture_pair_sides_concurrently_starts_both_independent_sides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One pair overlaps its independent Docker captures without sharing output."""

    sides = (
        ("base", tmp_path / "base", "base-cache"),
        ("candidate", tmp_path / "candidate", "candidate-cache"),
    )
    started: list[dict[str, object]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(CAPTURE_SIDE_WORKERS, timeout=2)

    def fake_capture(**kwargs: object) -> None:
        with lock:
            started.append(kwargs)
        try:
            barrier.wait()
        except threading.BrokenBarrierError as exc:
            raise AssertionError("pair sides were not started concurrently") from exc

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._capture_pair", fake_capture
    )

    _capture_pair_sides_concurrently(
        image="example.invalid/performance@sha256:" + "a" * 64,
        ordered_sides=sides,
        workdir="/src",
        environment={"HOME": CONTAINER_HOME},
        program=("cargo", "bench"),
        artifact_root=tmp_path / "artifacts",
        pair=3,
    )

    assert len(started) == CAPTURE_SIDE_WORKERS
    assert {str(item["description"]) for item in started} == {
        "capture base benchmark pair 03",
        "capture candidate benchmark pair 03",
    }
    assert {Path(item["output_path"]) for item in started} == {
        tmp_path / "artifacts" / "base" / "pair-03.txt",
        tmp_path / "artifacts" / "candidate" / "pair-03.txt",
    }
    assert all(item["emit_markers"] is False for item in started)


@pytest.mark.parametrize("bad_side", ("base", "candidate"))
@pytest.mark.parametrize(
    ("bad_kind", "expected_error"),
    (
        ("missing", "target is missing"),
        ("symlink", "must not be redirected"),
        ("junction", "must not be redirected"),
    ),
)
def test_capture_preflights_both_go_benchmark_targets_before_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad_side: str,
    bad_kind: str,
    expected_error: str,
) -> None:
    base_worktree = tmp_path / "base"
    candidate_worktree = tmp_path / "candidate"
    runner_temp = tmp_path / "runner-temp"
    for directory in (base_worktree, candidate_worktree, runner_temp):
        directory.mkdir()
    worktrees = {"base": base_worktree, "candidate": candidate_worktree}
    for side, worktree in worktrees.items():
        target = worktree / TRUSTED_GO_BENCHMARK_PATH
        if side == bad_side and bad_kind == "missing":
            continue
        target.parent.mkdir(parents=True)
        target.write_text("package hub\n", encoding="utf-8")

    docker_binary = tmp_path / "docker"
    timeout_binary = tmp_path / "timeout"
    docker_binary.touch()
    timeout_binary.touch()
    arguments = CaptureArguments(
        format_name="go",
        base_worktree=base_worktree,
        candidate_worktree=candidate_worktree,
        artifact_root=runner_temp / "artifacts",
        runner_temp=runner_temp,
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        rust_dockerfile=None,
    )
    resource_calls: list[str] = []
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.DOCKER_BINARY", docker_binary
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.TIMEOUT_BINARY", timeout_binary
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._resolve_worktree_head",
        lambda worktree, label: "a" * 40 if label == "base worktree" else "b" * 40,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._create_private_volume",
        lambda *_args: resource_calls.append("volume"),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._prefetch",
        lambda **_kwargs: resource_calls.append("prefetch"),
    )
    if bad_kind in {"symlink", "junction"}:
        bad_target = worktrees[bad_side] / TRUSTED_GO_BENCHMARK_PATH
        path_type = type(bad_target)
        original_is_symlink = path_type.is_symlink
        original_is_junction = path_type.is_junction
        if bad_kind == "symlink":
            monkeypatch.setattr(
                path_type,
                "is_symlink",
                lambda path: path == bad_target or original_is_symlink(path),
            )
        else:
            monkeypatch.setattr(
                path_type,
                "is_junction",
                lambda path: path == bad_target or original_is_junction(path),
            )

    with pytest.raises(CaptureError, match=expected_error):
        capture(arguments)

    assert resource_calls == []
    assert not arguments.artifact_root.exists()


def test_go_benchmark_target_guard_checks_symlink_and_junction_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "source"
    worktree.mkdir()
    target = worktree / TRUSTED_GO_BENCHMARK_PATH
    target.parent.mkdir(parents=True)
    target.write_text("package hub\n", encoding="utf-8")
    path_type = type(target)

    monkeypatch.setattr(path_type, "is_symlink", lambda path: path == target)
    monkeypatch.setattr(path_type, "is_junction", lambda _path: False)
    assert _is_symlink_or_junction(target) is True

    monkeypatch.setattr(path_type, "is_symlink", lambda _path: False)
    monkeypatch.setattr(path_type, "is_junction", lambda path: path == target)
    assert _is_symlink_or_junction(target) is True


def test_capture_pair_sides_concurrently_propagates_worker_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A side failure fails the pair after both workers have completed cleanup."""

    sides = (
        ("base", tmp_path / "base", "base-cache"),
        ("candidate", tmp_path / "candidate", "candidate-cache"),
    )
    barrier = threading.Barrier(CAPTURE_SIDE_WORKERS, timeout=2)
    calls: list[str] = []

    def fake_capture(**kwargs: object) -> None:
        description = str(kwargs["description"])
        calls.append(description)
        barrier.wait()
        if description.startswith("capture base"):
            raise CaptureError("base capture failed")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._capture_pair", fake_capture
    )

    with pytest.raises(CaptureError, match="base capture failed"):
        _capture_pair_sides_concurrently(
            image="example.invalid/performance@sha256:" + "b" * 64,
            ordered_sides=sides,
            workdir="/src",
            environment={"HOME": CONTAINER_HOME},
            program=("cargo", "bench"),
            artifact_root=tmp_path / "artifacts",
            pair=1,
        )

    assert set(calls) == {
        "capture base benchmark pair 01",
        "capture candidate benchmark pair 01",
    }


def test_capture_pair_sides_concurrently_requires_one_base_and_candidate(
    tmp_path: Path,
) -> None:
    """Reject malformed side lists before creating any benchmark container."""

    with pytest.raises(
        CaptureError,
        match="exactly one base and one candidate side",
    ):
        _capture_pair_sides_concurrently(
            image="example.invalid/performance@sha256:" + "c" * 64,
            ordered_sides=(
                ("base", tmp_path / "base", "base-cache"),
                ("base", tmp_path / "other", "other-cache"),
            ),
            workdir="/src",
            environment={"HOME": CONTAINER_HOME},
            program=("cargo", "bench"),
            artifact_root=tmp_path / "artifacts",
            pair=1,
        )


def test_image_content_id_must_be_an_immutable_sha256_identifier() -> None:
    """A mutable local tag alone is insufficient provenance for raw evidence."""

    assert _validate_image_content_id("sha256:" + "a" * 64) == "sha256:" + "a" * 64
    with pytest.raises(CaptureError, match="content ID"):
        _validate_image_content_id("quality-performance-rust:mutable")


def test_timeout_uses_a_hard_kill_deadline_and_cleanup_removes_named_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A quiet or SIGTERM-resistant benchmark cannot outlive its capture step."""

    command = _timeout_command(("docker", "run", "example"), timeout_seconds=300)
    assert command[:4] == [
        str(TIMEOUT_BINARY),
        "--foreground",
        "--kill-after=30s",
        "300s",
    ]

    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=1, stderr="No such container")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )
    container_name = "quality-benchmark-" + "b" * 32
    _force_remove_container(container_name)

    assert calls == [
        [str(DOCKER_BINARY), "container", "rm", "--force", container_name],
        [str(DOCKER_BINARY), "container", "inspect", container_name],
    ]


@pytest.mark.parametrize(
    ("failure", "failure_phase"),
    [
        (OSError("Docker client is unavailable"), "remove"),
        (subprocess.TimeoutExpired(["docker"], 30), "remove"),
        (OSError("Docker client is unavailable"), "inspect"),
        (subprocess.TimeoutExpired(["docker"], 30), "inspect"),
    ],
    ids=("remove-launch", "remove-timeout", "inspect-launch", "inspect-timeout"),
)
def test_force_remove_container_converts_docker_client_failures_to_capture_errors(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    failure_phase: str,
) -> None:
    """Unverified named-container cleanup must fail closed with a typed error."""

    container_name = "quality-benchmark-" + "d" * 32
    observed: list[tuple[list[str], object]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.append((command, kwargs.get("timeout")))
        if failure_phase == "inspect" and command[2] == "rm":
            return SimpleNamespace(returncode=1, stdout="", stderr="still present")
        raise failure

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )

    with pytest.raises(CaptureError, match="container cleanup") as error:
        _force_remove_container(container_name)

    assert container_name in str(error.value)
    assert observed[0] == (
        [str(DOCKER_BINARY), "container", "rm", "--force", container_name],
        30,
    )
    if failure_phase == "inspect":
        assert observed[1] == (
            [str(DOCKER_BINARY), "container", "inspect", container_name],
            30,
        )
    else:
        assert len(observed) == 1


def test_private_cache_volume_uses_a_capped_owned_tmpfs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Candidate cache storage must have a daemon-enforced size and ownership cap."""

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    volume_name = "quality-benchmark-cache-" + "a" * 32
    observed_commands: list[list[str]] = []

    class FinishedProcess:
        stdout = BytesIO()

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 0

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        observed_commands.append(command)
        if command[:3] == [str(DOCKER_BINARY), "volume", "create"]:
            return SimpleNamespace(returncode=0, stdout=f"{volume_name}\n", stderr="")
        if command[1:4] == ["container", "rm", "--force"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )
    captured_launches: list[list[str]] = []

    def fake_popen(command: list[str], **_: object) -> FinishedProcess:
        captured_launches.append(command)
        return FinishedProcess()

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.uuid.uuid4",
        lambda: SimpleNamespace(hex="a" * 32),
    )

    volume = _create_private_volume(
        "example.invalid/performance@sha256:" + "a" * 64,
        artifact_root,
        "candidate",
    )

    assert volume == volume_name
    assert observed_commands[0] == [
        str(DOCKER_BINARY),
        "volume",
        "create",
        "--driver",
        "local",
        "--opt",
        "type=tmpfs",
        "--opt",
        "device=tmpfs",
        "--opt",
        "o=size=2g,uid=10001,gid=10001,mode=0700",
        volume_name,
    ]
    initialization_command = captured_launches[0]
    assert initialization_command[:4] == [
        str(TIMEOUT_BINARY),
        "--foreground",
        "--kill-after=30s",
        "60s",
    ]
    initialization_command = initialization_command[4:]
    assert initialization_command[:2] == [str(DOCKER_BINARY), "run"]
    for option, value in (
        ("--memory", "6g"),
        ("--memory-swap", "6g"),
        ("--cpus", "2.0"),
        ("--pids-limit", "512"),
    ):
        assert initialization_command[initialization_command.index(option) + 1] == value
    assert "--init" in initialization_command
    assert (
        initialization_command[initialization_command.index("--platform") + 1]
        == "linux/amd64"
    )
    assert "--log-driver" in initialization_command
    assert (
        initialization_command[initialization_command.index("--log-driver") + 1]
        == "local"
    )
    assert [
        initialization_command[index + 1]
        for index, value in enumerate(initialization_command)
        if value == "--log-opt"
    ] == ["max-size=16m", "max-file=1", "compress=false"]


@pytest.mark.parametrize("offline", [False, True])
def test_language_capture_environments_pin_their_compilers(offline: bool) -> None:
    """Candidate toolchain files cannot select or download a different compiler."""

    assert _go_environment(offline=offline)["GOTOOLCHAIN"] == "local"
    assert _rust_environment(offline=offline)["RUSTUP_TOOLCHAIN"] == "1.94.1"


def test_toolchain_query_uses_bounded_logs_and_a_pinned_compiler_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Version capture streams through a bounded, resource-limited Docker run."""

    observed_commands: list[list[str]] = []
    removed_containers: list[str] = []

    class FinishedProcess:
        stdout = BytesIO(b"go version go1.26.9\n")

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 0

    def fake_popen(command: list[str], **_: object) -> FinishedProcess:
        observed_commands.append(command)
        return FinishedProcess()

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail(
            "toolchain query must use bounded streaming capture"
        ),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._force_remove_container",
        removed_containers.append,
    )

    assert (
        _container_tool_output(
            "example.invalid/performance@sha256:" + "a" * 64,
            ("go", "version"),
            environment={"GOTOOLCHAIN": "local", "HOME": CONTAINER_HOME},
        )
        == "go version go1.26.9"
    )

    command = observed_commands[0]
    assert command[:4] == [
        str(TIMEOUT_BINARY),
        "--foreground",
        "--kill-after=30s",
        "30s",
    ]
    command = command[4:]
    assert command[0:2] == [str(DOCKER_BINARY), "run"]
    assert "--rm" in command
    assert "--init" in command
    for option, value in (
        ("--memory", "6g"),
        ("--memory-swap", "6g"),
        ("--cpus", "2.0"),
        ("--pids-limit", "512"),
    ):
        assert command[command.index(option) + 1] == value
    assert command[command.index("--log-driver") + 1] == "local"
    assert [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--log-opt"
    ] == ["max-size=16m", "max-file=1", "compress=false"]
    assert "GOTOOLCHAIN=local" in command
    container_name = command[command.index("--name") + 1]
    assert removed_containers == [container_name]


def test_toolchain_query_rejects_a_timeout_and_removes_its_named_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stalled version query cannot outlive its host deadline or leak a container."""

    observed_commands: list[list[str]] = []
    removed_containers: list[str] = []

    class TimedOutProcess:
        stdout = BytesIO()

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 124

    def fake_popen(command: list[str], **_: object) -> TimedOutProcess:
        observed_commands.append(command)
        return TimedOutProcess()

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail(
            "toolchain query must use bounded streaming capture"
        ),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._force_remove_container",
        removed_containers.append,
    )

    with pytest.raises(CaptureError, match="query isolated toolchain failed"):
        _container_tool_output(
            "example.invalid/performance@sha256:" + "a" * 64,
            ("go", "version"),
            environment={"GOTOOLCHAIN": "local", "HOME": CONTAINER_HOME},
        )

    assert observed_commands[0][:4] == [
        str(TIMEOUT_BINARY),
        "--foreground",
        "--kill-after=30s",
        "30s",
    ]
    docker_command = observed_commands[0][4:]
    assert removed_containers == [docker_command[docker_command.index("--name") + 1]]


def test_toolchain_query_rejects_oversized_output_and_removes_its_named_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A version command cannot retain an unbounded response in host memory."""

    observed_commands: list[list[str]] = []
    removed_containers: list[str] = []
    terminated_processes: list[object] = []

    class OversizedProcess:
        stdout = BytesIO(b"123456789")

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 0

    def fake_popen(command: list[str], **_: object) -> OversizedProcess:
        observed_commands.append(command)
        return OversizedProcess()

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.MAX_OUTPUT_BYTES", 8
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail(
            "toolchain query must use bounded streaming capture"
        ),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._force_remove_container",
        removed_containers.append,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._terminate_capture_process",
        terminated_processes.append,
    )

    with pytest.raises(CaptureError, match="output exceeds"):
        _container_tool_output(
            "example.invalid/performance@sha256:" + "a" * 64,
            ("go", "version"),
            environment={"GOTOOLCHAIN": "local", "HOME": CONTAINER_HOME},
        )

    assert observed_commands[0][3] == "30s"
    docker_command = observed_commands[0][4:]
    assert terminated_processes
    assert removed_containers == [docker_command[docker_command.index("--name") + 1]]


def test_control_plane_timeout_becomes_a_capture_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stuck Docker API query has a finite client deadline and typed failure."""

    observed_timeouts: list[object] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed_timeouts.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )

    with pytest.raises(CaptureError, match="within 30 seconds"):
        _docker_server_version()

    assert observed_timeouts == [30]


@pytest.mark.parametrize(
    ("cleanup", "identifier", "expected_command"),
    [
        (
            _remove_volume,
            "quality-benchmark-cache-test",
            [
                str(DOCKER_BINARY),
                "volume",
                "rm",
                "--force",
                "quality-benchmark-cache-test",
            ],
        ),
        (
            _remove_image,
            "quality-performance-rust:test",
            [
                str(DOCKER_BINARY),
                "image",
                "rm",
                "--force",
                "quality-performance-rust:test",
            ],
        ),
    ],
)
def test_best_effort_cleanup_cannot_mask_a_timed_out_docker_client(
    monkeypatch: pytest.MonkeyPatch,
    cleanup: object,
    identifier: str,
    expected_command: list[str],
) -> None:
    """Failure to remove a disposable daemon object cannot mask the main result."""

    observed: list[tuple[list[str], object]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.append((command, kwargs.get("timeout")))
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )

    assert callable(cleanup)
    cleanup(identifier)

    assert observed == [(expected_command, 30)]


def test_cache_holder_is_non_networked_and_removed_before_its_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Holder lifecycle keeps cache mounts alive without leaking Docker state."""

    volume = "quality-benchmark-cache-holder"
    observed_start: list[list[str]] = []

    def fake_checked(command: tuple[str, ...] | list[str], _: str) -> SimpleNamespace:
        observed_start.append(list(command))
        return SimpleNamespace(returncode=0, stdout="a" * 64 + "\n", stderr="")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._run_checked", fake_checked
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._new_container_name",
        lambda: "quality-benchmark-" + "b" * 32,
    )
    holder = _start_cache_holder(
        image="example.invalid/performance@sha256:" + "a" * 64,
        cache_volume=volume,
        side="base",
    )
    assert holder == "quality-benchmark-" + "b" * 32
    assert observed_start[0][observed_start[0].index("--network") + 1] == "none"
    assert observed_start[0][observed_start[0].index("--detach") + 1].startswith(
        "example.invalid/"
    )

    cleanup: list[list[str]] = []
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._best_effort_docker_cleanup",
        cleanup.append,
    )
    _remove_volume(volume)
    assert cleanup == [
        [str(DOCKER_BINARY), "container", "rm", "--force", holder],
        [str(DOCKER_BINARY), "volume", "rm", "--force", volume],
    ]


@pytest.mark.parametrize(
    ("format_name", "expected_key", "expected_version", "environment_entry"),
    [
        ("go", "go", "go version go1.26.9", "GOTOOLCHAIN=local"),
        (
            "rust",
            "rustc",
            "rustc 1.94.1 (e408947bf 2026-03-25)",
            "RUSTUP_TOOLCHAIN=1.94.1",
        ),
    ],
)
def test_toolchain_report_records_the_effective_pinned_compiler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    format_name: str,
    expected_key: str,
    expected_version: str,
    environment_entry: str,
) -> None:
    """The report records the actual version queried under the pinned environment."""

    control_plane_commands: list[list[str]] = []
    capture_commands: list[list[str]] = []

    class FinishedProcess:
        stdout = BytesIO(f"{expected_version}\n".encode())

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 0

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        control_plane_commands.append(command)
        if command[1:2] == ["version"]:
            return SimpleNamespace(returncode=0, stdout="29.6.2\n", stderr="")
        if command[1:3] == ["image", "inspect"]:
            return SimpleNamespace(
                returncode=0, stdout="sha256:" + "b" * 64 + "\n", stderr=""
            )
        raise AssertionError(f"Unexpected Docker command: {command}")

    def fake_popen(command: list[str], **_: object) -> FinishedProcess:
        capture_commands.append(command)
        return FinishedProcess()

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._force_remove_container",
        lambda _name: None,
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.os.uname",
        lambda: SimpleNamespace(sysname="Linux", release="6.0", machine="x86_64"),
        raising=False,
    )

    trusted_go_benchmark = None
    if format_name == "go":
        overlay_path = tmp_path / "hub_bench_test.go"
        overlay_path.write_text("package hub\n", encoding="utf-8")
        trusted_go_benchmark = TrustedGoBenchmarkOverlay(
            path=overlay_path,
            commit=TRUSTED_GO_BENCHMARK_COMMIT,
            parent=TRUSTED_GO_BENCHMARK_PARENT,
            tree=TRUSTED_GO_BENCHMARK_TREE,
            blob=TRUSTED_GO_BENCHMARK_BLOB,
            sha256=TRUSTED_GO_BENCHMARK_SHA256,
            size_bytes=overlay_path.stat().st_size,
        )

    _write_toolchain(
        artifact_root=tmp_path,
        format_name=format_name,
        image="example.invalid/performance@sha256:" + "a" * 64,
        base_revision="a" * 40,
        rust_dockerfile=None,
        trusted_go_benchmark=trusted_go_benchmark,
    )

    report = json.loads((tmp_path / "toolchain.json").read_text(encoding="utf-8"))
    assert report[expected_key] == expected_version
    if trusted_go_benchmark is None:
        assert "trusted_go_benchmark_harness" not in report
    else:
        assert report["trusted_go_benchmark_harness"] == {
            "applied_sides": ["base", "candidate"],
            "commit": TRUSTED_GO_BENCHMARK_COMMIT,
            "parent": TRUSTED_GO_BENCHMARK_PARENT,
            "tree": TRUSTED_GO_BENCHMARK_TREE,
            "path": TRUSTED_GO_BENCHMARK_PATH,
            "blob": TRUSTED_GO_BENCHMARK_BLOB,
            "sha256": TRUSTED_GO_BENCHMARK_SHA256,
            "size_bytes": trusted_go_benchmark.size_bytes,
            "mount": "read-only overlay for warm and measurement containers",
        }
    run_command = capture_commands[0][4:]
    assert run_command[0:2] == [str(DOCKER_BINARY), "run"]
    assert environment_entry in run_command
    assert [
        run_command[index + 1]
        for index, value in enumerate(run_command)
        if value == "--log-opt"
    ] == ["max-size=16m", "max-file=1", "compress=false"]


def test_cleanup_failure_cannot_leave_github_command_parsing_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The stop-command marker is always closed, even when daemon cleanup fails."""

    class FinishedProcess:
        stdout = BytesIO()

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 0

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )

    def cleanup_failure(_: str) -> None:
        raise CaptureError("simulated daemon cleanup failure")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._force_remove_container",
        cleanup_failure,
    )
    container_name = "quality-benchmark-" + "c" * 32

    with pytest.raises(CaptureError, match="simulated daemon cleanup failure"):
        _safe_capture(
            ("docker", "run", "example"),
            tmp_path / "capture.txt",
            description="test capture",
            timeout_seconds=1,
            container_name=container_name,
        )

    marker_lines = capsys.readouterr().out.splitlines()
    assert marker_lines[0].startswith("::stop-commands::")
    marker = marker_lines[0].removeprefix("::stop-commands::")
    assert marker_lines[-1] == f"::{marker}::"


def test_safe_capture_can_suppress_nested_github_command_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Parallel workers keep their captured output out of the command stream."""

    class FinishedProcess:
        stdout = BytesIO()

        def poll(self) -> int:
            return 0

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen",
        lambda *_args, **_kwargs: FinishedProcess(),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._force_remove_container",
        lambda _container_name: None,
    )
    output_path = tmp_path / "capture.txt"

    _safe_capture(
        ("docker", "run", "example"),
        output_path,
        description="parallel worker capture",
        timeout_seconds=1,
        container_name="quality-benchmark-" + "e" * 32,
        emit_markers=False,
    )

    assert capsys.readouterr().out == ""
    assert output_path.read_bytes() == b""


def test_base_exception_cleanup_paths_have_required_audit_rationales() -> None:
    """Broad cleanup catches stay reviewable because they re-raise after cleanup."""

    source = (
        REPOSITORY_ROOT / "scripts" / "quality" / "capture_isolated_benchmarks.py"
    ).read_text(encoding="utf-8")
    assert source.count("BaseException") == 2
    assert source.count("# RZ-22-01-JUSTIFIED:") == 2


def test_artifact_root_must_be_a_fresh_host_only_runner_temp_directory(
    tmp_path: Path,
) -> None:
    """A candidate checkout must never choose a symlinkable evidence path."""

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()

    with pytest.raises(CaptureError, match="under the trusted runner temp"):
        prepare_artifact_root(candidate_root / "artifacts", runner_temp)

    artifact_root = runner_temp / "performance-evidence"
    assert prepare_artifact_root(artifact_root, runner_temp) == artifact_root
    assert artifact_root.is_dir()

    with pytest.raises(CaptureError, match="must not already exist"):
        prepare_artifact_root(artifact_root, runner_temp)


def test_build_rust_image_removes_the_deterministic_tag_after_a_build_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed build cannot leave a tag that later capture could accidentally reuse."""

    base_worktree = tmp_path / "base"
    dockerfile = (
        base_worktree / "containers" / "quality" / "Dockerfile.performance-rust"
    )
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    removed_images: list[str] = []

    def fail_build(*_args: object, **_kwargs: object) -> None:
        raise CaptureError("simulated build failure")

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._safe_capture", fail_build
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._remove_image",
        removed_images.append,
    )

    with pytest.raises(CaptureError, match="simulated build failure"):
        _build_rust_image(
            dockerfile=dockerfile,
            base_worktree=base_worktree,
            runner_temp=runner_temp,
            artifact_root=artifact_root,
            base_revision="a" * 40,
        )

    assert removed_images == ["quality-performance-rust:" + "a" * 12]


def test_build_rust_image_uses_a_fresh_dockerfile_only_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The Docker daemon receives neither base nor candidate source as context."""

    base_worktree = tmp_path / "base"
    dockerfile = (
        base_worktree / "containers" / "quality" / "Dockerfile.performance-rust"
    )
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    candidate_worktree = tmp_path / "candidate"
    candidate_worktree.mkdir()
    (candidate_worktree / "candidate-only.txt").write_text(
        "untrusted\n", encoding="utf-8"
    )
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    observed_commands: list[list[str]] = []

    class FinishedProcess:
        stdout = BytesIO(b"trusted image build\n")

        def poll(self) -> int:
            return 0

        def wait(self, *, timeout: int | None = None) -> int:
            del timeout
            return 0

    def fake_popen(command: list[str], **_: object) -> FinishedProcess:
        docker_index = command.index(str(DOCKER_BINARY))
        docker_command = command[docker_index:]
        observed_commands.append(docker_command)
        dockerfile_index = docker_command.index("--file") + 1
        build_context = Path(docker_command[-1])

        assert docker_command[:2] == [str(DOCKER_BINARY), "build"]
        assert "--pull" in docker_command
        assert build_context.is_dir()
        assert Path(docker_command[dockerfile_index]).parent == build_context
        assert {entry.name for entry in build_context.iterdir()} == {"Dockerfile"}
        assert (
            Path(docker_command[dockerfile_index]).read_bytes()
            == dockerfile.read_bytes()
        )
        assert str(base_worktree) not in docker_command
        assert str(candidate_worktree) not in docker_command
        return FinishedProcess()

    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks.subprocess.Popen", fake_popen
    )

    image = _build_rust_image(
        dockerfile=dockerfile,
        base_worktree=base_worktree,
        runner_temp=runner_temp,
        artifact_root=artifact_root,
        base_revision="a" * 40,
    )

    assert image == "quality-performance-rust:" + "a" * 12
    assert observed_commands[0][0:2] == [str(DOCKER_BINARY), "build"]
    assert (
        artifact_root / "build-rust-image.log"
    ).read_bytes() == b"trusted image build\n"


def test_rust_benchmark_image_cannot_copy_candidate_build_context() -> None:
    """The trusted image must be reproducible without candidate-controlled files."""

    dockerfile = (
        REPOSITORY_ROOT / "containers" / "quality" / "Dockerfile.performance-rust"
    )
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    instructions = [
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    python_image = (
        "python:3.14-slim-bookworm@"
        "sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52"
    )
    rust_image = (
        "rust:1.94.1-slim-bookworm@"
        "sha256:cf9dd0ec73e75f827fe59123fff9dc65af1a1c8363c3c31ee8d7f8ad0b6a5fb2"
    )
    copy_lines = [
        line for line in instructions if line.split(maxsplit=1)[0].upper() == "COPY"
    ]

    assert any("#checkov:skip=CKV_DOCKER_2" in line for line in lines)
    assert [line for line in instructions if line.startswith("FROM ")] == [
        f"FROM {python_image}"
    ]
    assert not any(line.split(maxsplit=1)[0].upper() == "ADD" for line in instructions)
    assert copy_lines == [
        f"COPY --from={rust_image} /usr/local/rustup /usr/local/rustup",
        f"COPY --from={rust_image} /usr/local/cargo /usr/local/cargo",
    ]
    assert "USER benchmark" in lines


def test_disposable_test_runner_provides_the_pinned_benchmark_compiler() -> None:
    """The maintained full Python runner must execute its real Go contracts."""
    dockerfile = (REPOSITORY_ROOT / "Dockerfile.test").read_text(encoding="utf-8")
    assert f"COPY --from={GO_IMAGE} /usr/local/go /usr/local/go" in dockerfile
    assert 'GOTOOLCHAIN="local"' in dockerfile
    assert 'PATH="/usr/local/go/bin:$PATH"' in dockerfile


def test_go_measurement_isolates_benchmarks_without_losing_coverage(
    tmp_path: Path,
) -> None:
    """A retained fixture cannot affect later benchmarks in either package."""

    assert shutil.which("go") is not None, (
        "Go is required for the real benchmark-process contract"
    )
    (tmp_path / "go.mod").write_text("module example.test/isolation\n\ngo 1.20\n")
    fixture = """package isolation

import "testing"

var retained bool
var counter uint64

func BenchmarkRetainsFixture(b *testing.B) {
    retained = true
    for i := 0; i < b.N; i++ { counter++ }
}

func BenchmarkChecksFreshProcess(b *testing.B) {
    if retained { b.Fatal("previous benchmark fixture leaked into this process") }
    b.Run("nested", func(b *testing.B) {
        for i := 0; i < b.N; i++ { counter++ }
    })
}
"""
    (tmp_path / "isolation_test.go").write_text(fixture)
    other_package = tmp_path / "other"
    other_package.mkdir()
    (other_package / "isolation_test.go").write_text(fixture)
    environment = {
        **os.environ,
        "GOWORK": "off",
        "GOTOOLCHAIN": "local",
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "GOCACHE": os.environ.get("GOCACHE", str(tmp_path / "go-build")),
        "GOPATH": os.environ.get("GOPATH", str(tmp_path / "go-path")),
    }

    result = subprocess.run(  # noqa: S603 - fixed runner command and local test fixtures
        _go_program(),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    records = re.findall(
        r"^(Benchmark\S+)\s+\d+\s+.*ns/op.*B/op.*allocs/op$",
        result.stdout,
        re.MULTILINE,
    )
    assert len(records) == 4, result.stdout
    assert sum(name.startswith("BenchmarkRetainsFixture-") for name in records) == 2
    assert (
        sum(name.startswith("BenchmarkChecksFreshProcess/nested-") for name in records)
        == 2
    )
    assert "pkg: example.test/isolation\n" in result.stdout
    assert "pkg: example.test/isolation/other\n" in result.stdout


@pytest.mark.parametrize("phase", ["discovery", "measurement"])
def test_go_measurement_stops_on_discovery_or_benchmark_failure(
    tmp_path: Path, phase: str
) -> None:
    """A failed package discovery or benchmark cannot become partial evidence."""

    assert shutil.which("go") is not None, (
        "Go is required for the real benchmark-process contract"
    )
    (tmp_path / "go.mod").write_text("module example.test/failure\n\ngo 1.20\n")
    (tmp_path / "failure_test.go").write_text(
        """package failure

import (
    "flag"
    "fmt"
    "os"
    "testing"
)

func TestMain(m *testing.M) {
    flag.Parse()
    if os.Getenv("FAILURE_PHASE") == "discovery" && flag.Lookup("test.list").Value.String() != "" {
        fmt.Println("intentional discovery failure")
        os.Exit(23)
    }
    os.Exit(m.Run())
}

func BenchmarkFails(b *testing.B) {
    if os.Getenv("FAILURE_PHASE") == "measurement" {
        b.Fatal("intentional measurement failure")
    }
}

func BenchmarkMustNotRun(b *testing.B) {
    fmt.Println("later benchmark executed after failure")
}
"""
    )
    result = subprocess.run(  # noqa: S603 - fixed runner command and local test fixtures
        _go_program(),
        cwd=tmp_path,
        env={
            **os.environ,
            "GOWORK": "off",
            "GOTOOLCHAIN": "local",
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "FAILURE_PHASE": phase,
            "GOCACHE": os.environ.get("GOCACHE", str(tmp_path / "go-build")),
            "GOPATH": os.environ.get("GOPATH", str(tmp_path / "go-path")),
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert f"intentional {phase} failure" in result.stdout + result.stderr
    assert "later benchmark executed after failure" not in result.stdout
