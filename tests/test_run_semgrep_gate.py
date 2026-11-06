"""Behavioral tests for the shared pinned Semgrep local and CI gate."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPOSITORY_ROOT = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "pyproject.toml").is_file()
    ),
    None,
)
if REPOSITORY_ROOT is None:
    raise RuntimeError("repository root could not be located")
sys.path.insert(0, str(REPOSITORY_ROOT))
RUNNER_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "quality" / "run_semgrep_gate.py"
)
SPEC = importlib.util.spec_from_file_location(
    "dockerfile_candidate_runner", RUNNER_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("candidate Semgrep runner could not be loaded")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)
SELECTOR_PATH = REPOSITORY_ROOT / "scripts" / "quality" / "select_semgrep_rules.py"
SELECTOR_SPEC = importlib.util.spec_from_file_location(
    "dockerfile_candidate_selector", SELECTOR_PATH
)
if SELECTOR_SPEC is None or SELECTOR_SPEC.loader is None:
    raise RuntimeError("Semgrep selector could not be loaded")
selector = importlib.util.module_from_spec(SELECTOR_SPEC)
sys.modules[SELECTOR_SPEC.name] = selector
SELECTOR_SPEC.loader.exec_module(selector)

TRACKED_PATHS = (
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
    ".semgrep-rules/vulnerable.py",
    ".semgrepignore",
    "alembic/env.py",
    "app/example.py",
    "app/tests/vulnerable.py",
    "frontend/coverage-leak.py",
    "quality/semgrep-dispositions.json",
    "scripts/quality/select_semgrep_rules.py",
    "scripts/quality/semgrep_dispositions_gate.py",
)
TEST_IMAGE = "semgrep/semgrep:1.179.0@sha256:" + "d" * 64
OTHER_TEST_IMAGE = "semgrep/semgrep:1.179.0@sha256:" + "e" * 64


def _precommit_config(image: str) -> str:
    return (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: semgrep-docker\n"
        '        entry: "uv run --frozen python -I scripts/quality/run_semgrep_gate.py '
        f'{image}"\n'
    )


def _write_ci_pin(repository_root: Path, commit: str) -> None:
    workflow = repository_root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "jobs:\n"
        "  semgrep-sast:\n"
        "    steps:\n"
        "      - uses: actions/checkout@pinned\n"
        "        with:\n"
        "          repository: semgrep/semgrep-rules\n"
        f"          ref: {commit}\n",
        encoding="utf-8",
        newline="\n",
    )


def _make_rules(root: Path) -> Path:
    for directory in selector.DEFAULT_DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)
    rule_file = root / "python" / "security.yml"
    rule_file.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "test.security",
                        "message": "test",
                        "languages": ["python"],
                        "metadata": {"category": "security", "subcategory": ["vuln"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    return root


def _completed(
    command: list[str],
    returncode: int = 0,
    *,
    stdout: Any = "",
    stderr: Any = "",
) -> subprocess.CompletedProcess[Any]:
    return subprocess.CompletedProcess(
        command, returncode=returncode, stdout=stdout, stderr=stderr
    )


def _git_blob_oid(content: bytes) -> str:
    git_object = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    return hashlib.new("sha1", git_object, usedforsecurity=False).hexdigest()


def _index_records(
    blobs: dict[str, bytes],
    *,
    modes: dict[str, str] | None = None,
    stages: dict[str, int] | None = None,
) -> tuple[list[tuple[str, str, str, int]], bytes]:
    modes = modes or {}
    stages = stages or {}
    records = []
    for path, content in sorted(blobs.items()):
        mode = modes.get(path, "100644")
        stage = stages.get(path, 0)
        oid = _git_blob_oid(content)
        records.append((path, mode, oid, stage))
    encoded = b"".join(
        f"{mode} {oid} {stage}\t{path}".encode() + b"\0"
        for path, mode, oid, stage in records
    )
    return records, encoded


def _cat_file_output(object_ids: list[str], blobs: dict[str, bytes]) -> bytes:
    by_oid = {_git_blob_oid(content): content for content in blobs.values()}
    output = bytearray()
    for object_id in object_ids:
        content = by_oid[object_id]
        output.extend(f"{object_id} blob {len(content)}\n".encode("ascii"))
        output.extend(content)
        output.extend(b"\n")
    return bytes(output)


def _output_mount(command: list[str]) -> Path:
    mount = next(part for part in command if part.endswith(":/out"))
    return Path(mount.removesuffix(":/out"))


def _source_mount(command: list[str]) -> Path:
    mount = next(part for part in command if part.endswith(":/src:ro"))
    return Path(mount.removesuffix(":/src:ro"))


def _runner_for_scan(
    repository_root: Path,
    *,
    scanner_status: int = 1,
    gate_status: int = 0,
    selector_status: int = 0,
    cleanup_status: int = 0,
    create_container: bool = True,
    include_sarif: bool = True,
    index_blobs: dict[str, bytes] | None = None,
    oversized_target: str | None = None,
    mutate_index_after_scan: bool = False,
    selected_config: dict[str, Any] | None = None,
) -> tuple[Any, list[list[str]], list[list[str]]]:
    calls: list[list[str]] = []
    snapshots: list[list[str]] = []
    scan_timeouts: list[int | None] = []
    container_id = "b" * 64
    if index_blobs is None:
        index_blobs = {
            path: (
                (repository_root / path).read_bytes()
                if (repository_root / path).is_file()
                else b"fixture\n"
            )
            for path in TRACKED_PATHS
        }
    _initial_records, initial_index = _index_records(index_blobs)
    mutated_blobs = dict(index_blobs)
    if mutate_index_after_scan:
        mutated_blobs["app/example.py"] = b"value = 'changed while scanning'\n"
    _mutated_records, mutated_index = _index_records(mutated_blobs)
    index_reads = 0

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        nonlocal index_reads
        calls.append(command)
        if command[:4] == ["git", "ls-files", "--stage", "-z"]:
            index_reads += 1
            return _completed(
                command,
                stdout=(
                    mutated_index
                    if mutate_index_after_scan and index_reads >= 2
                    else initial_index
                ),
            )
        if command[:3] == ["git", "cat-file", "--batch"]:
            requested = kwargs["input"].decode("ascii").splitlines()
            return _completed(
                command,
                stdout=_cat_file_output(requested, index_blobs),
            )
        if command[:2] == ["docker", "run"]:
            scan_timeouts.append(kwargs.get("timeout"))
            output_directory = _output_mount(command)
            scan_root = _source_mount(command)
            snapshots.append(
                sorted(
                    path.relative_to(scan_root).as_posix()
                    for path in scan_root.rglob("*")
                    if path.is_file()
                )
            )
            json_output_option = next(
                (token for token in command if token.startswith("--json-output=/out/")),
                None,
            )
            sarif_output_option = next(
                (
                    token
                    for token in command
                    if token.startswith("--sarif-output=/out/")
                ),
                None,
            )
            if create_container:
                cid_file = Path(command[command.index("--cidfile") + 1])
                cid_file.write_text(f"{container_id}\n", encoding="utf-8")
                report: dict[str, Any] = {
                    "results": [],
                    "errors": [],
                    "time": {},
                    "paths": {
                        "scanned": [
                            "app/example.py",
                            *(
                                ["frontend/src/main.tsx"]
                                if "frontend/src/main.tsx" in index_blobs
                                else []
                            ),
                        ]
                    },
                }
                dockerfile_supplement = (
                    "--config" in command
                    and command[command.index("--config") + 1]
                    == "/out/security-rules-dockerfile.json"
                )
                inline_javascript_supplement = (
                    "--config" in command
                    and command[command.index("--config") + 1]
                    == "/out/security-rules-mts.json"
                    and command[-len(gate.INLINE_JAVASCRIPT_ALIASES) :]
                    == list(gate.INLINE_JAVASCRIPT_ALIASES)
                )
                if selected_config is not None and not dockerfile_supplement:
                    report["skipped_rules"] = []
                if dockerfile_supplement:
                    target_start = command.index(sarif_output_option) + 1
                    targets = command[target_start:]
                    report = {
                        "results": [
                            {
                                "check_id": "out.dockerfile.security.php-version-usage.php-version-usage",
                                "path": targets[0].replace("/", "\\"),
                                "start": {"line": 1, "col": 1, "offset": 0},
                                "end": {"line": 1, "col": 13, "offset": 12},
                                "extra": {"message": "fixture finding"},
                            }
                        ],
                        "errors": [],
                        "skipped_rules": [],
                        "time": {"fixpoint_timeouts": []},
                        "paths": {
                            "scanned": [
                                target.replace("/", "\\") for target in targets
                            ],
                            "skipped": [],
                        },
                    }
                if inline_javascript_supplement:
                    mts_config = json.loads(
                        (output_directory / "security-rules-mts.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    javascript_rule = next(
                        rule
                        for rule in mts_config["rules"]
                        if gate.INLINE_JAVASCRIPT_RULE_LANGUAGES.intersection(
                            rule["languages"]
                        )
                    )
                    inline_alias = gate.INLINE_JAVASCRIPT_ALIASES[0]
                    report = {
                        "version": "1.179.0",
                        "results": [
                            {
                                "check_id": "out." + javascript_rule["id"],
                                "path": inline_alias.replace("/", "\\"),
                                "start": {"line": 2, "col": 9, "offset": 9},
                                "end": {"line": 2, "col": 15, "offset": 15},
                                "extra": {"message": "fixture finding"},
                            }
                        ],
                        "errors": [],
                        "skipped_rules": [],
                        "time": {"fixpoint_timeouts": []},
                        "paths": {
                            "scanned": [
                                alias.replace("/", "\\")
                                for alias in gate.INLINE_JAVASCRIPT_ALIASES
                            ],
                            "skipped": [],
                        },
                    }
                if oversized_target is not None and not dockerfile_supplement:
                    target_bytes = (scan_root / oversized_target).read_bytes()
                    assert len(target_bytes) > 1_000_000
                    assert target_bytes == index_blobs[oversized_target]
                    # Match the reviewed Semgrep 1.179.0 oversized-target probe.
                    if "--max-target-bytes=0" in command:
                        report["paths"]["scanned"].append(oversized_target)
                        report["results"].append(
                            {
                                "check_id": "out.test.security",
                                "path": oversized_target.replace("/", "\\"),
                                "start": {"line": 1, "col": 1, "offset": 0},
                                "end": {"line": 1, "col": 14, "offset": 13},
                                "extra": {"message": "eval"},
                            }
                        )
                    elif "--verbose" in command:
                        report["paths"]["skipped"] = [
                            {
                                "path": oversized_target.replace("/", "\\"),
                                "reason": "exceeded_size_limit",
                            }
                        ]
                if "--verbose" in command:
                    report["paths"].setdefault("skipped", [])
                assert json_output_option is not None
                json_name = json_output_option.removeprefix("--json-output=/out/")
                (output_directory / json_name).write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
                if include_sarif and sarif_output_option is not None:
                    sarif_name = sarif_output_option.removeprefix(
                        "--sarif-output=/out/"
                    )
                    if dockerfile_supplement:
                        sarif_payload = {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "artifacts": [{"location": {"uri": targets[0]}}],
                                    "results": [
                                        {
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": targets[0]
                                                        }
                                                    }
                                                }
                                            ]
                                        }
                                    ],
                                }
                            ],
                        }
                    elif inline_javascript_supplement:
                        mts_config = json.loads(
                            (output_directory / "security-rules-mts.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        javascript_rule = next(
                            rule
                            for rule in mts_config["rules"]
                            if gate.INLINE_JAVASCRIPT_RULE_LANGUAGES.intersection(
                                rule["languages"]
                            )
                        )
                        inline_alias = gate.INLINE_JAVASCRIPT_ALIASES[0]
                        sarif_payload = {
                            "version": "2.1.0",
                            "runs": [
                                {
                                    "tool": {
                                        "driver": {
                                            "rules": [
                                                {"id": "out." + rule["id"]}
                                                for rule in mts_config["rules"]
                                            ]
                                        }
                                    },
                                    "artifacts": [
                                        {"location": {"uri": alias.replace("/", "\\")}}
                                        for alias in gate.INLINE_JAVASCRIPT_ALIASES
                                    ],
                                    "results": [
                                        {
                                            "ruleId": "out." + javascript_rule["id"],
                                            "locations": [
                                                {
                                                    "physicalLocation": {
                                                        "artifactLocation": {
                                                            "uri": inline_alias
                                                        },
                                                        "region": {
                                                            "startLine": 2,
                                                            "startColumn": 9,
                                                            "endLine": 2,
                                                            "endColumn": 15,
                                                            "byteOffset": 9,
                                                            "byteLength": 6,
                                                            "charOffset": 9,
                                                            "charLength": 6,
                                                        },
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    else:
                        sarif_payload = (
                            {
                                "version": "2.1.0",
                                "runs": [{"results": []}],
                            }
                            if selected_config is not None
                            else {}
                        )
                    (output_directory / sarif_name).write_text(
                        json.dumps(sarif_payload) + "\n", encoding="utf-8"
                    )
            return _completed(command, scanner_status)
        if command[:2] == ["docker", "inspect"]:
            if not create_container:
                return _completed(
                    command,
                    1,
                    stderr=f"Error: No such object: {command[-1]}\n",
                )
            name = (
                command[command.index("--name") + 1]
                if "--name" in command
                else command[-1]
            )
            expected_name = next(
                call[call.index("--name") + 1]
                for call in reversed(calls)
                if call[:2] == ["docker", "run"]
            )
            assert name in (container_id, expected_name)
            return _completed(command, stdout=f"{container_id} /{expected_name}\n")
        if command[:3] == ["docker", "rm", "-v"]:
            return _completed(command, cleanup_status)
        if command[0] == "git":
            return _completed(command)
        if command[0] == sys.executable or any(
            token.endswith("select_semgrep_rules.py") for token in command
        ):
            if any(token.endswith("select_semgrep_rules.py") for token in command):
                if selector_status != 0:
                    return _completed(command, selector_status)
                output_path = Path(command[command.index("--output") + 1])
                output_path.write_text(
                    json.dumps(selected_config or {"rules": []}) + "\n",
                    encoding="utf-8",
                )
                return _completed(command)
        if any(token.endswith("semgrep_dispositions_gate.py") for token in command):
            gate_script = next(
                Path(token)
                for token in command
                if token.endswith("semgrep_dispositions_gate.py")
            )
            assert Path(
                command[command.index("--repository-root") + 1]
            ) == _source_mount(
                next(call for call in calls if call[:2] == ["docker", "run"])
            )
            assert gate_script.is_relative_to(
                Path(command[command.index("--repository-root") + 1])
            )
            assert Path(command[command.index("--dispositions") + 1]) == (
                Path(command[command.index("--repository-root") + 1])
                / "quality"
                / "semgrep-dispositions.json"
            )
            return _completed(command, gate_status)
        raise AssertionError(f"unexpected command: {command!r} ({kwargs!r})")

    run.scan_timeouts = scan_timeouts
    return run, calls, snapshots


def _rules_archive(path: str = "python/example.yml") -> bytes:
    data = b"rules: []\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        directory = tarfile.TarInfo("python/")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        member = tarfile.TarInfo(path)
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def _prepare_repository(
    repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, Path]:
    global TRACKED_PATHS
    from tests import test_run_semgrep_helm_overlay as helm_tests

    TRACKED_PATHS = tuple(
        sorted(
            set(TRACKED_PATHS)
            | set(helm_tests.CHART_PATHS)
            | set(helm_tests.TEMPLATE_PATHS)
            | {helm_tests.HELPER_PATH, helm_tests.PROFILE_REGISTRY_PATH}
        )
    )
    commit = "a" * 40
    _write_ci_pin(repository_root, commit)
    for relative in TRACKED_PATHS:
        path = repository_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative.startswith("charts/"):
            source = helm_tests.helper_tests.REPOSITORY_ROOT / relative
            path.write_bytes(source.read_bytes())
        elif relative == helm_tests.HELPER_PATH:
            path.write_bytes(helm_tests._helper_bytes("success"))
        elif relative == helm_tests.PROFILE_REGISTRY_PATH:
            path.write_bytes(helm_tests._test_registry_bytes())
        elif relative == ".semgrepignore":
            path.write_text("tests/\n", encoding="utf-8")
        elif relative == ".pre-commit-config.yaml":
            path.write_text(_precommit_config(TEST_IMAGE), encoding="utf-8")
        elif relative == "app/example.py":
            path.write_text("value = True\n", encoding="utf-8")
        elif relative in {
            ".semgrep-rules/vulnerable.py",
            "alembic/env.py",
            "app/tests/vulnerable.py",
            "frontend/coverage-leak.py",
        }:
            path.write_text("eval(input())\n", encoding="utf-8")
        elif relative == ".github/workflows/ci.yml":
            continue
        else:
            path.write_text("{}\n", encoding="utf-8")
    (repository_root / ".env").write_text(
        "untracked credential placeholder\n", encoding="utf-8"
    )
    untracked_dependency = repository_root / "node_modules" / "example.js"
    untracked_dependency.parent.mkdir(parents=True, exist_ok=True)
    untracked_dependency.write_text("untracked package\n", encoding="utf-8")
    untracked_temp = repository_root / ".pytest_tmp_example" / "sample.py"
    untracked_temp.parent.mkdir(parents=True, exist_ok=True)
    untracked_temp.write_text("untracked test output\n", encoding="utf-8")
    archive_bytes = helm_tests.ARCHIVE_BYTES

    def offline_helm_archive(pin: dict[str, str], destination: Path) -> Path:
        if hashlib.sha256(archive_bytes).hexdigest() != pin["archive_sha256"]:
            raise AssertionError("synthetic Helm archive checksum mismatch")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive_bytes)
        return destination

    monkeypatch.setattr(gate, "_download_helm_archive", offline_helm_archive)
    return commit, _make_rules(repository_root / "fixture-rules")


def _private_temporary_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runner_root = tmp_path.parent
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", runner_root)
    temporary_parent = runner_root / ".git" / "ue-audit-work" / "runner-tests"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    return temporary_parent


def _expected_rendered_scan_paths() -> list[str]:
    from tests import test_run_semgrep_helm_overlay as helm_tests

    return sorted(
        (set(TRACKED_PATHS) - set(helm_tests.TEMPLATE_PATHS))
        | {view_path for _name, view_path in helm_tests.PROFILE_VIEWS}
    )


def _stub_ignore_validator(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    validated: list[Path] = []
    monkeypatch.setattr(
        gate,
        "_validate_semgrep_ignore_policy",
        lambda root: validated.append(root),
    )
    return validated


def test_archive_uses_only_the_workflow_commit_without_checkout(
    tmp_path: Path,
) -> None:
    commit = "b" * 40
    responses = iter(
        [
            _completed(["git", "init"]),
            _completed(["git", "remote"]),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout=f"{commit}\n"),
            _completed(["git", "archive"], stdout=_rules_archive()),
        ]
    )
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        calls.append(command)
        return next(responses)

    rules_root = gate._checkout_rules(commit, tmp_path / "rules", command_runner=run)

    assert rules_root == tmp_path / "rules" / "rules"
    assert (rules_root / "python" / "example.yml").read_bytes() == b"rules: []\n"
    fetch = next(command for command in calls if command[1:2] == ["fetch"])
    assert fetch[-1] == commit
    assert "--depth=1" in fetch
    assert not any(command[1:2] == ["checkout"] for command in calls)
    assert calls[-1][1:] == ["archive", "--format=tar", "FETCH_HEAD"]


def test_archive_rejects_a_commit_that_differs_from_the_workflow_pin(
    tmp_path: Path,
) -> None:
    commit = "c" * 40
    different_commit = "d" * 40
    responses = iter(
        [
            _completed(["git", "init"]),
            _completed(["git", "remote"]),
            _completed(["git", "fetch"]),
            _completed(["git", "rev-parse"], stdout=f"{different_commit}\n"),
        ]
    )

    with pytest.raises(gate.SemgrepGateError, match="do not match the CI pin"):
        gate._checkout_rules(
            commit,
            tmp_path / "rules",
            command_runner=lambda *_args, **_kwargs: next(responses),
        )


def test_full_scan_uses_selector_and_dispositions_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    temporary_parent = _private_temporary_parent(tmp_path, monkeypatch)
    validated_ignore_roots = _stub_ignore_validator(monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    runner, calls, snapshots = _runner_for_scan(repository_root)
    report_directory = tmp_path / "reports"
    report_directory.mkdir()
    (report_directory / "semgrep.json").write_text("stale\n", encoding="utf-8")

    result = gate.main(
        [
            TEST_IMAGE,
            "--output-directory",
            str(report_directory),
        ],
        repository_root=repository_root,
        command_runner=runner,
        temporary_parent=temporary_parent,
    )

    assert result == 0
    scan = next(call for call in calls if call[:2] == ["docker", "run"])
    scan_root = _source_mount(scan)
    assert validated_ignore_roots == [
        repository_root,
        scan_root.parent / "src",
        _source_mount(scan),
    ]
    assert not list(temporary_parent.iterdir())
    selector_call = next(
        call
        for call in calls
        if any(token.endswith("select_semgrep_rules.py") for token in call)
    )
    assert selector_call[selector_call.index("--rules-root") + 1] == str(rules_root)
    assert selector_call[1] == "-I"
    selector_script = next(
        Path(token)
        for token in selector_call
        if token.endswith("select_semgrep_rules.py")
    )
    assert selector_script.is_relative_to(scan_root.parent / "src")
    assert scan[scan.index("--metrics") + 1] == "off"
    assert "--disable-version-check" in scan
    assert "--disable-nosem" in scan
    assert "--no-git-ignore" in scan
    assert "--verbose" in scan
    assert "--max-target-bytes=0" in scan
    assert "--read-only" in scan
    assert "--rm" not in scan
    assert "--cpus=2" in scan
    assert "--memory=3g" in scan
    assert "--memory-swap=3g" in scan
    assert f"HOME={gate.CONTAINER_TMP}" in scan
    assert f"{gate.CONTAINER_TMP}:rw,nosuid,nodev,size=512m" in scan
    cidfile = Path(scan[scan.index("--cidfile") + 1])
    assert cidfile.parent == _output_mount(scan).parent
    assert cidfile != _output_mount(scan)
    assert scan[scan.index("--config") + 1] == "/out/security-rules.json"
    assert scan_root != repository_root
    assert f"{scan_root.as_posix()}:/src:ro" in scan
    assert snapshots == [_expected_rendered_scan_paths()]
    assert ".env" not in snapshots[0]
    assert "node_modules/example.js" not in snapshots[0]
    assert ".pytest_tmp_example/sample.py" not in snapshots[0]
    assert "--exclude" not in scan
    assert scan[-1] == "."
    assert {
        ".semgrep-rules/vulnerable.py",
        "alembic/env.py",
        "app/tests/vulnerable.py",
        "frontend/coverage-leak.py",
    }.issubset(snapshots[0])
    assert scan[scan.index("-c") + 1] == (
        f'mkdir -p {gate.CONTAINER_TMP}/.semgrep && exec semgrep "$@"'
    )
    assert scan[scan.index("--name") + 1].startswith("ue-r9-semgrep-luna-")
    cleanup = next(call for call in calls if call[:2] == ["docker", "rm"])
    assert cleanup[2:4] == ["-v", "--force"]
    assert cleanup[-1] == "b" * 64
    dispositions_call = next(
        call
        for call in calls
        if any(token.endswith("semgrep_dispositions_gate.py") for token in call)
    )
    assert dispositions_call[1] == "-I"
    gate_script = next(
        Path(token)
        for token in dispositions_call
        if token.endswith("semgrep_dispositions_gate.py")
    )
    assert gate_script.is_relative_to(scan_root)
    assert (
        dispositions_call[dispositions_call.index("--strip-check-prefix") + 1] == "out."
    )
    assert (
        (report_directory / "semgrep.json")
        .read_text(encoding="utf-8")
        .startswith('{"results": []')
    )
    assert (report_directory / "semgrep.sarif").read_text(encoding="utf-8") == "{}\n"
    target_manifest = json.loads(
        (report_directory / "semgrep-targets.json").read_text(encoding="utf-8")
    )
    assert [target["path"] for target in target_manifest["targets"]] == list(
        TRACKED_PATHS
    )
    source_bytes = (repository_root / "app" / "example.py").read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    assert (
        next(
            target["sha256"]
            for target in target_manifest["targets"]
            if target["path"] == "app/example.py"
        )
        == source_digest
    )
    app_entry = next(
        target
        for target in target_manifest["targets"]
        if target["path"] == "app/example.py"
    )
    assert app_entry["mode"] == "100644"
    assert app_entry["oid"] == _git_blob_oid(source_bytes)
    assert app_entry["stage"] == "0"
    consistency = json.loads(
        (report_directory / "semgrep-targets-consistency.json").read_text(
            encoding="utf-8"
        )
    )
    assert consistency["status"] == "match"
    assert consistency["target_count"] == len(TRACKED_PATHS)
    assert consistency["index_before_sha256"] == consistency["index_after_sha256"]


def test_oversized_staged_vulnerability_is_scanned_with_no_size_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    _stub_ignore_validator(monkeypatch)

    prefix = b"eval(input())\n"
    oversized_source = prefix + b"#" * (1_200_014 - len(prefix))
    index_blobs = {
        relative: (repository_root / relative).read_bytes()
        for relative in TRACKED_PATHS
    }
    index_blobs["app/oversized.py"] = oversized_source
    runner, calls, snapshots = _runner_for_scan(
        repository_root,
        index_blobs=index_blobs,
        oversized_target="app/oversized.py",
    )

    result = gate.run_gate(
        TEST_IMAGE,
        repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
        output_directory=tmp_path / "reports",
    )

    assert result == 0
    scan = next(call for call in calls if call[:2] == ["docker", "run"])
    assert "app/oversized.py" in snapshots[0]
    assert "--verbose" in scan
    assert "--max-target-bytes=0" in scan
    report_directory = tmp_path / "reports"
    report = json.loads((report_directory / "semgrep.json").read_text("utf-8"))
    assert "app/oversized.py" in report["paths"]["scanned"]
    assert report["paths"]["skipped"] == []
    assert report["results"][0]["path"] == "app\\oversized.py"


def test_scanner_status_one_still_runs_the_disposition_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    _stub_ignore_validator(monkeypatch)
    runner, calls, _snapshots = _runner_for_scan(repository_root, scanner_status=1)

    result = gate.run_gate(
        TEST_IMAGE,
        repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
    )

    assert result == 0
    assert any(
        any(token.endswith("semgrep_dispositions_gate.py") for token in call)
        for call in calls
    )


def test_staged_precommit_image_must_match_the_requested_scanner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, _rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate, "_checkout_rules", lambda *_args, **_kwargs: pytest.fail()
    )
    _stub_ignore_validator(monkeypatch)
    staged_blobs = {
        path: (repository_root / path).read_bytes() for path in TRACKED_PATHS
    }
    staged_blobs[".pre-commit-config.yaml"] = _precommit_config(
        OTHER_TEST_IMAGE
    ).encode("utf-8")
    runner, calls, _snapshots = _runner_for_scan(
        repository_root, index_blobs=staged_blobs
    )

    result = gate.main(
        [TEST_IMAGE],
        repository_root=repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
    )

    assert result == 1
    assert not any(call[0] == "docker" for call in calls)


def test_selector_failure_blocks_before_docker_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    _stub_ignore_validator(monkeypatch)
    runner, calls, _snapshots = _runner_for_scan(repository_root, selector_status=1)

    result = gate.main(
        [TEST_IMAGE],
        repository_root=repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
    )

    assert result == 1
    assert not any(call[0] == "docker" for call in calls)


def test_docker_start_failure_without_a_container_does_not_attempt_rm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    _stub_ignore_validator(monkeypatch)
    runner, calls, _snapshots = _runner_for_scan(
        repository_root, scanner_status=125, create_container=False
    )

    result = gate.main(
        [TEST_IMAGE],
        repository_root=repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
    )

    assert result == 1
    assert any(call[:2] == ["docker", "inspect"] for call in calls)
    assert not any(call[:2] == ["docker", "rm"] for call in calls)


@pytest.mark.parametrize(
    ("scanner_status", "include_sarif", "gate_status"),
    [(2, True, 0), (0, False, 0), (0, True, 1)],
)
def test_scan_or_gate_failures_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scanner_status: int,
    include_sarif: bool,
    gate_status: int,
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    _stub_ignore_validator(monkeypatch)
    runner, calls, _snapshots = _runner_for_scan(
        repository_root,
        scanner_status=scanner_status,
        gate_status=gate_status,
        include_sarif=include_sarif,
    )
    report_directory = tmp_path / "reports"

    result = gate.main(
        [
            TEST_IMAGE,
            "--output-directory",
            str(report_directory),
        ],
        repository_root=repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
    )

    assert result == 1
    if scanner_status != 2 and include_sarif:
        assert any(
            any(token.endswith("semgrep_dispositions_gate.py") for token in call)
            for call in calls
        )
    else:
        assert not any(
            any(token.endswith("semgrep_dispositions_gate.py") for token in call)
            for call in calls
        )
    assert (report_directory / "semgrep.json").is_file()
    assert (report_directory / "semgrep.sarif").is_file() is include_sarif


def test_invalid_image_fails_before_any_subprocess(tmp_path: Path) -> None:
    runner, calls, _snapshots = _runner_for_scan(tmp_path)

    result = gate.main(
        ["semgrep/semgrep:latest"],
        repository_root=tmp_path,
        command_runner=runner,
        temporary_parent=tmp_path,
    )

    assert result == 1
    assert calls == []


def test_isolated_cli_does_not_import_a_repository_yaml_shadow(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "yaml-shadow-imported"
    (tmp_path / "yaml.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('shadowed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    isolated_yaml = subprocess.run(  # noqa: S603  # fixed interpreter with isolated-mode arguments
        [
            sys.executable,
            "-I",
            "-c",
            "import yaml; assert yaml.safe_load('value: true') == {'value': True}",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert isolated_yaml.returncode == 0, isolated_yaml.stderr
    assert not marker.exists()

    isolated_runner = subprocess.run(  # noqa: S603  # fixed interpreter with isolated-mode arguments
        [
            sys.executable,
            "-I",
            str(Path(gate.__file__).resolve()),
            "semgrep/semgrep:latest",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert isolated_runner.returncode == 1
    assert "version tag and immutable digest" in isolated_runner.stderr
    assert not marker.exists()


def test_semgrep_ignore_validator_import_does_not_mutate_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_root = tmp_path / "snapshot"
    validator_path = (
        snapshot_root / "scripts" / "quality" / "semgrep_dispositions_gate.py"
    )
    validator_path.parent.mkdir(parents=True)
    validator_called = tmp_path / "validator-called"
    validator_path.write_text(
        "from pathlib import Path\n"
        "class GateError(Exception):\n"
        "    pass\n"
        "def validate_semgrep_ignore_policy(repository_root):\n"
        f"    Path({str(validator_called)!r}).write_text(\n"
        "        str(repository_root), encoding='utf-8'\n"
        "    )\n"
        "def _matches_reviewed_semgrep_ignore(relative_path):\n"
        "    return relative_path == 'reviewed/path.py'\n",
        encoding="utf-8",
    )
    snapshot_before = {
        path.relative_to(snapshot_root).as_posix(): path.read_bytes()
        for path in snapshot_root.rglob("*")
        if path.is_file()
    }

    # The `python -I` entrypoint ignores PYTHONDONTWRITEBYTECODE.
    # Exercise the write-enabled state and require local suppression.
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    matcher = gate._validate_semgrep_ignore_policy(snapshot_root)

    assert validator_called.read_text(encoding="utf-8") == str(snapshot_root)
    assert matcher is not None
    assert matcher("reviewed/path.py") is True
    assert matcher("other/path.py") is False
    assert sys.dont_write_bytecode is False
    assert "_ue_semgrep_dispositions_gate_policy" not in sys.modules
    snapshot_after = {
        path.relative_to(snapshot_root).as_posix(): path.read_bytes()
        for path in snapshot_root.rglob("*")
        if path.is_file()
    }
    assert snapshot_after == snapshot_before
    assert not (validator_path.parent / "__pycache__").exists()


DOCKERFILE_TARGETS = tuple(sorted(gate.REVIEWED_UNIGNORED_DOCKERFILE_TARGETS))
DOCKERFILE_ALIASES = tuple(
    f"target-{index:02d}/Dockerfile" for index in range(len(DOCKERFILE_TARGETS))
)
DOCKERFILE_ALIAS_TO_SOURCE = dict(
    zip(DOCKERFILE_ALIASES, DOCKERFILE_TARGETS, strict=True)
)
DOCKERFILE_RULE = {
    "id": gate.DOCKERFILE_RULE_ID,
    "message": "Detect PHP FROM tags expressed as a variable.",
    "languages": ["dockerfile"],
    "severity": "ERROR",
    "pattern": "FROM php:$PVERSION",
}
JAVASCRIPT_RULE = {
    "id": "javascript.security.test-inline",
    "message": "test inline JavaScript rule",
    "languages": ["javascript"],
    "severity": "WARNING",
    "pattern": "eval($X)",
}
TYPESCRIPT_RULE = {
    "id": "typescript.security.test-inline",
    "message": "test TypeScript rule",
    "languages": ["typescript"],
    "severity": "WARNING",
    "pattern": "eval($X)",
}


def _snapshot_manifest_sha256(manifest: list[dict[str, str]]) -> str:
    payload = (
        json.dumps(
            {"targets": manifest},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inline_javascript_fixture(
    tmp_path: Path, overrides: dict[str, bytes] | None = None
) -> tuple[Path, list[dict[str, str]], dict[str, str]]:
    source_root = tmp_path / "scan"
    source_root.mkdir(parents=True)
    source_manifest: list[dict[str, str]] = []
    overlay_hashes: dict[str, str] = {}
    source_overrides = overrides or {}
    fixture_paths = (*gate.REVIEWED_INLINE_JAVASCRIPT_PATHS, "frontend/src/main.tsx")
    for path in fixture_paths:
        content = source_overrides.get(path, (REPOSITORY_ROOT / path).read_bytes())
        target = source_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        oid = _git_blob_oid(content)
        source_manifest.append(
            {
                "path": path,
                "mode": "100644",
                "stage": "0",
                "oid": oid,
                "sha256": digest,
            }
        )
        overlay_hashes[path] = digest
    return source_root, source_manifest, overlay_hashes


def _materialized_inline_javascript_fixture(
    tmp_path: Path, overrides: dict[str, bytes] | None = None
) -> tuple[
    Path,
    tuple[str, ...],
    dict[str, gate.InlineJavaScriptBinding],
    str,
]:
    source_root, source_manifest, overlay_hashes = _inline_javascript_fixture(
        tmp_path, overrides
    )
    targets = gate._inline_javascript_scan_targets(
        source_root, overlay_hashes, source_manifest, lambda _path: False
    )
    aliases, bindings, manifest_hash = gate._materialize_inline_javascript_inputs(
        source_root=source_root,
        destination=tmp_path / "aliases",
        targets=targets,
        source_manifest=source_manifest,
        overlay_target_hashes=overlay_hashes,
        mapping_manifest_path=tmp_path / "inline-inputs.json",
        source_snapshot_manifest_sha256=_snapshot_manifest_sha256(source_manifest),
        ignore_matcher=lambda _path: False,
    )
    return source_root, aliases, bindings, manifest_hash


def _inline_javascript_report(aliases: tuple[str, ...]) -> dict[str, Any]:
    return {
        "version": "1.179.0",
        "results": [
            {
                "check_id": "out." + JAVASCRIPT_RULE["id"],
                "path": aliases[0],
                "start": {"line": 2, "col": 9, "offset": 9},
                "end": {"line": 2, "col": 15, "offset": 15},
                "extra": {"message": "fixture finding"},
            }
        ],
        "errors": [],
        "skipped_rules": [],
        "time": {"fixpoint_timeouts": []},
        "paths": {"scanned": list(aliases), "skipped": []},
    }


def test_dockerfile_target_selection_is_exact_and_fail_closed(
    tmp_path: Path,
) -> None:
    scan_root = tmp_path / "scan"
    hashes: dict[str, str] = {}
    for relative in DOCKERFILE_TARGETS:
        path = scan_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"FROM alpine:{relative}\n".encode()
        path.write_bytes(payload)
        hashes[relative] = hashlib.sha256(payload).hexdigest()

    selected = gate._dockerfile_scan_targets(scan_root, hashes, lambda _path: False)

    assert selected == DOCKERFILE_TARGETS
    assert gate._dockerfile_scan_targets(scan_root, {}, lambda _path: False) == ()
    with pytest.raises(gate.SemgrepGateError, match="target set is incomplete"):
        gate._dockerfile_scan_targets(
            scan_root,
            {DOCKERFILE_TARGETS[0]: hashes[DOCKERFILE_TARGETS[0]]},
            lambda _path: False,
        )
    with pytest.raises(gate.SemgrepGateError, match="ignore policy"):
        gate._dockerfile_scan_targets(scan_root, hashes, lambda _path: True)

    (scan_root / DOCKERFILE_TARGETS[0]).unlink()
    with pytest.raises(gate.SemgrepGateError, match="missing, linked or non-regular"):
        gate._dockerfile_scan_targets(scan_root, hashes, lambda _path: False)


def test_dockerfile_rule_projection_keeps_only_the_selected_unfiltered_rule(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "selected.json"
    destination = tmp_path / "dockerfile.json"
    selected.write_text(
        json.dumps(
            {
                "rules": [
                    {"id": "python-rule", "languages": ["python"]},
                    DOCKERFILE_RULE,
                    {"id": "js-rule", "languages": ["javascript"]},
                ]
            }
        ),
        encoding="utf-8",
        newline="\n",
    )

    digest, ids = gate._write_dockerfile_rules_config(selected, destination)

    assert json.loads(destination.read_text("utf-8")) == {"rules": [DOCKERFILE_RULE]}
    assert ids == (gate.DOCKERFILE_RULE_ID,)
    assert digest == hashlib.sha256(destination.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        {**DOCKERFILE_RULE, "paths": {"exclude": ["containers/**"]}},
        {**DOCKERFILE_RULE, "id": "different-dockerfile-rule"},
        {**DOCKERFILE_RULE, "languages": ["dockerfile", "python"]},
    ],
)
def test_dockerfile_rule_projection_rejects_path_filters_and_rule_changes(
    tmp_path: Path, mutation: dict[str, Any]
) -> None:
    selected = tmp_path / "selected.json"
    selected.write_text(json.dumps({"rules": [mutation]}), encoding="utf-8")

    with pytest.raises(gate.SemgrepGateError):
        gate._write_dockerfile_rules_config(selected, tmp_path / "projected.json")


def _dockerfile_report() -> dict[str, Any]:
    return {
        "version": "1.179.0",
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": list(DOCKERFILE_ALIASES), "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-target", "exact target set"),
        ("duplicate-target", "exact target set"),
        ("missing-skipped-metadata", "malformed path evidence"),
        ("skipped-target", "skipped an explicit target"),
        ("timeout", "timed-out analysis"),
        ("skipped-rule", "skipped rules"),
        ("error", "reported diagnostics"),
        ("outside-finding", "outside its target set"),
        ("wrong-rule", "outside the selected rule"),
    ],
)
def test_dockerfile_report_rejects_incomplete_or_out_of_scope_evidence(
    mutation: str, message: str
) -> None:
    report = _dockerfile_report()
    if mutation == "missing-target":
        report["paths"]["scanned"].pop()
    elif mutation == "duplicate-target":
        report["paths"]["scanned"].append(DOCKERFILE_ALIASES[0])
    elif mutation == "missing-skipped-metadata":
        del report["paths"]["skipped"]
    elif mutation == "skipped-target":
        report["paths"]["skipped"].append(
            {"path": DOCKERFILE_ALIASES[0], "reason": "exceeded_size_limit"}
        )
    elif mutation == "timeout":
        report["time"]["fixpoint_timeouts"].append({"rule": "r"})
    elif mutation == "skipped-rule":
        report["skipped_rules"].append({"rule_id": "r"})
    elif mutation == "error":
        report["errors"].append({"type": "PartialParsing"})
    elif mutation == "outside-finding":
        report["results"].append(
            {"check_id": "out." + gate.DOCKERFILE_RULE_ID, "path": "app/outside.py"}
        )
    else:
        report["results"].append(
            {"check_id": "out.other-rule", "path": DOCKERFILE_ALIASES[0]}
        )

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._validate_dockerfile_supplement_report(
            report, DOCKERFILE_ALIASES, DOCKERFILE_ALIAS_TO_SOURCE
        )


def test_dockerfile_merge_retains_findings_scanned_paths_and_sarif_runs() -> None:
    primary = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": ["app/example.py"], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    supplemental_raw = _dockerfile_report()
    supplemental_raw["results"].append(
        {
            "check_id": "out." + gate.DOCKERFILE_RULE_ID,
            "path": DOCKERFILE_ALIASES[0],
        }
    )
    gate._validate_dockerfile_supplement_report(
        supplemental_raw, DOCKERFILE_ALIASES, DOCKERFILE_ALIAS_TO_SOURCE
    )
    supplemental = gate._remap_dockerfile_report_paths(
        supplemental_raw, DOCKERFILE_ALIAS_TO_SOURCE
    )
    evidence = {
        "mode": "canonical-dockerfile-alias",
        "targets": list(DOCKERFILE_TARGETS),
        "aliases": DOCKERFILE_ALIAS_TO_SOURCE,
        "source_mapping_manifest_sha256": "b" * 64,
        "dockerfile_rule_ids": [gate.DOCKERFILE_RULE_ID],
        "time": supplemental["time"],
    }

    merged = gate._merge_semgrep_reports(
        primary,
        supplemental,
        targets=DOCKERFILE_TARGETS,
        javascript_typescript_config_sha256="a" * 64,
        javascript_typescript_rule_ids=(gate.DOCKERFILE_RULE_ID,),
        supplemental_evidence=evidence,
    )

    assert merged["paths"]["scanned"] == ["app/example.py", *DOCKERFILE_TARGETS]
    assert merged["paths"]["skipped"] == []
    assert merged["results"] == supplemental["results"]
    assert merged["supplemental_scan_evidence"] == [evidence]
    assert primary["paths"]["scanned"] == ["app/example.py"]
    mts_targets = tuple(sorted(gate.REVIEWED_UNIGNORED_MTS_TARGETS))
    mts = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": list(mts_targets), "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    merged_with_mts = gate._merge_semgrep_reports(
        merged,
        mts,
        targets=mts_targets,
        javascript_typescript_config_sha256="c" * 64,
        javascript_typescript_rule_ids=("typescript-rule",),
    )
    assert [item["mode"] for item in merged_with_mts["supplemental_scan_evidence"]] == [
        "canonical-dockerfile-alias",
        "explicit-unknown-extension-typescript",
    ]
    merged_sarif = gate._merge_sarif_reports(
        {"version": "2.1.0", "runs": [{"results": []}]},
        gate._remap_dockerfile_sarif(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "results": [
                            {
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {
                                                "uri": DOCKERFILE_ALIASES[0]
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ],
            },
            DOCKERFILE_ALIAS_TO_SOURCE,
        ),
    )
    assert len(merged_sarif["runs"]) == 2
    assert (
        merged_sarif["runs"][1]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        == DOCKERFILE_TARGETS[0]
    )


def test_dockerfile_sarif_remapping_handles_container_file_uris_and_rejects_others() -> (
    None
):
    report = {
        "version": "2.1.0",
        "runs": [
            {
                "artifacts": [
                    {"location": {"uri": "file:///src/" + DOCKERFILE_ALIASES[0]}}
                ]
            }
        ],
    }

    remapped = gate._remap_dockerfile_sarif(report, DOCKERFILE_ALIAS_TO_SOURCE)

    assert (
        remapped["runs"][0]["artifacts"][0]["location"]["uri"] == DOCKERFILE_TARGETS[0]
    )
    with pytest.raises(gate.SemgrepGateError, match="outside its alias set"):
        gate._remap_dockerfile_sarif(
            {
                "version": "2.1.0",
                "runs": [
                    {"artifacts": [{"location": {"uri": "elsewhere/Dockerfile"}}]}
                ],
            },
            DOCKERFILE_ALIAS_TO_SOURCE,
        )


def test_inline_javascript_slices_are_derived_and_ambiguous_scripts_fail_closed(
    tmp_path: Path,
) -> None:
    source_root, manifest, overlay_hashes = _inline_javascript_fixture(tmp_path)
    targets = gate._inline_javascript_scan_targets(
        source_root, overlay_hashes, manifest, lambda _path: False
    )
    assert tuple(source.path for source in targets) == (
        gate.REVIEWED_INLINE_JAVASCRIPT_PATHS
    )
    for source in targets:
        raw = (source_root / source.path).read_bytes()
        extracted = gate._extract_reviewed_inline_script(raw, source.path)
        assert hashlib.sha256(extracted.view).hexdigest() == source.view_sha256
        assert extracted.byte_start == source.byte_start
        assert extracted.byte_end == source.byte_end
        assert extracted.source_start_line == source.source_start_line
        assert extracted.source_start_column > 1
        assert source.oid == _git_blob_oid(raw)
        assert source.source_sha256 == hashlib.sha256(raw).hexdigest()

    ambiguous = b"<script>x()</script><script>y()</script>"
    with pytest.raises(gate.SemgrepGateError, match="missing or ambiguous"):
        gate._extract_reviewed_inline_script(ambiguous, "fixture.html")


@pytest.mark.parametrize(
    "source",
    [
        b'<script type="application/ld+json">{"ok":true}</script><script>x()</script>',
        b'<script type="application/ecmascript">run()</script>',
        b'<script src=""></script><script>x()</script>',
        b'<script src="/src/main.tsx">window.evasion=true;</script><script>x()</script>',
    ],
)
def test_inline_javascript_parser_rejects_unclassified_script_blocks(
    source: bytes,
) -> None:
    with pytest.raises(gate.SemgrepGateError):
        gate._extract_reviewed_inline_script(source, "fixture.html")


@pytest.mark.parametrize(
    "src",
    [
        "https://cdn.example.test/main.tsx",
        "//cdn.example.test/main.tsx",
        "data:text/javascript,run()",
        "javascript:run()",
        "../src/main.tsx",
    ],
)
def test_inline_external_script_rejects_remote_scheme_and_escape_sources(
    tmp_path: Path, src: str
) -> None:
    html_path = gate.REVIEWED_INLINE_JAVASCRIPT_PATHS[0]
    source_root, manifest, hashes = _inline_javascript_fixture(
        tmp_path,
        {html_path: f'<script src="{src}"></script><script>run()</script>'.encode()},
    )

    with pytest.raises(gate.SemgrepGateError, match="external script src"):
        gate._inline_javascript_scan_targets(
            source_root, hashes, manifest, lambda _path: False
        )


def test_inline_external_script_requires_tracked_unignored_scanned_source(
    tmp_path: Path,
) -> None:
    source_root, manifest, hashes = _inline_javascript_fixture(tmp_path)
    targets = gate._inline_javascript_scan_targets(
        source_root, hashes, manifest, lambda _path: False
    )
    external_paths = {
        path for source in targets for _src, path in source.external_sources
    }
    assert external_paths == {"frontend/src/main.tsx"}
    gate._validate_inline_external_source_coverage(targets, [r"frontend\src\main.tsx"])
    with pytest.raises(gate.SemgrepGateError, match="not covered"):
        gate._validate_inline_external_source_coverage(targets, ["app/example.py"])

    html_path = gate.REVIEWED_INLINE_JAVASCRIPT_PATHS[0]
    missing_source = b'<script src="/src/untracked.tsx"></script><script>run()</script>'
    source_root, manifest, hashes = _inline_javascript_fixture(
        tmp_path / "untracked", {html_path: missing_source}
    )
    with pytest.raises(gate.SemgrepGateError, match="stage-zero identity"):
        gate._inline_javascript_scan_targets(
            source_root, hashes, manifest, lambda _path: False
        )

    source_root, manifest, hashes = _inline_javascript_fixture(tmp_path / "ignored")
    with pytest.raises(gate.SemgrepGateError, match="ignore policy"):
        gate._inline_javascript_scan_targets(
            source_root,
            hashes,
            manifest,
            lambda path: path == "frontend/src/main.tsx",
        )


def test_inline_javascript_data_attributes_do_not_hide_executable_code() -> None:
    extracted = gate._extract_reviewed_inline_script(
        b'<script data-src="/ignored.js">run()</script>', "fixture.html"
    )

    assert extracted.view == b"run()"


def test_inline_javascript_target_selection_binds_exact_index_entries(
    tmp_path: Path,
) -> None:
    source_root, manifest, hashes = _inline_javascript_fixture(tmp_path)
    targets = gate._inline_javascript_scan_targets(
        source_root, hashes, manifest, lambda _path: False
    )
    assert tuple(source.path for source in targets) == (
        gate.REVIEWED_INLINE_JAVASCRIPT_PATHS
    )

    with pytest.raises(gate.SemgrepGateError, match="target set is incomplete"):
        gate._inline_javascript_scan_targets(
            source_root,
            {targets[0].path: hashes[targets[0].path]},
            manifest[:1],
            lambda _path: False,
        )
    with pytest.raises(gate.SemgrepGateError, match="stage-zero identity"):
        gate._inline_javascript_scan_targets(
            source_root,
            hashes,
            [{**manifest[0], "oid": "0" * 40}, manifest[1]],
            lambda _path: False,
        )
    with pytest.raises(gate.SemgrepGateError, match="ignore policy"):
        gate._inline_javascript_scan_targets(
            source_root, hashes, manifest, lambda path: path == targets[0].path
        )


def test_staged_html_edit_derives_and_materializes_fresh_inline_source_identity(
    tmp_path: Path,
) -> None:
    path = gate.REVIEWED_INLINE_JAVASCRIPT_PATHS[0]
    original = (REPOSITORY_ROOT / path).read_bytes()
    close_tag = original.index(b"</script>")
    addition = b"\nwindow.__staged_html_edit__ = true;\n"
    edited = original[:close_tag] + addition + original[close_tag:]
    source_root, manifest, overlay_hashes = _inline_javascript_fixture(
        tmp_path, {path: edited}
    )
    targets = gate._inline_javascript_scan_targets(
        source_root, overlay_hashes, manifest, lambda _path: False
    )
    source = targets[0]
    assert source.path == path
    assert source.oid == _git_blob_oid(edited)
    assert source.source_sha256 == hashlib.sha256(edited).hexdigest()
    assert source.byte_end - source.byte_start == source.view_byte_length
    assert (
        source.view_sha256
        != hashlib.sha256(
            gate._extract_reviewed_inline_script(original, path).view
        ).hexdigest()
    )

    snapshot_sha256 = _snapshot_manifest_sha256(manifest)
    aliases, _bindings, mapping_sha256 = gate._materialize_inline_javascript_inputs(
        source_root=source_root,
        destination=tmp_path / "aliases",
        targets=targets,
        source_manifest=manifest,
        overlay_target_hashes=overlay_hashes,
        mapping_manifest_path=tmp_path / "inline-inputs.json",
        source_snapshot_manifest_sha256=snapshot_sha256,
        ignore_matcher=lambda _path: False,
    )
    alias_bytes = (tmp_path / "aliases" / aliases[0]).read_bytes()
    assert addition.strip() in alias_bytes
    mapping = json.loads((tmp_path / "inline-inputs.json").read_text("utf-8"))
    assert mapping["source_snapshot_manifest_sha256"] == snapshot_sha256
    assert mapping["targets"][0]["oid"] == source.oid
    assert mapping["targets"][0]["source_sha256"] == source.source_sha256
    assert mapping["targets"][0]["view_sha256"] == source.view_sha256
    assert mapping["targets"][0]["external_sources"] == [
        {"src": "/src/main.tsx", "path": "frontend/src/main.tsx"}
    ]
    gate._verify_inline_javascript_inputs(
        source_root=source_root,
        destination=tmp_path / "aliases",
        targets=targets,
        source_manifest=manifest,
        overlay_target_hashes=overlay_hashes,
        source_snapshot_manifest_sha256=snapshot_sha256,
        mapping_manifest_path=tmp_path / "inline-inputs.json",
        expected_mapping_manifest_sha256=mapping_sha256,
        ignore_matcher=lambda _path: False,
    )


@pytest.mark.parametrize("mutation", ["source", "alias", "manifest"])
def test_inline_javascript_per_run_bindings_reject_snapshot_or_view_drift(
    tmp_path: Path, mutation: str
) -> None:
    source_root, manifest, overlay_hashes = _inline_javascript_fixture(tmp_path)
    targets = gate._inline_javascript_scan_targets(
        source_root, overlay_hashes, manifest, lambda _path: False
    )
    snapshot_sha256 = _snapshot_manifest_sha256(manifest)
    aliases, _bindings, mapping_sha256 = gate._materialize_inline_javascript_inputs(
        source_root=source_root,
        destination=tmp_path / "aliases",
        targets=targets,
        source_manifest=manifest,
        overlay_target_hashes=overlay_hashes,
        mapping_manifest_path=tmp_path / "inline-inputs.json",
        source_snapshot_manifest_sha256=snapshot_sha256,
        ignore_matcher=lambda _path: False,
    )
    if mutation == "source":
        source_path = source_root / targets[0].path
        source_path.write_bytes(source_path.read_bytes() + b"<!-- drift -->")
    elif mutation == "alias":
        alias_path = tmp_path / "aliases" / aliases[0]
        alias_path.write_bytes(alias_path.read_bytes() + b"\n// drift\n")
    else:
        mapping_path = tmp_path / "inline-inputs.json"
        mapping_path.write_bytes(mapping_path.read_bytes() + b" ")

    with pytest.raises(gate.SemgrepGateError):
        gate._verify_inline_javascript_inputs(
            source_root=source_root,
            destination=tmp_path / "aliases",
            targets=targets,
            source_manifest=manifest,
            overlay_target_hashes=overlay_hashes,
            source_snapshot_manifest_sha256=snapshot_sha256,
            mapping_manifest_path=tmp_path / "inline-inputs.json",
            expected_mapping_manifest_sha256=mapping_sha256,
            ignore_matcher=lambda _path: False,
        )


def test_javascript_rule_projection_rejects_path_filters(tmp_path: Path) -> None:
    selected = tmp_path / "selected.json"
    projected = tmp_path / "mts.json"
    selected.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        **JAVASCRIPT_RULE,
                        "paths": {"include": [".github/workflows/**"]},
                    },
                    TYPESCRIPT_RULE,
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(gate.SemgrepGateError, match="path filter"):
        gate._write_mts_rules_config(selected, projected)


def test_inline_javascript_report_remaps_html_lines_and_sarif_regions(
    tmp_path: Path,
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    report = _inline_javascript_report(aliases)
    gate._validate_inline_javascript_supplement_report(
        report,
        aliases,
        bindings,
        (JAVASCRIPT_RULE["id"],),
    )
    remapped = gate._remap_inline_javascript_report(report, bindings)
    first_source = bindings[aliases[0]]
    assert remapped["paths"]["scanned"] == [
        source_path for source_path in gate.REVIEWED_INLINE_JAVASCRIPT_PATHS
    ]
    assert remapped["results"][0]["path"] == first_source.path
    assert remapped["results"][0]["start"] == {
        "line": first_source.source_start_line + 1,
        "col": 9,
        "offset": first_source.source_byte_start + 9,
    }

    raw_sarif = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [
                            {"id": "out." + JAVASCRIPT_RULE["id"]},
                            {"id": "out." + TYPESCRIPT_RULE["id"]},
                        ]
                    }
                },
                "artifacts": [{"location": {"uri": alias}} for alias in aliases],
                "results": [
                    {
                        "ruleId": "out." + JAVASCRIPT_RULE["id"],
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": aliases[0]},
                                    "region": {
                                        "startLine": 2,
                                        "startColumn": 9,
                                        "endLine": 2,
                                        "endColumn": 15,
                                        "byteOffset": 9,
                                        "byteLength": 6,
                                        "charOffset": 9,
                                        "charLength": 6,
                                    },
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
    remapped_sarif = gate._remap_inline_javascript_sarif(
        raw_sarif,
        bindings,
        (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
        (JAVASCRIPT_RULE["id"],),
    )
    region = remapped_sarif["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["region"]
    assert region == {
        "startLine": first_source.source_start_line + 1,
        "startColumn": 9,
        "endLine": first_source.source_start_line + 1,
        "endColumn": 15,
        "byteOffset": first_source.source_byte_start + 9,
        "byteLength": 6,
        "charOffset": first_source.source_char_start + 9,
        "charLength": 6,
    }
    assert remapped_sarif["runs"][0]["artifacts"][0]["location"]["uri"] == (
        first_source.path
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-target", "exact target set"),
        ("extra-target", "exact target set"),
        ("skipped-target", "skipped a target"),
        ("error", "reported diagnostics"),
        ("skipped-rule", "skipped rules"),
        ("timeout", "timed-out analysis"),
        ("outside-path", "outside its exact alias set"),
        ("wrong-rule", "outside the selected rules"),
        ("missing-namespace", "outside the selected rules"),
        ("wrong-namespace", "outside the selected rules"),
        ("outside-position", "outside its slice"),
        ("unbounded-column", "outside its slice"),
        ("column-offset-mismatch", "disagrees with its byte offset"),
        ("line-offset-mismatch", "disagrees with its byte offset"),
    ],
)
def test_inline_javascript_report_rejects_missing_or_out_of_scope_evidence(
    tmp_path: Path, mutation: str, message: str
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    report = _inline_javascript_report(aliases)
    if mutation == "missing-target":
        report["paths"]["scanned"].pop()
    elif mutation == "extra-target":
        report["paths"]["scanned"].append("target-02/inline.js")
    elif mutation == "skipped-target":
        report["paths"]["skipped"].append(
            {"path": aliases[0], "reason": "exceeded_size_limit"}
        )
    elif mutation == "error":
        report["errors"].append({"type": "PartialParsing"})
    elif mutation == "skipped-rule":
        report["skipped_rules"].append({"rule_id": "rule"})
    elif mutation == "timeout":
        report["time"]["fixpoint_timeouts"].append({"rule": "rule"})
    elif mutation == "outside-path":
        report["results"][0]["path"] = "target-02/inline.js"
    elif mutation == "wrong-rule":
        report["results"][0]["check_id"] = "out.unselected.rule"
    elif mutation == "missing-namespace":
        report["results"][0]["check_id"] = JAVASCRIPT_RULE["id"]
    elif mutation == "wrong-namespace":
        report["results"][0]["check_id"] = "rules." + JAVASCRIPT_RULE["id"]
    elif mutation == "outside-position":
        report["results"][0]["end"]["offset"] = (
            bindings[aliases[0]].view_byte_length + 1
        )
    elif mutation == "unbounded-column":
        report["results"][0]["start"]["col"] = 99999
    elif mutation == "column-offset-mismatch":
        report["results"][0]["start"]["col"] += 1
    else:
        report["results"][0]["start"]["line"] += 1

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._validate_inline_javascript_supplement_report(
            report, aliases, bindings, (JAVASCRIPT_RULE["id"],)
        )


def test_inline_javascript_sarif_rejects_wrong_rules_and_artifacts(
    tmp_path: Path,
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    sarif = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [
                            {"id": "out." + JAVASCRIPT_RULE["id"]},
                            {"id": "out." + TYPESCRIPT_RULE["id"]},
                        ]
                    }
                },
                "artifacts": [],
                "results": [
                    {
                        "ruleId": "out." + JAVASCRIPT_RULE["id"],
                        "ruleIndex": 0,
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": aliases[0]},
                                    "region": {"startLine": 2},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
    bad_rule = json.loads(json.dumps(sarif))
    bad_rule["runs"][0]["results"][0]["ruleId"] = "out.unselected"
    with pytest.raises(gate.SemgrepGateError, match="outside the selected rules"):
        gate._remap_inline_javascript_sarif(
            bad_rule,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    wrong_namespace = json.loads(json.dumps(sarif))
    wrong_namespace["runs"][0]["results"][0]["ruleId"] = (
        "rules." + JAVASCRIPT_RULE["id"]
    )
    with pytest.raises(gate.SemgrepGateError, match="outside the selected rules"):
        gate._remap_inline_javascript_sarif(
            wrong_namespace,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    missing_namespace = json.loads(json.dumps(sarif))
    missing_namespace["runs"][0]["results"][0]["ruleId"] = JAVASCRIPT_RULE["id"]
    with pytest.raises(gate.SemgrepGateError, match="outside the selected rules"):
        gate._remap_inline_javascript_sarif(
            missing_namespace,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    mismatched_rule_index = json.loads(json.dumps(sarif))
    mismatched_rule_index["runs"][0]["results"][0]["ruleIndex"] = 1
    with pytest.raises(gate.SemgrepGateError, match="outside the selected rules"):
        gate._remap_inline_javascript_sarif(
            mismatched_rule_index,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    duplicate_driver_rule = json.loads(json.dumps(sarif))
    duplicate_driver_rule["runs"][0]["tool"]["driver"]["rules"].append(
        {"id": "out." + JAVASCRIPT_RULE["id"]}
    )
    with pytest.raises(gate.SemgrepGateError, match="rules differ"):
        gate._remap_inline_javascript_sarif(
            duplicate_driver_rule,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    non_string_driver_rule = json.loads(json.dumps(sarif))
    non_string_driver_rule["runs"][0]["tool"]["driver"]["rules"][0]["id"] = None
    with pytest.raises(gate.SemgrepGateError, match="rules differ"):
        gate._remap_inline_javascript_sarif(
            non_string_driver_rule,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    missing_artifact_inventory = _inline_javascript_sarif_fixture(aliases)
    missing_artifact_inventory["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["artifactLocation"]["index"] = 0
    del missing_artifact_inventory["runs"][0]["artifacts"]
    with pytest.raises(gate.SemgrepGateError, match="index has no exact inventory"):
        gate._remap_inline_javascript_sarif(
            missing_artifact_inventory,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    contradictory_artifact_reference = _inline_javascript_sarif_fixture(aliases)
    contradictory_artifact_reference["runs"][0]["artifacts"] = [
        {"location": {"uri": aliases[1]}}
    ]
    contradictory_artifact_reference["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["artifactLocation"]["index"] = 0
    with pytest.raises(gate.SemgrepGateError, match="contradicts its index"):
        gate._remap_inline_javascript_sarif(
            contradictory_artifact_reference,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    direct_uri_base = _inline_javascript_sarif_fixture(aliases)
    direct_uri_base["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "artifactLocation"
    ]["uriBaseId"] = "%SRCROOT%"
    with pytest.raises(gate.SemgrepGateError, match="URI base is unsupported"):
        gate._remap_inline_javascript_sarif(
            direct_uri_base,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    indexed_uri_base = _inline_javascript_sarif_fixture(aliases)
    indexed_artifact = indexed_uri_base["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["artifactLocation"]
    indexed_artifact["index"] = 0
    indexed_artifact["uriBaseId"] = "%SRCROOT%"
    with pytest.raises(gate.SemgrepGateError, match="URI base is unsupported"):
        gate._remap_inline_javascript_sarif(
            indexed_uri_base,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    artifact_table_uri_base = _inline_javascript_sarif_fixture(aliases)
    artifact_table_uri_base["runs"][0]["artifacts"] = [
        {"location": {"uri": aliases[0], "uriBaseId": "%SRCROOT%"}}
    ]
    artifact_table_uri_base["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["artifactLocation"]["index"] = 0
    with pytest.raises(gate.SemgrepGateError, match="URI base is unsupported"):
        gate._remap_inline_javascript_sarif(
            artifact_table_uri_base,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )

    bad_path = json.loads(json.dumps(sarif))
    bad_path["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "artifactLocation"
    ]["uri"] = "other/file.js"
    with pytest.raises(gate.SemgrepGateError, match="outside its alias set"):
        gate._remap_inline_javascript_sarif(
            bad_path,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )


def _inline_javascript_sarif_fixture(aliases: tuple[str, ...]) -> dict[str, Any]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [
                            {"id": "out." + JAVASCRIPT_RULE["id"]},
                            {"id": "out." + TYPESCRIPT_RULE["id"]},
                        ]
                    }
                },
                "artifacts": [{"location": {"uri": alias}} for alias in aliases],
                "results": [
                    {
                        "ruleId": "out." + JAVASCRIPT_RULE["id"],
                        "ruleIndex": 0,
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": aliases[0]},
                                    "region": {
                                        "startLine": 2,
                                        "startColumn": 9,
                                        "endLine": 2,
                                        "endColumn": 15,
                                        "byteOffset": 9,
                                        "byteLength": 6,
                                        "charOffset": 9,
                                        "charLength": 6,
                                    },
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    ["missing-rule", "extra-rule", "wrong-namespace", "missing-namespace"],
)
def test_inline_javascript_sarif_requires_exact_out_namespaced_inventory(
    tmp_path: Path, mutation: str
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    sarif = _inline_javascript_sarif_fixture(aliases)
    rules = sarif["runs"][0]["tool"]["driver"]["rules"]
    if mutation == "missing-rule":
        rules.pop()
    elif mutation == "extra-rule":
        rules.append({"id": "out.unselected.rule"})
    elif mutation == "wrong-namespace":
        rules[0]["id"] = "rules." + JAVASCRIPT_RULE["id"]
    else:
        rules[0]["id"] = JAVASCRIPT_RULE["id"]

    with pytest.raises(
        gate.SemgrepGateError,
        match="rules differ from the selected config",
    ):
        gate._remap_inline_javascript_sarif(
            sarif,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unbounded-column", "column is outside its slice"),
        ("reversed-coordinates", "region is reversed"),
        ("byte-range-escape", "byte range is outside its slice"),
        ("character-range-escape", "char range is outside its slice"),
        ("byte-range-mismatch", "byte range disagrees with coordinates"),
        ("character-offset-mismatch", "char range disagrees with coordinates"),
        ("missing-end-column", "column is malformed"),
        ("missing-byte-length", "byte range is malformed"),
        ("incomplete-location", "location is incomplete"),
    ],
)
def test_inline_javascript_sarif_rejects_unbounded_or_inconsistent_ranges(
    tmp_path: Path, mutation: str, message: str
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    sarif = _inline_javascript_sarif_fixture(aliases)
    region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "region"
    ]
    if mutation == "unbounded-column":
        region["startColumn"] = 99999
    elif mutation == "reversed-coordinates":
        region["endColumn"] = 8
    elif mutation == "byte-range-escape":
        region["byteLength"] = bindings[aliases[0]].view_byte_length + 1
    elif mutation == "character-range-escape":
        region["charLength"] = bindings[aliases[0]].view_char_length + 1
    elif mutation == "byte-range-mismatch":
        region["byteLength"] = 5
    elif mutation == "character-offset-mismatch":
        region["charOffset"] = 11
    elif mutation == "missing-end-column":
        del region["endColumn"]
    elif mutation == "missing-byte-length":
        del region["byteLength"]
    else:
        del sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._remap_inline_javascript_sarif(
            sarif,
            bindings,
            (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
            (JAVASCRIPT_RULE["id"],),
        )


def test_inline_javascript_sarif_allows_no_artifacts_when_findings_are_empty(
    tmp_path: Path,
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    sarif = _inline_javascript_sarif_fixture(aliases)
    sarif["runs"][0]["artifacts"] = []
    sarif["runs"][0]["results"] = []

    remapped = gate._remap_inline_javascript_sarif(
        sarif,
        bindings,
        (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
        (JAVASCRIPT_RULE["id"],),
    )

    assert remapped["runs"][0]["artifacts"] == []
    assert remapped["runs"][0]["results"] == []

    omitted_empty_artifacts = json.loads(json.dumps(sarif))
    del omitted_empty_artifacts["runs"][0]["artifacts"]
    remapped_without_artifacts = gate._remap_inline_javascript_sarif(
        omitted_empty_artifacts,
        bindings,
        (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
        (JAVASCRIPT_RULE["id"],),
    )
    assert "artifacts" not in remapped_without_artifacts["runs"][0]


def test_inline_javascript_sarif_accepts_exact_direct_uri_without_artifact_table(
    tmp_path: Path,
) -> None:
    _source_root, aliases, bindings, _mapping_hash = (
        _materialized_inline_javascript_fixture(tmp_path)
    )
    sarif = _inline_javascript_sarif_fixture(aliases)
    del sarif["runs"][0]["artifacts"]

    remapped = gate._remap_inline_javascript_sarif(
        sarif,
        bindings,
        (JAVASCRIPT_RULE["id"], TYPESCRIPT_RULE["id"]),
        (JAVASCRIPT_RULE["id"],),
    )

    physical_location = remapped["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]
    assert physical_location["artifactLocation"]["uri"] == bindings[aliases[0]].path
    assert physical_location["region"]["startLine"] == (
        bindings[aliases[0]].source_start_line + 1
    )


def test_run_gate_executes_and_merges_the_four_path_dockerfile_supplement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    monkeypatch.setattr(
        gate, "_validate_semgrep_ignore_policy", lambda _root: lambda _path: False
    )
    index_blobs = {
        relative: (repository_root / relative).read_bytes()
        for relative in TRACKED_PATHS
    }
    for relative in DOCKERFILE_TARGETS:
        source = repository_root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("FROM alpine:3.20\n", encoding="utf-8", newline="\n")
        index_blobs[relative] = source.read_bytes()
    selected_config = {"rules": [DOCKERFILE_RULE]}
    runner, calls, snapshots = _runner_for_scan(
        repository_root,
        index_blobs=index_blobs,
        selected_config=selected_config,
    )
    reports = tmp_path / "reports"
    result = gate.run_gate(
        TEST_IMAGE,
        repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
        output_directory=reports,
    )

    assert result == 0
    scans = [call for call in calls if call[:2] == ["docker", "run"]]
    assert len(scans) == 2
    dockerfile_scan = scans[1]
    assert dockerfile_scan[dockerfile_scan.index("--config") + 1] == (
        "/out/security-rules-dockerfile.json"
    )
    assert "--scan-unknown-extensions" not in dockerfile_scan
    assert dockerfile_scan[-len(DOCKERFILE_ALIASES) :] == list(DOCKERFILE_ALIASES)
    assert "--cpus=2" in dockerfile_scan and "--memory=3g" in dockerfile_scan
    assert runner.scan_timeouts == [gate.SCAN_TIMEOUT_SECONDS, 60]
    assert snapshots[1] == list(DOCKERFILE_ALIASES)
    projected = json.loads(
        (reports / "security-rules-dockerfile.json").read_text("utf-8")
    )
    assert projected == {"rules": [DOCKERFILE_RULE]}
    input_manifest = json.loads(
        (reports / "semgrep-dockerfile-inputs.json").read_text("utf-8")
    )
    assert [item["alias"] for item in input_manifest["targets"]] == list(
        DOCKERFILE_ALIASES
    )
    assert [item["path"] for item in input_manifest["targets"]] == list(
        DOCKERFILE_TARGETS
    )
    for item in input_manifest["targets"]:
        source_bytes = index_blobs[item["path"]]
        assert item["oid"] == _git_blob_oid(source_bytes)
        assert item["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    dockerfile_raw = json.loads(
        (reports / "semgrep-dockerfile-raw.json").read_text("utf-8")
    )
    assert [
        path.replace("\\", "/") for path in dockerfile_raw["paths"]["scanned"]
    ] == list(DOCKERFILE_ALIASES)
    dockerfile_remapped = json.loads(
        (reports / "semgrep-dockerfile.json").read_text("utf-8")
    )
    assert dockerfile_remapped["paths"]["scanned"] == list(DOCKERFILE_TARGETS)
    sarif_remapped = json.loads(
        (reports / "semgrep-dockerfile.sarif").read_text("utf-8")
    )
    assert (
        sarif_remapped["runs"][0]["artifacts"][0]["location"]["uri"]
        == (DOCKERFILE_TARGETS[0])
    )
    merged = json.loads((reports / "semgrep.json").read_text("utf-8"))
    assert set(merged["paths"]["scanned"]) == {
        "app/example.py",
        *DOCKERFILE_TARGETS,
    }
    assert merged["results"][0]["path"].replace("\\", "/") == DOCKERFILE_TARGETS[0]
    assert merged["supplemental_scan_evidence"][0]["targets"] == list(
        DOCKERFILE_TARGETS
    )
    assert len(json.loads((reports / "semgrep.sarif").read_text("utf-8"))["runs"]) == 2


def test_run_gate_scans_current_staged_inline_javascript_slices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    monkeypatch.setattr(
        gate, "_validate_semgrep_ignore_policy", lambda _root: lambda _path: False
    )
    index_blobs = {
        relative: (repository_root / relative).read_bytes()
        for relative in TRACKED_PATHS
    }
    staged_edit_path = gate.REVIEWED_INLINE_JAVASCRIPT_PATHS[0]
    staged_original = (REPOSITORY_ROOT / staged_edit_path).read_bytes()
    staged_close = staged_original.index(b"</script>")
    staged_addition = b"\nwindow.__staged_source_scan__ = true;\n"
    staged_edited = (
        staged_original[:staged_close]
        + staged_addition
        + staged_original[staged_close:]
    )
    for path in gate.REVIEWED_INLINE_JAVASCRIPT_PATHS:
        content = (
            staged_edited
            if path == staged_edit_path
            else (REPOSITORY_ROOT / path).read_bytes()
        )
        target = repository_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        index_blobs[path] = content
    main_source_path = "frontend/src/main.tsx"
    main_source = (REPOSITORY_ROOT / main_source_path).read_bytes()
    main_target = repository_root / main_source_path
    main_target.parent.mkdir(parents=True, exist_ok=True)
    main_target.write_bytes(main_source)
    index_blobs[main_source_path] = main_source
    selected_config = {"rules": [DOCKERFILE_RULE, JAVASCRIPT_RULE, TYPESCRIPT_RULE]}
    runner, calls, snapshots = _runner_for_scan(
        repository_root,
        index_blobs=index_blobs,
        selected_config=selected_config,
    )
    reports = tmp_path / "reports"
    result = gate.run_gate(
        TEST_IMAGE,
        repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
        output_directory=reports,
    )

    assert result == 0
    scans = [call for call in calls if call[:2] == ["docker", "run"]]
    assert len(scans) == 2
    inline_scan = scans[1]
    assert inline_scan[inline_scan.index("--config") + 1] == (
        "/out/security-rules-mts.json"
    )
    assert "--scan-unknown-extensions" not in inline_scan
    assert inline_scan[-len(gate.INLINE_JAVASCRIPT_ALIASES) :] == list(
        gate.INLINE_JAVASCRIPT_ALIASES
    )
    assert runner.scan_timeouts == [gate.SCAN_TIMEOUT_SECONDS, 60]
    assert snapshots[1] == list(gate.INLINE_JAVASCRIPT_ALIASES)
    inline_manifest = json.loads(
        (reports / "semgrep-inline-js-inputs.json").read_text("utf-8")
    )
    snapshot_manifest_bytes = (reports / "semgrep-targets.json").read_bytes()
    assert (
        inline_manifest["source_snapshot_manifest_sha256"]
        == hashlib.sha256(snapshot_manifest_bytes).hexdigest()
    )
    assert [entry["alias"] for entry in inline_manifest["targets"]] == list(
        gate.INLINE_JAVASCRIPT_ALIASES
    )
    assert [entry["path"] for entry in inline_manifest["targets"]] == list(
        gate.REVIEWED_INLINE_JAVASCRIPT_PATHS
    )
    first_entry = inline_manifest["targets"][0]
    assert first_entry["oid"] == _git_blob_oid(staged_edited)
    assert first_entry["source_sha256"] == hashlib.sha256(staged_edited).hexdigest()
    staged_view = gate._extract_reviewed_inline_script(
        staged_edited, staged_edit_path
    ).view
    assert staged_addition.strip() in staged_view
    assert first_entry["view_sha256"] == hashlib.sha256(staged_view).hexdigest()
    inline_raw = json.loads((reports / "semgrep-inline-js-raw.json").read_text("utf-8"))
    assert [path.replace("\\", "/") for path in inline_raw["paths"]["scanned"]] == list(
        gate.INLINE_JAVASCRIPT_ALIASES
    )
    inline_report = json.loads((reports / "semgrep-inline-js.json").read_text("utf-8"))
    first_source = inline_manifest["targets"][0]
    assert inline_report["paths"]["scanned"] == [
        path for path in gate.REVIEWED_INLINE_JAVASCRIPT_PATHS
    ]
    assert inline_report["results"][0]["path"] == first_source["path"]
    assert inline_report["results"][0]["start"]["line"] == (
        first_source["source_start_line"] + 1
    )
    assert inline_report["results"][0]["start"]["offset"] == (
        first_source["source_byte_start"] + 9
    )
    merged = json.loads((reports / "semgrep.json").read_text("utf-8"))
    assert set(merged["paths"]["scanned"]) == {
        "app/example.py",
        "frontend/src/main.tsx",
        *gate.REVIEWED_INLINE_JAVASCRIPT_PATHS,
    }
    assert [item["mode"] for item in merged["supplemental_scan_evidence"]] == [
        "inline-javascript-source-slice"
    ]
    assert len(json.loads((reports / "semgrep.sarif").read_text("utf-8"))["runs"]) == 2


def test_run_gate_rechecks_inline_source_binding_after_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    monkeypatch.setattr(
        gate, "_validate_semgrep_ignore_policy", lambda _root: lambda _path: False
    )
    index_blobs = {
        relative: (repository_root / relative).read_bytes()
        for relative in TRACKED_PATHS
    }
    for path in gate.REVIEWED_INLINE_JAVASCRIPT_PATHS:
        content = (REPOSITORY_ROOT / path).read_bytes()
        target = repository_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        index_blobs[path] = content
    main_source_path = "frontend/src/main.tsx"
    main_source = (REPOSITORY_ROOT / main_source_path).read_bytes()
    main_target = repository_root / main_source_path
    main_target.parent.mkdir(parents=True, exist_ok=True)
    main_target.write_bytes(main_source)
    index_blobs[main_source_path] = main_source
    runner, _calls, _snapshots = _runner_for_scan(
        repository_root,
        index_blobs=index_blobs,
        selected_config={"rules": [DOCKERFILE_RULE, JAVASCRIPT_RULE, TYPESCRIPT_RULE]},
    )
    docker_scan = gate._docker_scan

    def mutate_inline_alias_after_scan(**kwargs: Any) -> int:
        status = docker_scan(**kwargs)
        if kwargs.get("scan_id") == "semgrep-inline-js":
            alias = kwargs["scan_root"] / gate.INLINE_JAVASCRIPT_ALIASES[0]
            alias.write_bytes(alias.read_bytes() + b"\n// altered after scan\n")
        return status

    monkeypatch.setattr(gate, "_docker_scan", mutate_inline_alias_after_scan)
    with pytest.raises(
        gate.SemgrepGateError, match="parser alias differs from its source"
    ):
        gate.run_gate(
            TEST_IMAGE,
            repository_root,
            command_runner=runner,
            temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
            output_directory=tmp_path / "reports",
        )


def _blob_snapshot_runner(
    blobs: dict[str, bytes],
) -> Any:
    _records, index_output = _index_records(blobs)

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if command[:4] == ["git", "ls-files", "--stage", "-z"]:
            return _completed(command, stdout=index_output)
        if command[:3] == ["git", "cat-file", "--batch"]:
            requested = kwargs["input"].decode("ascii").splitlines()
            return _completed(command, stdout=_cat_file_output(requested, blobs))
        raise AssertionError(f"unexpected command: {command!r}")

    return run


def test_snapshot_uses_staged_blob_and_ignores_cross_api_ctime_variance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged_content = b"eval(input())\n"
    worktree_content = b"value = 'benign'\n"
    blobs = {
        ".semgrepignore": b"tests/\n",
        "app/example.py": staged_content,
    }
    source = tmp_path / "app" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(worktree_content)
    runner = _blob_snapshot_runner(blobs)
    real_lstat = Path.lstat
    real_fstat = os.fstat
    metadata_calls: list[str] = []
    actual = source.stat()

    def fake_lstat(path: Path) -> Any:
        if path == source:
            metadata_calls.append("lstat")
            return SimpleNamespace(
                st_dev=actual.st_dev,
                st_ino=actual.st_ino,
                st_mode=actual.st_mode,
                st_size=actual.st_size,
                st_mtime_ns=actual.st_mtime_ns,
                st_ctime_ns=actual.st_ctime_ns + 101,
            )
        return real_lstat(path)

    def fake_fstat(descriptor: int) -> Any:
        metadata_calls.append("fstat")
        stat_result = real_fstat(descriptor)
        return SimpleNamespace(
            st_dev=stat_result.st_dev,
            st_ino=stat_result.st_ino,
            st_mode=stat_result.st_mode,
            st_size=stat_result.st_size,
            st_mtime_ns=stat_result.st_mtime_ns,
            st_ctime_ns=stat_result.st_ctime_ns + 202,
        )

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(os, "fstat", fake_fstat)
    destination = tmp_path / "snapshot"
    scan_root, manifest, entries = gate._create_scan_snapshot(
        tmp_path, destination, command_runner=runner
    )

    assert (scan_root / "app" / "example.py").read_bytes() == staged_content
    assert (scan_root / "app" / "example.py").read_bytes() != worktree_content
    assert not metadata_calls
    app_entry = next(item for item in manifest if item["path"] == "app/example.py")
    assert app_entry["oid"] == _git_blob_oid(staged_content)
    assert app_entry["sha256"] == hashlib.sha256(staged_content).hexdigest()
    assert [entry.path.as_posix() for entry in entries] == [
        ".semgrepignore",
        "app/example.py",
    ]


def test_index_blob_snapshot_keeps_a_staged_file_missing_from_worktree(
    tmp_path: Path,
) -> None:
    content = b"value = True\n"
    blobs = {".semgrepignore": b"tests/\n", "app/staged.py": content}
    scan_root, manifest, _entries = gate._create_scan_snapshot(
        tmp_path,
        tmp_path / "snapshot",
        command_runner=_blob_snapshot_runner(blobs),
    )

    assert not (tmp_path / "app" / "staged.py").exists()
    assert (scan_root / "app" / "staged.py").read_bytes() == content
    assert any(item["path"] == "app/staged.py" for item in manifest)


@pytest.mark.parametrize(
    ("mode", "stage", "message"),
    [
        ("120000", 0, "unsupported file mode"),
        ("160000", 0, "unsupported file mode"),
        ("100644", 2, "unresolved merge entry"),
    ],
)
def test_index_rejects_nonregular_and_unmerged_entries(
    tmp_path: Path,
    mode: str,
    stage: int,
    message: str,
) -> None:
    content = b"tests/\n"
    oid = _git_blob_oid(content)
    output = f"{mode} {oid} {stage}\t.semgrepignore\0".encode("ascii")

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._read_index_entries(
            tmp_path,
            command_runner=lambda command, **_kwargs: _completed(
                command, stdout=output
            ),
        )


def test_index_rejects_nested_semgrepignore(tmp_path: Path) -> None:
    blobs = {
        ".semgrepignore": b"tests/\n",
        "app/.semgrepignore": b"generated/\n",
    }
    runner = _blob_snapshot_runner(blobs)

    with pytest.raises(gate.SemgrepGateError, match="nested Semgrep ignore files"):
        gate._read_index_entries(tmp_path, command_runner=runner)


def test_index_rejects_case_distinct_paths_that_alias_on_windows(
    tmp_path: Path,
) -> None:
    blobs = {
        ".semgrepignore": b"tests/\n",
        "app/Vulnerable.py": b"eval(input())\n",
        "app/vulnerable.py": b"pass\n",
    }
    runner = _blob_snapshot_runner(blobs)

    with pytest.raises(gate.SemgrepGateError, match="collide on Windows"):
        gate._read_index_entries(tmp_path, command_runner=runner)


def test_index_rejects_cat_file_bytes_that_do_not_match_the_index_oid(
    tmp_path: Path,
) -> None:
    indexed = {".semgrepignore": b"tests/\n"}
    _records, index_output = _index_records(indexed)

    def runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if command[:4] == ["git", "ls-files", "--stage", "-z"]:
            return _completed(command, stdout=index_output)
        if command[:3] == ["git", "cat-file", "--batch"]:
            requested_oid = next(iter(indexed.values()))
            object_id = _git_blob_oid(requested_oid)
            fake_content = b"different bytes\n"
            return _completed(
                command,
                stdout=(
                    f"{object_id} blob {len(fake_content)}\n".encode("ascii")
                    + fake_content
                    + b"\n"
                ),
            )
        raise AssertionError(f"unexpected command: {command!r}")

    with pytest.raises(gate.SemgrepGateError, match="wrong object id"):
        gate._create_scan_snapshot(
            tmp_path, tmp_path / "snapshot", command_runner=runner
        )


def test_index_change_during_scan_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    _commit, rules_root = _prepare_repository(repository_root, monkeypatch)
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda _commit, _destination, *, command_runner: rules_root,
    )
    _stub_ignore_validator(monkeypatch)
    runner, calls, _snapshots = _runner_for_scan(
        repository_root, mutate_index_after_scan=True
    )
    report_directory = tmp_path / "reports"

    result = gate.main(
        [TEST_IMAGE, "--output-directory", str(report_directory)],
        repository_root=repository_root,
        command_runner=runner,
        temporary_parent=_private_temporary_parent(tmp_path, monkeypatch),
    )

    assert result == 1
    assert not any(
        any(token.endswith("semgrep_dispositions_gate.py") for token in call)
        for call in calls
    )
    consistency = json.loads(
        (report_directory / "semgrep-targets-consistency.json").read_text(
            encoding="utf-8"
        )
    )
    assert consistency["status"] == "mismatch"
    assert consistency["changed_paths"] == ["app/example.py"]
