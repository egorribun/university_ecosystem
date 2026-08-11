import json
import subprocess
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality.capture_isolated_benchmarks import (
    CONTAINER_HOME,
    DOCKER_BINARY,
    TIMEOUT_BINARY,
    CaptureArguments,
    CaptureError,
    _build_rust_image,
    _container_tool_output,
    _copy_limited_stream,
    _create_private_volume,
    _docker_server_version,
    _force_remove_container,
    _go_environment,
    _go_prefetch_environment,
    _remove_image,
    _remove_volume,
    _rust_environment,
    _rust_prefetch_program,
    _safe_capture,
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
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._capture_pair",
        lambda **kwargs: captured_descriptions.append(kwargs["description"]),
    )
    monkeypatch.setattr(
        "scripts.quality.capture_isolated_benchmarks._write_toolchain",
        lambda **_kwargs: None,
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
    assert captured_descriptions == [
        "warm base benchmark build",
        "warm candidate benchmark build",
        *[
            f"capture {side} benchmark pair {pair:02d}"
            for pair in range(1, 13)
            for side in (("base", "candidate") if pair % 2 else ("candidate", "base"))
        ],
    ]


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
        stdout = BytesIO(b"go version go1.26.5\n")

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
        == "go version go1.26.5"
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


@pytest.mark.parametrize(
    ("format_name", "expected_key", "expected_version", "environment_entry"),
    [
        ("go", "go", "go version go1.26.5", "GOTOOLCHAIN=local"),
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

    _write_toolchain(
        artifact_root=tmp_path,
        format_name=format_name,
        image="example.invalid/performance@sha256:" + "a" * 64,
        base_revision="a" * 40,
        rust_dockerfile=None,
    )

    report = json.loads((tmp_path / "toolchain.json").read_text(encoding="utf-8"))
    assert report[expected_key] == expected_version
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
