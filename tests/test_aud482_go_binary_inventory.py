"""AUD-482 evidence must describe the binaries, not their download logs."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = ROOT / "scripts/ci/inventory_go_binaries.py"
WINDOWS = pytest.mark.skipif(
    os.name != "nt", reason="AUD-482 build lifecycle is supported only on Windows"
)


def load_producer() -> ModuleType:
    assert PRODUCER.is_file(), "AUD-482 binary inventory producer is missing"
    spec = importlib.util.spec_from_file_location("aud482_inventory", PRODUCER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def go_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile a real binary containing a versioned module replaced locally."""
    root = tmp_path_factory.mktemp("aud482-go")
    replacement = root / "replacement"
    replacement.mkdir()
    (root / "go.mod").write_text(
        "module example.test/main\n\n"
        "go 1.26.10\n\n"
        "require example.test/dependency v1.2.3\n"
        "replace example.test/dependency => ./replacement\n",
        encoding="utf-8",
    )
    (replacement / "go.mod").write_text(
        "module example.test/dependency\n\ngo 1.26.10\n", encoding="utf-8"
    )
    (replacement / "lib.go").write_text(
        'package dependency\nfunc Message() string { return "linked" }\n',
        encoding="utf-8",
    )
    (root / "main.go").write_text(
        'package main\nimport ("fmt"; "example.test/dependency")\n'
        "func main() { fmt.Println(dependency.Message()) }\n",
        encoding="utf-8",
    )
    binary = root / "fixture.exe"
    env = {
        **os.environ,
        "GOTOOLCHAIN": "go1.26.10",
        "GOWORK": "off",
        "GOPROXY": "off",
        "GOMAXPROCS": "2",
        "GOFLAGS": "-p=2",
    }

    async def compile_fixture() -> None:
        process = await asyncio.create_subprocess_exec(
            "go",
            "build",
            "-trimpath",
            "-o",
            str(binary),
            ".",
            cwd=root,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, error = await process.communicate()
        assert process.returncode == 0, error.decode("utf-8")

    asyncio.run(compile_fixture())
    return binary


@WINDOWS
def test_inventory_reads_real_binary_and_its_linked_replacement(
    go_binary: Path,
) -> None:
    inventory = load_producer().inspect_binary(go_binary)
    assert inventory["sha256"] == hashlib.sha256(go_binary.read_bytes()).hexdigest()
    assert inventory["go_version"] == "go1.26.10"
    assert inventory["path"] == "example.test/main"
    assert inventory["main"]["path"] == "example.test/main"
    dependency = next(
        item
        for item in inventory["dependencies"]
        if item["path"] == "example.test/dependency"
    )
    assert dependency["version"] == "v1.2.3"
    assert dependency["replacement"]["path"] == "./replacement"
    assert dependency["replacement"]["version"] == "(devel)"


def test_versioned_replacement_is_distinct_from_original_module() -> None:
    producer = load_producer()
    output = (
        "/binary: go1.26.10\n"
        "\tpath\texample.test/main\n"
        "\tmod\texample.test/main\tv1.0.0\th1:main\n"
        "\tdep\tgithub.com/go-jose/go-jose/v4\tv4.1.5\th1:old\n"
        "\t=>\tgithub.com/go-jose/go-jose/v4\tv4.1.6\th1:new\n"
        "\tdep\tgithub.com/go-jose/go-jose/v3\tv3.0.5\th1:v3\n"
        "\tbuild\tGOOS=linux\n"
        "\tbuild\tGOARCH=amd64\n"
    )
    result = producer.parse_build_info(output)
    assert result["dependencies"] == [
        {
            "path": "github.com/go-jose/go-jose/v4",
            "version": "v4.1.5",
            "sum": "h1:old",
            "replacement": {
                "path": "github.com/go-jose/go-jose/v4",
                "version": "v4.1.6",
                "sum": "h1:new",
            },
        },
        {
            "path": "github.com/go-jose/go-jose/v3",
            "version": "v3.0.5",
            "sum": "h1:v3",
            "replacement": None,
        },
    ]
    assert result["platform"] == {"goos": "linux", "goarch": "amd64"}


@pytest.mark.parametrize(
    "output",
    [
        "",
        "not a Go binary\n",
        "/binary: go1.26.10\n\tpath\tmain\n",
        "/binary: go1.26.10\n\tpath\tmain\n\t=>\tbad\tv1.0.0\n",
        "/binary: go1.26.10\n\tpath\tmain\n\tmod\tmain\t(devel)\n"
        "\tdep\texample.test/missing-version\n",
        "/binary: go1.26.10\n\tpath\tmain\n\tmod\tmain\t(devel)\n"
        "\tdep\texample.test/duplicate\tv1.0.0\n"
        "\tdep\texample.test/duplicate\tv1.0.0\n",
        "/binary: go1.26.10\n\tpath\tmain\n\tmod\tmain\t(devel)\n"
        "\tbuild\tGOOS=linux\n\tbuild\tGOOS=windows\n",
    ],
)
def test_rejects_missing_or_malformed_binary_metadata(output: str) -> None:
    producer = load_producer()
    with pytest.raises(producer.InventoryError):
        producer.parse_build_info(output)


@WINDOWS
def test_rejects_non_go_binary(tmp_path: Path) -> None:
    producer = load_producer()
    binary = tmp_path / "not-a-go-binary"
    binary.write_bytes(b"not an executable")
    with pytest.raises(producer.InventoryError):
        producer.inspect_binary(binary)


def test_missing_binary_fails_closed(tmp_path: Path) -> None:
    producer = load_producer()
    with pytest.raises(producer.InventoryError, match="Cannot read"):
        producer.inspect_binary(tmp_path / "missing")


@WINDOWS
def test_rejects_symbolic_link_even_when_target_is_a_valid_go_binary(
    go_binary: Path, tmp_path: Path
) -> None:
    producer = load_producer()
    link = tmp_path / "external-binary-link"
    link.symlink_to(go_binary)
    with pytest.raises(producer.InventoryError, match="regular file"):
        producer.inspect_binary(link)


def test_rejects_regular_looking_windows_reparse_point() -> None:
    producer = load_producer()

    class ReparseFile:
        def lstat(self) -> SimpleNamespace:
            return SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400)

    with pytest.raises(producer.InventoryError, match="regular file"):
        producer._require_regular_binary(ReparseFile())


