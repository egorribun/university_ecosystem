"""Private causal tests for the staged rendered-target runner glue."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import marshal
import os
import shutil
import struct
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.quality import run_semgrep_gate as gate
from tests import test_helm_rendered_target_overlay as helper_tests
from tests import test_run_semgrep_gate as base_tests

HELPER_PATH = "scripts/quality/helm_rendered_target_overlay.py"
PROFILE_REGISTRY_PATH = "scripts/quality/helm_semgrep_profile_registry.json"
ARCHIVE_BYTES = b"synthetic, checksum-pinned Helm archive"
HELM_CALLS: list[list[str]] = []
_template_roles, GUARD_PATHS = helper_tests.helm_overlay._roles(
    json.loads(helper_tests.TEST_REGISTRY_BYTES)
)
TEMPLATE_PATHS = tuple(sorted(_template_roles))
PROFILE_VIEWS = tuple(
    (name, f"charts/rendered-profiles/{name}.yaml")
    for name in helper_tests.helm_overlay.PROFILE_NAMES
)
CHART_PATHS = tuple(
    sorted(
        path.relative_to(helper_tests.REPOSITORY_ROOT).as_posix()
        for path in (helper_tests.REPOSITORY_ROOT / "charts").rglob("*")
        if path.is_file()
    )
)

FAKE_HELPER_TEMPLATE = r'''"""Tiny staged helper stub used to test runner orchestration only."""
from __future__ import annotations

MODE = __MODE__
TEMPLATE_PATHS = __TEMPLATE_PATHS__
GUARD_PATHS = set(__GUARD_PATHS__)
PROFILE_VIEWS = __PROFILE_VIEWS__


class HelmOverlayError(RuntimeError):
    pass


def helm_archive_pin(source_snapshot_root, source_manifest):
    from tests.test_run_semgrep_helm_overlay import _fake_helm_archive_pin
    return _fake_helm_archive_pin(
        MODE, source_snapshot_root, source_manifest, HelmOverlayError
    )


def verify_helm_archive(source_snapshot_root, source_manifest, archive_path, extraction_root):
    from tests.test_run_semgrep_helm_overlay import _fake_verify_helm_archive
    return _fake_verify_helm_archive(
        MODE, source_snapshot_root, source_manifest, archive_path, extraction_root,
        HelmOverlayError,
    )


def bounded_process_runner(argv, cwd, timeout_seconds, stdout_limit_bytes, stderr_limit_bytes):
    from tests.test_run_semgrep_helm_overlay import _fake_bounded_process_runner
    return _fake_bounded_process_runner(
        MODE, argv, cwd, timeout_seconds, stdout_limit_bytes, stderr_limit_bytes
    )


def prepare_overlay(
    source_snapshot_root, overlay_root, source_manifest, *, helm_tool, bounded_runner
):
    from tests.test_run_semgrep_helm_overlay import _fake_prepare_overlay
    return _fake_prepare_overlay(
        MODE, TEMPLATE_PATHS, GUARD_PATHS, PROFILE_VIEWS,
        source_snapshot_root, overlay_root, source_manifest,
        helm_tool, bounded_runner, HelmOverlayError,
    )
'''


def _helper_bytes(mode: str) -> bytes:
    source = (
        FAKE_HELPER_TEMPLATE.replace("__MODE__", repr(mode))
        .replace("__TEMPLATE_PATHS__", repr(TEMPLATE_PATHS))
        .replace("__GUARD_PATHS__", repr(GUARD_PATHS))
        .replace("__PROFILE_VIEWS__", repr(PROFILE_VIEWS))
    )
    return source.encode("utf-8")


def _test_helm_pin(archive_bytes: bytes = ARCHIVE_BYTES) -> dict[str, str]:
    windows = os.name == "nt"
    platform_key = "windows-amd64" if windows else "linux-amd64"
    archive_type = "zip" if windows else "tar.gz"
    executable_name = "helm.exe" if windows else "helm"
    return {
        "platform_key": platform_key,
        "version": "v4.2.4",
        "archive_url": f"https://get.helm.sh/helm-v4.2.4-{platform_key}.{archive_type}",
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "archive_type": archive_type,
        "archive_member": f"{platform_key}/{executable_name}",
        "executable_name": executable_name,
    }


def _test_registry_bytes(archive_bytes: bytes = ARCHIVE_BYTES) -> bytes:
    return (
        json.dumps(
            {"helm_toolchains": [_test_helm_pin(archive_bytes)]},
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _fake_helm_archive_pin(
    mode: str,
    source_root: Path,
    source_manifest: list[dict[str, str]],
    error_type: type,
) -> dict[str, str]:
    if mode == "worktree":
        raise error_type("worktree helper must never run")
    staged = {entry["path"]: entry for entry in source_manifest}
    registry_path = source_root / PROFILE_REGISTRY_PATH
    registry_entry = staged[PROFILE_REGISTRY_PATH]
    registry_bytes = registry_path.read_bytes()
    if hashlib.sha256(registry_bytes).hexdigest() != registry_entry["sha256"]:
        raise error_type("staged registry bytes differ from the index manifest")
    return json.loads(registry_bytes)["helm_toolchains"][0]


def _fake_verify_helm_archive(
    mode: str,
    source_root: Path,
    source_manifest: list[dict[str, str]],
    archive_path: Path,
    extraction_root: Path,
    error_type: type,
) -> SimpleNamespace:
    if mode == "archive-failure":
        raise error_type("synthetic archive verification failure")
    pin = _fake_helm_archive_pin(mode, source_root, source_manifest, error_type)
    archive_bytes = archive_path.read_bytes()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if archive_sha256 != pin["archive_sha256"]:
        raise error_type("synthetic archive checksum mismatch")
    extraction_root.mkdir(parents=True)
    executable = extraction_root / pin["executable_name"]
    executable.write_bytes(b"test-only fake Helm executable")
    return SimpleNamespace(
        executable=executable,
        extraction_root=extraction_root,
        archive_path=archive_path,
        archive_sha256=archive_sha256,
        binary_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        version=pin["version"],
        platform_key=pin["platform_key"],
    )


def _fake_bounded_process_runner(
    mode: str,
    argv: list[str],
    cwd: Path,
    timeout_seconds: float,
    stdout_limit_bytes: int,
    stderr_limit_bytes: int,
) -> SimpleNamespace:
    assert cwd.is_dir()
    assert timeout_seconds > 0
    assert stdout_limit_bytes == 8 * 1024 * 1024
    assert stderr_limit_bytes == 256 * 1024
    HELM_CALLS.append(list(argv))
    if len(argv) > 1 and argv[1] == "version":
        return SimpleNamespace(
            returncode=0,
            stdout=b"v4.2.4\n",
            stderr=b"",
            timed_out=False,
            output_limit_exceeded=False,
        )
    if mode == "profile-failure":
        return SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"synthetic render failure",
            timed_out=False,
            output_limit_exceeded=False,
        )
    return SimpleNamespace(
        returncode=0,
        stdout=b"synthetic rendered profile\n",
        stderr=b"",
        timed_out=False,
        output_limit_exceeded=False,
    )


def _fake_prepare_overlay(
    mode: str,
    template_paths: tuple[str, ...],
    guard_paths: set[str],
    profile_views: tuple[tuple[str, str], ...],
    source_root: Path,
    overlay_root: Path,
    source_manifest: list[dict[str, str]],
    helm_tool: SimpleNamespace,
    bounded_runner: Any,
    error_type: type,
) -> tuple[Path, dict[str, Any]]:
    if mode == "worktree":
        raise error_type("worktree helper must never run")
    staged = {entry["path"]: entry for entry in source_manifest}
    if set(template_paths) - set(staged):
        raise error_type("template inventory missing from staged index blobs")
    for path in template_paths:
        entry = staged[path]
        if (
            hashlib.sha256((source_root / path).read_bytes()).hexdigest()
            != entry["sha256"]
        ):
            raise error_type("template source did not come from its stage-zero blob")

    version = bounded_runner(
        [str(helm_tool.executable), "version", "--template", "{{.Version}}"],
        source_root,
        10.0,
        8 * 1024 * 1024,
        256 * 1024,
    )
    if version.returncode != 0 or version.stdout.strip() != b"v4.2.4":
        raise error_type("verified Helm version probe failed")
    commands: list[list[str]] = []
    for name, _view_path in profile_views:
        command = [
            str(helm_tool.executable),
            "template",
            name,
            "--dependency-update=false",
        ]
        result = bounded_runner(
            command,
            source_root,
            60.0,
            8 * 1024 * 1024,
            256 * 1024,
        )
        commands.append(command)
        if result.returncode != 0 or result.stderr:
            raise error_type("profile render failed: " + name)

    shutil.copytree(source_root, overlay_root, symlinks=False)
    for path in template_paths:
        (overlay_root / path).unlink()

    profiles = []
    for name, view_path in profile_views:
        destination = overlay_root / view_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        rendered = (
            "# Source: synthetic/templates/profile.yaml\n"
            "apiVersion: v1\n"
            "kind: ConfigMap\n"
            "metadata:\n"
            f"  name: {name}\n"
        ).encode()
        destination.write_bytes(rendered)
        profiles.append(
            {
                "name": name,
                "profile_kind": "diagnostic-only"
                if name.startswith("gateway-api")
                else "deployment",
                "command_sha256": hashlib.sha256(
                    json.dumps(commands[len(profiles)], separators=(",", ":")).encode()
                ).hexdigest(),
                "values_sources": [],
                "api_versions": [],
                "view_path": view_path,
                "view_sha256": hashlib.sha256(rendered).hexdigest(),
                "objects": [],
                "source_paths_seen": [],
            }
        )

    source_manifest_bytes = (
        json.dumps(
            {"targets": source_manifest},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    targets = []
    for path, entry in sorted(staged.items()):
        if path in template_paths:
            continue
        targets.append(
            {
                **entry,
                "sha256": hashlib.sha256(
                    (overlay_root / path).read_bytes()
                ).hexdigest(),
                "origin": "staged-index",
            }
        )
    for profile in profiles:
        rendered = (overlay_root / profile["view_path"]).read_bytes()
        targets.append(
            {
                "path": profile["view_path"],
                "mode": "100644",
                "oid": base_tests._git_blob_oid(rendered),
                "stage": "rendered",
                "sha256": profile["view_sha256"],
                "origin": "helm-profile:" + profile["name"],
            }
        )
    template_sources = [
        {
            "path": path,
            "source_sha256": staged[path]["sha256"],
            "git_blob_oid": staged[path]["oid"],
            "role": "guard-only" if path in guard_paths else "resource",
            "profiles": [name for name, _view in profile_views],
        }
        for path in template_paths
    ]
    registry_sha256 = hashlib.sha256(
        (source_root / PROFILE_REGISTRY_PATH).read_bytes()
    ).hexdigest()
    return overlay_root, {
        "schema_version": 1,
        "target_model": "test-rendered-overlay-v1",
        "helm_version": "v4.2.4",
        "helm_platform_key": helm_tool.platform_key,
        "helm_archive_sha256": helm_tool.archive_sha256,
        "helm_binary_sha256": helm_tool.binary_sha256,
        "profile_registry_path": PROFILE_REGISTRY_PATH,
        "profile_registry_sha256": registry_sha256,
        "source_snapshot_manifest_sha256": hashlib.sha256(
            source_manifest_bytes
        ).hexdigest(),
        "template_sources": template_sources,
        "guard_only_sources": sorted(guard_paths),
        "profiles": profiles,
        "targets": targets,
    }


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    helper_mode: str = "success",
    missing_template: str | None = None,
    drift_worktree: bool = False,
    actual_helper: bool = False,
) -> tuple[Path, Path, dict[str, bytes]]:
    relative_paths = tuple(
        sorted(
            set(base_tests.TRACKED_PATHS)
            | set(CHART_PATHS)
            | set(TEMPLATE_PATHS)
            | {HELPER_PATH, PROFILE_REGISTRY_PATH}
        )
    )
    monkeypatch.setattr(base_tests, "TRACKED_PATHS", relative_paths)
    repository_root = tmp_path / "repository"
    for path in TEMPLATE_PATHS:
        (repository_root / path).parent.mkdir(parents=True, exist_ok=True)
    _commit, rules_root = base_tests._prepare_repository(repository_root, monkeypatch)
    relative_paths = base_tests.TRACKED_PATHS
    index_blobs = {
        path: (repository_root / path).read_bytes() for path in relative_paths
    }
    for path in TEMPLATE_PATHS:
        index_blobs[path] = f"# staged source blob for {path}\n".encode()
    if actual_helper:
        candidate_root = Path(gate.__file__).resolve().parents[2]
        index_blobs[HELPER_PATH] = (candidate_root / HELPER_PATH).read_bytes()
        index_blobs[PROFILE_REGISTRY_PATH] = helper_tests.TEST_REGISTRY_BYTES
    else:
        index_blobs[HELPER_PATH] = _helper_bytes(helper_mode)
        index_blobs[PROFILE_REGISTRY_PATH] = _test_registry_bytes()
    index_blobs["app/example.py"] = b"eval(input())\n"
    if missing_template is not None:
        index_blobs.pop(missing_template)
    if drift_worktree:
        (repository_root / HELPER_PATH).write_bytes(_helper_bytes("worktree"))
        (repository_root / "app/example.py").write_bytes(b"worktree benign bytes\n")
        (repository_root / TEMPLATE_PATHS[0]).write_bytes(b"worktree template bytes\n")
    return repository_root, rules_root, index_blobs


def _run_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    helper_mode: str = "success",
    missing_template: str | None = None,
    drift_worktree: bool = False,
    actual_helper: bool = False,
    mutate_after: str | None = None,
    download_bytes: bytes | None = None,
    prefetched_archive: bytes | None = None,
) -> tuple[
    int,
    Path,
    list[list[str]],
    list[list[str]],
    list[list[str]],
    list[dict[str, str]],
]:
    # The shared fixtures load a separate source-bound module; all fixture
    # patches must target the same runner instance that this case executes.
    monkeypatch.setattr(base_tests, "gate", gate)
    repository_root, rules_root, index_blobs = _fixture(
        tmp_path,
        monkeypatch,
        helper_mode=helper_mode,
        missing_template=missing_template,
        drift_worktree=drift_worktree,
        actual_helper=actual_helper,
    )
    runner_repository_root = Path(gate.__file__).resolve().parents[2]
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", runner_repository_root)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    base_tests._stub_ignore_validator(monkeypatch)
    base_runner, calls, snapshots = base_tests._runner_for_scan(
        repository_root, index_blobs=index_blobs
    )
    HELM_CALLS.clear()
    download_calls: list[dict[str, str]] = []
    expected_archive = (
        helper_tests.TEST_HELM_ARCHIVE if actual_helper else ARCHIVE_BYTES
    )
    response_archive = (
        download_bytes if download_bytes is not None else expected_archive
    )

    def fake_download(pin: dict[str, str], destination: Path) -> Path:
        download_calls.append(pin)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response_archive)
        if hashlib.sha256(response_archive).hexdigest() != pin["archive_sha256"]:
            raise gate.SemgrepGateError("mocked archive digest mismatch")
        return destination

    monkeypatch.setattr(gate, "_download_helm_archive", fake_download)
    if actual_helper:
        original_loader = gate._load_overlay_helper
        fake_helm = helper_tests.FakeBoundedRunner(
            json.loads(helper_tests.TEST_REGISTRY_BYTES)
        )

        def load_candidate_helper(source_root: Path) -> Any:
            module = original_loader(source_root)
            module.EXPECTED_PROFILE_REGISTRY_SHA256 = helper_tests._sha(
                helper_tests.TEST_REGISTRY_BYTES
            )

            def run_mocked_helm(
                argv: list[str],
                cwd: Path,
                timeout_seconds: float,
                stdout_limit_bytes: int,
                stderr_limit_bytes: int,
            ) -> Any:
                result = fake_helm(
                    argv,
                    cwd,
                    timeout_seconds,
                    stdout_limit_bytes,
                    stderr_limit_bytes,
                )
                HELM_CALLS.append(list(argv))
                return module.BoundedProcessResult(
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    timed_out=result.timed_out,
                    output_limit_exceeded=result.output_limit_exceeded,
                )

            module.bounded_process_runner = run_mocked_helm
            return module

        monkeypatch.setattr(gate, "_load_overlay_helper", load_candidate_helper)

    def command_runner(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[Any]:
        completed = base_runner(command, **kwargs)
        if mutate_after == "scan" and command[:2] == ["docker", "run"]:
            overlay = base_tests._source_mount(command)
            (overlay / "app" / "example.py").write_bytes(b"mutated by scanner\n")
        if mutate_after == "gate" and any(
            token.endswith("semgrep_dispositions_gate.py") for token in command
        ):
            overlay = Path(command[command.index("--repository-root") + 1])
            (overlay / "app" / "example.py").write_bytes(b"mutated by gate\n")
        return completed

    output_directory = tmp_path / "reports"
    private_git_root = tmp_path / "git-common"
    monkeypatch.setattr(
        gate,
        "_git_common_directory",
        lambda _repository_root, *, command_runner: private_git_root,
    )
    if prefetched_archive is not None:
        prefetched_path = tmp_path / "prefetched-helm.zip"
        prefetched_path.write_bytes(prefetched_archive)
    else:
        prefetched_path = None
    result = gate.main(
        [base_tests.TEST_IMAGE, "--output-directory", str(output_directory)],
        repository_root=repository_root,
        command_runner=command_runner,
        helm_archive_path=prefetched_path,
    )
    return result, output_directory, calls, snapshots, HELM_CALLS.copy(), download_calls


def test_runner_renders_only_from_index_snapshot_and_preserves_other_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, report_directory, calls, snapshots, helm_calls, download_calls = _run_case(
        tmp_path,
        monkeypatch,
        actual_helper=True,
        drift_worktree=True,
    )

    assert result == 0
    scan = next(call for call in calls if call[:2] == ["docker", "run"])
    overlay_root = base_tests._source_mount(scan)
    assert overlay_root.name == "scan"
    assert snapshots == [
        sorted(
            set(base_tests.TRACKED_PATHS) - set(TEMPLATE_PATHS)
            | {view for _name, view in PROFILE_VIEWS}
        )
    ]
    assert len(helm_calls) == len(PROFILE_VIEWS) + 1
    assert all("--dependency-update=false" in command for command in helm_calls[1:])
    assert len(download_calls) == 1

    source_manifest = json.loads(
        (report_directory / "semgrep-targets.json").read_text(encoding="utf-8")
    )["targets"]
    staged_app = next(row for row in source_manifest if row["path"] == "app/example.py")
    assert staged_app["sha256"] == hashlib.sha256(b"eval(input())\n").hexdigest()
    assert (
        staged_app["sha256"] != hashlib.sha256(b"worktree benign bytes\n").hexdigest()
    )
    candidate_root = Path(gate.__file__).resolve().parents[2]
    staged_helper = next(row for row in source_manifest if row["path"] == HELPER_PATH)
    staged_registry = next(
        row for row in source_manifest if row["path"] == PROFILE_REGISTRY_PATH
    )
    assert (
        staged_helper["sha256"]
        == hashlib.sha256((candidate_root / HELPER_PATH).read_bytes()).hexdigest()
    )
    assert (
        staged_helper["sha256"] != hashlib.sha256(_helper_bytes("worktree")).hexdigest()
    )
    assert staged_registry["sha256"] == helper_tests._sha(
        helper_tests.TEST_REGISTRY_BYTES
    )

    overlay_report = json.loads(
        (report_directory / "semgrep-rendered-target-overlay.json").read_text(
            encoding="utf-8"
        )
    )
    assert overlay_report["source_snapshot_manifest_sha256"]
    assert overlay_report["target_model"] == "helm-rendered-v1"
    assert overlay_report["scanner_invoked"] is False
    assert overlay_report["profile_registry_sha256"] == staged_registry["sha256"]
    assert {source["path"] for source in overlay_report["template_sources"]} == set(
        TEMPLATE_PATHS
    )
    assert set(overlay_report["guard_only_sources"]) == set(GUARD_PATHS)
    assert {profile["name"] for profile in overlay_report["profiles"]} == {
        name for name, _view in PROFILE_VIEWS
    }
    target_rows = {row["path"]: row for row in overlay_report["targets"]}
    assert set(target_rows) == (set(base_tests.TRACKED_PATHS) - set(TEMPLATE_PATHS)) | {
        view for _name, view in PROFILE_VIEWS
    }
    assert not set(target_rows).intersection(TEMPLATE_PATHS)
    assert target_rows["app/example.py"]["origin"] == "staged-index"
    assert target_rows["app/example.py"]["sha256"] == staged_app["sha256"]
    assert all(
        target_rows[view]["origin"] == f"helm-profile:{name}"
        for name, view in PROFILE_VIEWS
    )
    consistency = json.loads(
        (report_directory / "semgrep-targets-consistency.json").read_text(
            encoding="utf-8"
        )
    )
    assert consistency["status"] == "match"


def test_missing_template_inventory_fails_before_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = TEMPLATE_PATHS[-1]
    result, report_directory, calls, _snapshots, helm_calls, download_calls = _run_case(
        tmp_path,
        monkeypatch,
        missing_template=missing,
    )

    assert result == 1
    assert not any(call[:2] == ["docker", "run"] for call in calls)
    assert not helm_calls
    assert not download_calls
    assert not (report_directory / "semgrep.json").exists()


def test_profile_failure_fails_before_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, report_directory, calls, _snapshots, helm_calls, _download_calls = (
        _run_case(
            tmp_path,
            monkeypatch,
            helper_mode="profile-failure",
        )
    )

    assert result == 1
    assert not any(call[:2] == ["docker", "run"] for call in calls)
    assert [call[1] for call in helm_calls] == ["version", "template"]
    assert not (report_directory / "semgrep.json").exists()


def test_staged_helper_loader_ignores_valid_hash_bytecode(tmp_path: Path) -> None:
    candidate_root = Path(gate.__file__).resolve().parents[2]
    staged_helper = tmp_path / HELPER_PATH
    staged_helper.parent.mkdir(parents=True)
    source = (candidate_root / HELPER_PATH).read_bytes()
    staged_helper.write_bytes(source)
    cache_path = Path(importlib.util.cache_from_source(str(staged_helper)))
    cache_path.parent.mkdir(parents=True)
    sentinel = tmp_path / "bytecode-executed"
    malicious_code = compile(
        f"open({str(sentinel)!r}, 'wb').write(b'executed')",
        str(staged_helper),
        "exec",
    )
    bytecode = (
        importlib.util.MAGIC_NUMBER
        + struct.pack("<I", 1)
        + importlib.util.source_hash(source)
        + marshal.dumps(malicious_code)
    )
    cache_path.write_bytes(bytecode)

    loaded = gate._load_overlay_helper(tmp_path)

    assert callable(loaded.prepare_overlay)
    assert not sentinel.exists()
    assert cache_path.read_bytes() == bytecode


class _FakeHTTPResponse:
    def __init__(
        self,
        data: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        on_read: Callable[[], None] | None = None,
    ) -> None:
        self._data = data
        self._offset = 0
        self.status = status
        self._on_read = on_read
        self.headers = headers or {"Content-Length": str(len(data))}

    def getheader(self, name: str) -> str | None:
        return self.headers.get(name)

    def read(self, size: int) -> bytes:
        if self._on_read is not None:
            self._on_read()
        result = self._data[self._offset : self._offset + size]
        self._offset += len(result)
        return result


class _FakeSocket:
    def settimeout(self, timeout_seconds: float) -> None:
        assert timeout_seconds > 0


class _FakeHTTPSConnection:
    def __init__(self, response: _FakeHTTPResponse, *, timeout: float) -> None:
        self._response = response
        self.timeout = timeout
        self.sock = _FakeSocket()
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, path, headers))

    def getresponse(self) -> _FakeHTTPResponse:
        return self._response

    def close(self) -> None:
        self.closed = True


def _stub_archive_connections(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_FakeHTTPResponse],
) -> list[_FakeHTTPSConnection]:
    connections: list[_FakeHTTPSConnection] = []

    def create_connection(
        host: str,
        *,
        port: int,
        timeout: float,
        context: object,
    ) -> _FakeHTTPSConnection:
        assert host == gate.HELM_ARCHIVE_HOST
        assert port == 443
        assert timeout <= gate.HELM_ARCHIVE_TIMEOUT_SECONDS
        assert context is not None
        connection = _FakeHTTPSConnection(responses.pop(0), timeout=timeout)
        connections.append(connection)
        return connection

    monkeypatch.setattr(gate.http.client, "HTTPSConnection", create_connection)
    return connections


def test_download_streams_only_the_pinned_official_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = b"bounded test archive"
    pin = _test_helm_pin(archive)
    response = _FakeHTTPResponse(archive)
    connections = _stub_archive_connections(monkeypatch, [response])

    destination = gate._download_helm_archive(pin, tmp_path / "helm.archive")

    assert destination.read_bytes() == archive
    assert connections[0].requests == [
        (
            "GET",
            pin["archive_url"].removeprefix("https://get.helm.sh"),
            {"User-Agent": "university-ecosystem-semgrep-gate"},
        )
    ]
    assert connections[0].closed


def test_download_rejects_non_https_and_unapproved_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _test_helm_pin()
    bad_protocol = dict(
        pin, archive_url=pin["archive_url"].replace("https://", "http://")
    )
    with pytest.raises(gate.SemgrepGateError, match="canonical official release URL"):
        gate._download_helm_archive(bad_protocol, tmp_path / "bad-protocol.archive")

    response = _FakeHTTPResponse(
        status=302,
        headers={"Location": "https://attacker.invalid/helm-v4.2.4-windows-amd64.zip"},
    )
    connections = _stub_archive_connections(monkeypatch, [response])
    with pytest.raises(gate.SemgrepGateError, match="redirected outside"):
        gate._download_helm_archive(pin, tmp_path / "redirected.archive")
    assert not (tmp_path / "redirected.archive").exists()
    assert connections[0].closed


def test_download_rejects_oversized_and_wrong_digest_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _test_helm_pin(b"small")
    monkeypatch.setattr(gate, "HELM_ARCHIVE_MAX_BYTES", 4)
    oversized_response = _FakeHTTPResponse(b"12345")
    _stub_archive_connections(monkeypatch, [oversized_response])
    with pytest.raises(gate.SemgrepGateError, match="size limit"):
        gate._download_helm_archive(pin, tmp_path / "oversized.archive")
    assert not (tmp_path / "oversized.archive").exists()

    monkeypatch.setattr(gate, "HELM_ARCHIVE_MAX_BYTES", 128 * 1024 * 1024)
    wrong_response = _FakeHTTPResponse(b"wrong")
    _stub_archive_connections(monkeypatch, [wrong_response])
    with pytest.raises(gate.SemgrepGateError, match="pinned SHA-256"):
        gate._download_helm_archive(pin, tmp_path / "wrong-digest.archive")
    assert not (tmp_path / "wrong-digest.archive").exists()


def test_download_enforces_total_deadline_and_removes_its_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _test_helm_pin()
    monkeypatch.setattr(gate, "HELM_ARCHIVE_TIMEOUT_SECONDS", 0.001)
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(gate, "time", SimpleNamespace(monotonic=lambda: clock.now))
    destination = tmp_path / "slow.archive"

    def exceed_deadline_during_read() -> None:
        assert destination.is_file()
        clock.now = 10.0

    response = _FakeHTTPResponse(ARCHIVE_BYTES, on_read=exceed_deadline_during_read)
    connections = _stub_archive_connections(monkeypatch, [response])

    with pytest.raises(gate.SemgrepGateError, match="time limit"):
        gate._download_helm_archive(pin, destination)
    assert not destination.exists()
    assert connections[0].closed


def test_prefetched_archive_cache_tampering_fails_before_render_or_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _reports, calls, _snapshots, helm_calls, download_calls = _run_case(
        tmp_path,
        monkeypatch,
        prefetched_archive=b"tampered cached archive",
    )

    assert result == 1
    assert not any(call[:2] == ["docker", "run"] for call in calls)
    assert not helm_calls
    assert not download_calls


@pytest.mark.parametrize("mutate_after", ["scan", "gate"])
def test_overlay_mutation_after_scan_or_gate_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate_after: str,
) -> None:
    result, _report_directory, calls, _snapshots, _helm_calls, _download_calls = (
        _run_case(
            tmp_path,
            monkeypatch,
            mutate_after=mutate_after,
        )
    )

    assert result == 1
    gate_called = any(
        any(token.endswith("semgrep_dispositions_gate.py") for token in call)
        for call in calls
    )
    assert gate_called is (mutate_after == "gate")