@WINDOWS
def test_checks_binary_hash_before_and_after_reading_metadata(
    go_binary: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    binary = tmp_path / "changing.exe"
    shutil.copyfile(go_binary, binary)
    real_run = producer._run

    def mutate_after_read(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        result = real_run(command, **kwargs)
        binary.write_bytes(binary.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(producer, "_run", mutate_after_read)
    with pytest.raises(producer.InventoryError, match="changed"):
        producer.inspect_binary(binary)


@WINDOWS
@pytest.mark.parametrize("moment", ["before", "during"])
def test_rejects_producer_source_changed_before_or_during_inventory(
    moment: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / "producer.py"
    shutil.copyfile(PRODUCER, copied)
    spec = importlib.util.spec_from_file_location("copied_aud482", copied)
    assert spec is not None and spec.loader is not None
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    revision = "a" * 40
    if moment == "before":
        copied.write_bytes(copied.read_bytes() + b"\n# modified\n")

    def fake_git(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, 0, revision, "")

    def fake_build(*_args: object) -> dict[str, object]:
        if moment == "during":
            copied.write_bytes(copied.read_bytes() + b"\n# modified\n")
        return {"binary": {"dependencies": [{}]}}

    monkeypatch.setattr(producer, "_run", fake_git)
    monkeypatch.setattr(producer, "_build_artifact", fake_build)
    with pytest.raises(producer.InventoryError, match=r"producer.*changed"):
        producer.build_inventory(tmp_path, revision, tmp_path)


def test_producer_identity_check_rejects_unexpected_loaded_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producer = load_producer()
    monkeypatch.setattr(producer, "_LOADED_PRODUCER_SHA256", "0" * 64)
    with pytest.raises(producer.InventoryError, match="source changed"):
        producer._check_producer_identity()


@WINDOWS
@pytest.mark.parametrize("failure", ["create", "configure", "assign", "collision"])
def test_windows_job_setup_fails_closed_before_starting_command(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()

    class FakeFunction:
        def __init__(self, result: int) -> None:
            self.result = result

        def __call__(self, *_args: object) -> int:
            return self.result

    class FakeKernel:
        CreateJobObjectW = FakeFunction(0 if failure == "create" else 1)
        SetInformationJobObject = FakeFunction(0 if failure == "configure" else 1)
        GetCurrentProcess = FakeFunction(1)
        AssignProcessToJobObject = FakeFunction(0 if failure == "assign" else 1)
        CloseHandle = FakeFunction(1)

    monkeypatch.setattr(
        ctypes, "WinDLL", lambda *_args, **_kwargs: FakeKernel(), raising=False
    )
    monkeypatch.setattr(
        ctypes, "get_last_error", lambda: 183 if failure == "collision" else 0
    )
    with pytest.raises(OSError, match=r"[Pp]rocess job|supervisor"):
        job = producer._setup_windows_job("owned-job")
        if failure == "assign":

            class Transport:
                def get_extra_info(self, _name: str) -> object:
                    return type("Native", (), {"_handle": 1})()

            process = type("Process", (), {"_transport": Transport()})()
            producer._assign_windows_job(job, process)


@WINDOWS
def test_missing_supervisor_native_handle_fails_closed() -> None:
    producer = load_producer()

    class Transport:
        def get_extra_info(self, _name: str) -> None:
            return None

    process = SimpleNamespace(_transport=Transport())
    with pytest.raises(OSError, match="process handle"):
        producer._assign_windows_job(1, process)


@WINDOWS
def test_failed_job_close_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    producer = load_producer()

    class FakeFunction:
        def __call__(self, *_args: object) -> int:
            return 0

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: SimpleNamespace(CloseHandle=FakeFunction()),
    )
    with pytest.raises(OSError, match="close owned"):
        producer._close_windows_job(1)


@WINDOWS
@pytest.mark.parametrize("failure", ["open", "verify", "timeout"])
def test_supervisor_will_not_start_target_without_verified_job(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()

    class FakeFunction:
        def __init__(self, result: int) -> None:
            self.result = result

        def __call__(self, *_args: object) -> int:
            return self.result

    class FakeKernel:
        OpenJobObjectW = FakeFunction(0 if failure == "open" else 1)
        GetCurrentProcess = FakeFunction(1)
        IsProcessInJob = FakeFunction(0 if failure == "verify" else 1)
        CloseHandle = FakeFunction(1)

    clock = iter((0.0, 1.0, 11.0))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: FakeKernel())
    monkeypatch.setattr(
        producer,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _seconds: None),
    )
    with pytest.raises(OSError, match="job"):
        producer._supervise(
            "unassigned-job", [sys.executable, "-c", "raise SystemExit(0)"]
        )


@WINDOWS
def test_failed_job_assignment_never_starts_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    target = tmp_path / "should-not-exist"

    def reject(*_args: object) -> None:
        raise OSError("assignment failed")

    monkeypatch.setattr(producer, "_assign_windows_job", reject)
    with pytest.raises(producer.InventoryError):
        producer._run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path(__import__('sys').argv[1]).touch()",
                str(target),
            ]
        )
    assert not target.exists()


@WINDOWS
def test_build_inventory_binds_archive_image_and_final_binary(
    go_binary: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fake Docker I/O, but read a real commit archive and real Go binary."""
    producer = load_producer()
    revision = producer._run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    expected_tree = producer._run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT
    ).stdout.strip()
    real_run = producer._run
    images = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
    archives: list[tuple[bytes, list[str], bytes]] = []
    removed: list[str] = []
    identity: dict[str, str] = {}

    def fake_docker(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        if args[1] == "build":
            archive = kwargs["stdin"].read()
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                names = tar.getnames()
                dockerfile = (
                    "Dockerfile"
                    if not archives
                    else "services/file-processor/Dockerfile"
                )
                member = tar.extractfile(dockerfile)
                assert member is not None
                dockerfile_content = member.read()
            archives.append((archive, names, dockerfile_content))
            iidfile = Path(args[args.index("--iidfile") + 1])
            iidfile.write_text(images[len(archives) - 1] + "\n", encoding="utf-8")
            assert f"org.opencontainers.image.revision={revision}" in args
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "create":
            identity["name"] = args[args.index("--name") + 1]
            identity["owner"] = args[args.index("--label") + 1].split("=", 1)[1]
            identity["image"] = args[-1]
            return subprocess.CompletedProcess(args, 0, "a" * 64 + "\n", "")
        if args[1] == "inspect":
            output = f"{'a' * 64}|{identity['image']}|/{identity['name']}|{identity['owner']}"
            return subprocess.CompletedProcess(args, 0, output, "")
        if args[1] == "cp":
            shutil.copyfile(go_binary, Path(args[-1]))
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "rm":
            removed.append(args[-1])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(producer, "_run", fake_docker)
    work = tmp_path / "work"
    work.mkdir()
    report = producer.build_inventory(ROOT, revision, work)
    assert report["source"]["revision"] == revision
    assert report["source"]["tree"] == expected_tree
    assert len(archives) == 2
    assert "Dockerfile" in archives[0][1]
    assert "services/file-processor/Dockerfile" in archives[1][1]
    for archive, path in zip(
        archives,
        ("services/caddy/Dockerfile", "services/file-processor/Dockerfile"),
        strict=True,
    ):
        expected = real_run(["git", "show", f"{revision}:{path}"], cwd=ROOT).stdout
        assert archive[2] == expected.encode("utf-8")
    assert (
        report["artifacts"]["caddy"]["context_sha256"]
        == hashlib.sha256(archives[0][0]).hexdigest()
    )
    assert (
        report["artifacts"]["probe"]["context_sha256"]
        == hashlib.sha256(archives[1][0]).hexdigest()
    )
    for name, image, runtime_path in (
        ("caddy", images[0], "/usr/bin/caddy"),
        ("probe", images[1], "/usr/local/bin/grpc_health_probe"),
    ):
        artifact = report["artifacts"][name]
        assert artifact["image_config_id"] == image
        assert artifact["runtime_path"] == runtime_path
        assert (
            artifact["binary"]["sha256"]
            == hashlib.sha256(go_binary.read_bytes()).hexdigest()
        )
        assert artifact["binary"]["dependencies"][0]["replacement"]["path"] == (
            "./replacement"
        )
    assert removed == ["a" * 64, "a" * 64]


@WINDOWS
def test_rejects_symbolic_source_revision(tmp_path: Path) -> None:
    producer = load_producer()
    with pytest.raises(producer.InventoryError, match="full"):
        producer.build_inventory(ROOT, "HEAD", tmp_path)


def test_unverified_posix_build_is_rejected_before_any_process_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    monkeypatch.setattr(producer, "_IS_WINDOWS", False)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unverified platform must not start a process")

    monkeypatch.setattr(producer, "_run", forbidden)
    with pytest.raises(producer.InventoryError, match=r"POSIX.*not been verified"):
        producer.build_inventory(ROOT, "a" * 40, tmp_path)


@WINDOWS
@pytest.mark.parametrize("bad", ["commit", "tree"])
def test_rejects_inconsistent_source_identity(
    bad: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    revision = "a" * 40

    def inconsistent(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        output = revision if bad == "tree" and "--verify" in args else "wrong"
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(producer, "_run", inconsistent)
    with pytest.raises(producer.InventoryError, match=r"Revision|tree"):
        producer.build_inventory(ROOT, revision, tmp_path)


def test_process_timeout_and_missing_executable_fail_closed() -> None:
    producer = load_producer()
    with pytest.raises(producer.InventoryError, match="failed"):
        producer._run(["aud482-executable-does-not-exist", "arg"])
    with pytest.raises(producer.InventoryError, match="failed"):
        producer._run(
            [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.01
        )


@WINDOWS
def test_timed_out_owned_process_does_not_leave_its_child_running(
    tmp_path: Path,
) -> None:
    producer = load_producer()
    child = tmp_path / "child.py"
    parent = tmp_path / "parent.py"
    child.write_text(
        "from pathlib import Path\nimport sys, time\n"
        "root = Path(sys.argv[1])\n(root / 'ready').write_text('ready')\n"
        "time.sleep(1.5)\n(root / 'finished').write_text('still running')\n",
        encoding="utf-8",
    )
    parent.write_text(
        "from pathlib import Path\nimport subprocess, sys, time\n"
        "root = Path(sys.argv[1])\n"
        "subprocess.Popen([sys.executable, str(root / 'child.py'), str(root)])\n"
        "while not (root / 'ready').exists(): time.sleep(0.01)\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )
    with pytest.raises(producer.InventoryError):
        producer._run([sys.executable, str(parent), str(tmp_path)], timeout=0.7)
    assert (tmp_path / "ready").exists()
    time.sleep(1.6)
    assert not (tmp_path / "finished").exists()


@WINDOWS
def test_terminated_producer_does_not_leave_its_owned_descendants(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child.py"
    runner = tmp_path / "runner.py"
    child.write_text(
        "from pathlib import Path\nimport sys, time\n"
        "root = Path(sys.argv[1])\n(root / 'ready').write_text('ready')\n"
        "time.sleep(1.5)\n(root / 'finished').write_text('still running')\n",
        encoding="utf-8",
    )
    runner.write_text(
        "import importlib.util, sys\nfrom pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location('producer', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "root = Path(sys.argv[2])\n"
        "module._run([sys.executable, str(root / 'child.py'), str(root)], timeout=10)\n",
        encoding="utf-8",
    )

    async def exercise() -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(runner),
            str(PRODUCER),
            str(tmp_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        deadline = asyncio.get_running_loop().time() + 5
        try:
            while not (tmp_path / "ready").exists():
                assert process.returncode is None
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        await asyncio.sleep(1.6)
        assert not (tmp_path / "finished").exists()

    asyncio.run(exercise())


def test_does_not_kill_an_already_reaped_process_on_output_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producer = load_producer()

    class AlreadyReaped:
        returncode = 0

        async def communicate(self) -> None:
            raise OSError("output read failed")

        def kill(self) -> None:
            raise AssertionError("a reaped process must not be killed")

    async def spawn(*_args: object, **_kwargs: object) -> AlreadyReaped:
        return AlreadyReaped()

    monkeypatch.setattr(producer, "_setup_windows_job", lambda _name: 1)
    monkeypatch.setattr(producer, "_assign_windows_job", lambda *_args: None)
    monkeypatch.setattr(producer, "_close_windows_job", lambda _job: None)
    monkeypatch.setattr(producer.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(producer.InventoryError, match="failed"):
        producer._run(["git", "version"])


def test_posix_timeout_targets_only_its_owned_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producer = load_producer()
    monkeypatch.setattr(producer, "_IS_WINDOWS", False)
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        producer.os, "killpg", lambda pid, sig: calls.append((pid, sig)), raising=False
    )
    monkeypatch.setattr(producer.signal, "SIGKILL", 9, raising=False)

    class TimedOut:
        returncode = None
        pid = 12345
        calls = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError
            return b"", b""

    async def spawn(*_args: object, **kwargs: object) -> TimedOut:
        assert kwargs["start_new_session"] is True
        return TimedOut()

    monkeypatch.setattr(producer.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(producer.InventoryError):
        producer._run(["git", "version"])
    assert calls == [(12345, 9)]


def test_non_windows_supervisor_forwards_exit_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producer = load_producer()
    monkeypatch.setattr(producer, "_IS_WINDOWS", False)
    assert producer._supervise("", [sys.executable, "-c", "raise SystemExit(7)"]) == 7


@WINDOWS
@pytest.mark.parametrize("failure", ["image", "container", "copy", "modules"])
def test_build_rejects_incomplete_artifacts_and_cleans_owned_container(
    failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    real_run = producer._run
    revision = real_run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    removed: list[str] = []
    identity: dict[str, str] = {}

    def failing_docker(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        if args[1] == "build":
            image_id = "wrong" if failure == "image" else "sha256:" + "1" * 64
            Path(args[args.index("--iidfile") + 1]).write_text(
                image_id, encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "create":
            container_id = "wrong" if failure == "container" else "a" * 64
            identity["name"] = args[args.index("--name") + 1]
            identity["owner"] = args[args.index("--label") + 1].split("=", 1)[1]
            identity["image"] = args[-1]
            return subprocess.CompletedProcess(args, 0, container_id, "")
        if args[1] == "inspect":
            output = f"{'a' * 64}|{identity['image']}|/{identity['name']}|{identity['owner']}"
            return subprocess.CompletedProcess(args, 0, output, "")
        if args[1] == "cp":
            if failure == "copy":
                raise producer.InventoryError("docker cp failed")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "rm":
            removed.append(args[-1])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(producer, "_run", failing_docker)
    monkeypatch.setattr(producer, "inspect_binary", lambda _: {"dependencies": []})
    with pytest.raises(producer.InventoryError):
        producer.build_inventory(ROOT, revision, tmp_path)
    assert removed == (["a" * 64] if failure in ("copy", "modules") else [])


@WINDOWS
def test_rejects_build_context_changed_during_build(
    go_binary: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    real_run = producer._run
    revision = real_run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()

    def changing_build(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        if args[1] == "build":
            context = Path(kwargs["stdin"].name)
            context.write_bytes(context.read_bytes() + b"tampered")
            Path(args[args.index("--iidfile") + 1]).write_text(
                "sha256:" + "1" * 64, encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "create":
            return subprocess.CompletedProcess(args, 0, "a" * 64, "")
        if args[1] == "cp":
            shutil.copyfile(go_binary, Path(args[-1]))
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "rm":
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(producer, "_run", changing_build)
    with pytest.raises(producer.InventoryError, match="context changed"):
        producer.build_inventory(ROOT, revision, tmp_path)


@WINDOWS
def test_lost_create_response_leaves_owned_recovery_receipt_without_blind_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    real_run = producer._run
    revision = real_run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    commands: list[list[str]] = []

    def timeout_after_create(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        commands.append(args)
        if args[1] == "build":
            Path(args[args.index("--iidfile") + 1]).write_text(
                "sha256:" + "1" * 64, encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "create":
            raise producer.InventoryError("response lost after daemon accepted request")
        raise AssertionError("an unknown container must not be blindly removed")

    monkeypatch.setattr(producer, "_run", timeout_after_create)
    with pytest.raises(producer.InventoryError, match="uncertain"):
        producer.build_inventory(ROOT, revision, tmp_path)
    create = next(command for command in commands if command[1] == "create")
    receipt = json.loads((tmp_path / "caddy.container-intent.json").read_text())
    assert receipt["name"] == create[create.index("--name") + 1]
    assert receipt["ownership_label"] == create[create.index("--label") + 1]
    assert receipt["image_config_id"] == "sha256:" + "1" * 64
    assert not any(command[1] == "rm" for command in commands)


@WINDOWS
def test_interrupted_build_reports_unresolved_daemon_state_and_keeps_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    real_run = producer._run
    revision = real_run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    commands: list[list[str]] = []

    def interrupted(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        commands.append(args)
        raise producer.InventoryError("build client exited before daemon response")

    monkeypatch.setattr(producer, "_run", interrupted)
    with pytest.raises(producer.InventoryError, match=r"daemon.*unresolved"):
        producer.build_inventory(ROOT, revision, tmp_path)
    receipt = json.loads((tmp_path / "caddy.build-intent.json").read_text())
    assert receipt["source_revision"] == revision
    assert (
        receipt["context_sha256"]
        == hashlib.sha256((tmp_path / "caddy.context.tar").read_bytes()).hexdigest()
    )
    assert receipt["build_label"] in commands[0]
    assert all(command[1] != "create" for command in commands)


@WINDOWS
def test_container_identity_mismatch_is_never_copied_or_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    real_run = producer._run
    revision = real_run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    commands: list[list[str]] = []

    def impostor(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        commands.append(args)
        if args[1] == "build":
            Path(args[args.index("--iidfile") + 1]).write_text(
                "sha256:" + "1" * 64, encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "create":
            return subprocess.CompletedProcess(args, 0, "a" * 64, "")
        if args[1] == "inspect":
            return subprocess.CompletedProcess(args, 0, "unexpected-owner", "")
        raise AssertionError("unverified container must not be copied or removed")

    monkeypatch.setattr(producer, "_run", impostor)
    with pytest.raises(producer.InventoryError, match="ownership"):
        producer.build_inventory(ROOT, revision, tmp_path)
    assert not any(command[1] in ("cp", "rm") for command in commands)
    assert (tmp_path / "caddy.container-intent.json").is_file()


@WINDOWS
def test_existing_container_with_reserved_name_is_never_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    real_run = producer._run
    revision = real_run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    commands: list[list[str]] = []

    def existing(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if args[0] != "docker":
            return real_run(args, **kwargs)
        commands.append(args)
        if args[1] == "build":
            Path(args[args.index("--iidfile") + 1]).write_text(
                "sha256:" + "1" * 64, encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "ps":
            return subprocess.CompletedProcess(args, 0, "a" * 64, "")
        raise AssertionError("pre-existing container must not be touched")

    monkeypatch.setattr(producer, "_run", existing)
    with pytest.raises(producer.InventoryError, match="already exists"):
        producer.build_inventory(ROOT, revision, tmp_path)
    assert all(command[1] not in ("create", "rm", "cp") for command in commands)


def test_cli_writes_inventory_with_uncommitted_source_scope_explained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    output = tmp_path / "inventory.json"
    work = tmp_path / "work"
    revision = "a" * 40
    example_report = {
        "source": {"revision": revision, "context": "uncommitted changes excluded"}
    }
    received: list[tuple[Path, str, Path]] = []

    def build(repo: Path, source: str, directory: Path) -> dict[str, object]:
        received.append((repo, source, directory))
        assert directory.is_dir()
        return example_report

    monkeypatch.setattr(producer, "build_inventory", build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(PRODUCER),
            "--revision",
            revision,
            "--work-dir",
            str(work),
            "--output",
            str(output),
        ],
    )
    assert producer.main() == 0
    assert received == [(ROOT, revision, work)]
    assert json.loads(output.read_text(encoding="utf-8")) == example_report


@pytest.mark.parametrize("destination", ["existing", "missing-parent"])
def test_cli_rejects_unwritable_report_destination_before_build(
    destination: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = load_producer()
    work = tmp_path / "work"
    output = tmp_path / "inventory.json"
    if destination == "existing":
        output.write_text("preserve", encoding="utf-8")
    else:
        output = tmp_path / "missing" / "inventory.json"
    calls: list[bool] = []
    monkeypatch.setattr(producer, "build_inventory", lambda *_: calls.append(True))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(PRODUCER),
            "--revision",
            "a" * 40,
            "--work-dir",
            str(work),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as failure:
        producer.main()
    assert failure.value.code == 1
    assert not calls
    assert not work.exists()
    if destination == "existing":
        assert output.read_text(encoding="utf-8") == "preserve"


def test_script_rejects_symbolic_revision_without_creating_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    work = tmp_path / "work"
    output = tmp_path / "inventory.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(PRODUCER),
            "--revision",
            "HEAD",
            "--work-dir",
            str(work),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as failure:
        runpy.run_path(str(PRODUCER), run_name="__main__")
    assert failure.value.code == 1
    assert "full 40-character" in capsys.readouterr().err
    assert not work.exists()
    assert not output.exists()
