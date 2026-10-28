"""Parsed contracts for the canonical Chaos app-lane runtime and safety gates."""

import asyncio
import hashlib
import json
import logging
import shlex
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType, SimpleNamespace
from typing import Any, cast

import pytest
import yaml

from scripts.chaos import run_chaos_loadtest as chaos

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/nightly-full-gate.yml"
)
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"


def _job() -> dict[str, Any]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document["jobs"]["chaos-tests"])


def test_chaos_job_is_main_only_and_fail_closed() -> None:
    job = _job()
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 30
    assert job["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])


def test_chaos_installs_pinned_python_before_dependency_sync() -> None:
    steps = _job()["steps"]
    setup = [
        step
        for step in steps
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup) == 1
    assert setup[0]["uses"] == SETUP_PYTHON
    assert setup[0]["with"]["python-version"] == "3.14"
    assert "if" not in setup[0]
    assert "continue-on-error" not in setup[0]
    sync = next(step for step in steps if step.get("name") == "Install dependencies")
    assert sync["run"] == "uv sync --frozen --group dev"
    assert steps.index(setup[0]) < steps.index(sync)


def test_chaos_uses_pinned_minio_and_toxiproxy_services() -> None:
    job = _job()
    services = job["services"]
    assert set(services) == {"minio", "toxiproxy"}

    minio = services["minio"]
    assert "@sha256:" in minio["image"]
    assert minio["command"] == "mini -dir=/data -s3.port=9000"
    assert minio["ports"] == ["9000:9000"]

    toxiproxy = services["toxiproxy"]
    assert "@sha256:" in toxiproxy["image"]
    assert toxiproxy["ports"] == ["8474:8474", "9003:9003"]


def test_chaos_configures_proxy_before_fail_closed_tests_and_keeps_reset_safety() -> (
    None
):
    job = _job()
    assert job["env"]["DATABASE_URL"] == "sqlite+aiosqlite:///./test_chaos.db"
    assert job["env"]["UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"] == "1"
    steps = job["steps"]
    configure = next(
        step for step in steps if step.get("name") == "Configure ToxiProxy proxies"
    )
    assert "for _attempt in {1..30}" in configure["run"]
    assert "curl --fail --silent http://localhost:9000/status" in configure["run"]
    assert "--request POST http://localhost:8474/proxies" in configure["run"]

    tests = next(step for step in steps if step.get("name") == "Run chaos tests")
    assert (
        tests["env"]["STORAGE_S3_ACCESS_KEY_ID"]
        == job["services"]["minio"]["env"]["AWS_ACCESS_KEY_ID"]
    )
    assert (
        tests["env"]["STORAGE_S3_SECRET_ACCESS_KEY"]
        == job["services"]["minio"]["env"]["AWS_SECRET_ACCESS_KEY"]
    )
    run_lines = tests["run"].splitlines()
    assert len(run_lines) == 3
    assert run_lines[:2] == [
        'export MINIO_ACCESS_KEY="$STORAGE_S3_ACCESS_KEY_ID"',
        'export MINIO_SECRET_KEY="$STORAGE_S3_SECRET_ACCESS_KEY"',
    ]
    assert shlex.split(run_lines[2]) == [
        "uv",
        "run",
        "pytest",
        "tests/chaos/",
        "-v",
        "-m",
        "chaos",
        "--tb=short",
    ]
    assert steps.index(configure) < steps.index(tests)
    assert tests["env"]["UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"] == "1"
    assert tests["env"]["MINIO_PROXY_ENDPOINT"] == "http://localhost:9003"
    assert tests["env"]["MINIO_DIRECT_ENDPOINT"] == "localhost:9000"
    assert tests["env"]["STORAGE_S3_ENDPOINT_URL"] == "http://localhost:9003"
    assert "if" not in tests
    assert "continue-on-error" not in tests


@dataclass
class _ChaosHarness:
    orchestrator: chaos.ChaosLoadTestOrchestrator
    events: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    command_errors: dict[str, BaseException] = field(default_factory=dict)
    load_errors: dict[str, BaseException] = field(default_factory=dict)
    request_counts: dict[str, int] = field(default_factory=dict)
    recovery_successes: int = 10


@pytest.fixture
def chaos_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _ChaosHarness:
    manifest = tmp_path / "fault.yaml"
    manifest.write_text("kind: NetworkChaos\n", encoding="utf-8")
    orchestrator = chaos.ChaosLoadTestOrchestrator(str(manifest), 1, "http://target")
    harness = _ChaosHarness(orchestrator)
    api = _FakeChaosAPI(
        orchestrator,
        [
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "NetworkChaos",
                "metadata": {"name": "fault-a"},
            }
        ],
    )

    def fake_kubectl(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        input: str | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output and text
        harness.commands.append(command)
        if "version" in command:
            operation = "version"
        elif "config" in command:
            operation = "config"
        elif "--dry-run=client" in command:
            operation = "plan"
        elif "create" in command:
            operation = "create"
        elif "delete" in command:
            operation = "delete"
        else:
            operation = "wait"
        harness.events.append(operation)
        if operation in harness.command_errors:
            raise harness.command_errors[operation]
        return api.run(
            command,
            capture_output=capture_output,
            text=text,
            check=check,
            input=input,
            timeout=timeout,
        )

    async def fake_load(phase: str, duration: float) -> chaos.PhaseMetrics:
        harness.events.append(phase)
        if phase in harness.load_errors:
            raise harness.load_errors[phase]
        requests = harness.request_counts.get(phase, 10)
        successes = (
            min(requests, harness.recovery_successes)
            if phase.startswith("Phase 6")
            else requests
        )
        return chaos.PhaseMetrics(
            phase_name=phase,
            total_requests=requests,
            successful_requests=successes,
            failed_requests=requests - successes,
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "kubectl-test")
    monkeypatch.setattr(subprocess, "run", fake_kubectl)
    monkeypatch.setattr(
        orchestrator, "_send_http_request", lambda *_args, **_kw: (200, 0.0, None)
    )
    monkeypatch.setattr(orchestrator, "_run_http_load", fake_load)
    return harness


def test_monitor_failure_removes_fault_before_returning_error(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.load_errors["Phase 4: Fault Injection"] = RuntimeError(
        "monitor failed"
    )

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events == [
        "version",
        "Phase 2: Baseline",
        "config",
        "plan",
        "create",
        "Phase 4: Fault Injection",
        "delete",
        "wait",
    ]
    assert any(
        "--raw=/apis/chaos-mesh.org/v1alpha1/namespaces/qa/networkchaos/fault-a"
        in command
        for command in chaos_harness.commands
    )


@pytest.mark.parametrize("failure", ["command", "os"])
def test_failed_create_does_not_delete_unconfirmed_resource(
    chaos_harness: _ChaosHarness, failure: str
) -> None:
    chaos_harness.command_errors["create"] = (
        subprocess.CalledProcessError(1, ["kubectl-test", "create"])
        if failure == "command"
        else OSError("could not execute create")
    )

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events == [
        "version",
        "Phase 2: Baseline",
        "config",
        "plan",
        "create",
    ]


def test_monitor_cancellation_removes_fault_and_propagates_cancellation(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.load_errors["Phase 4: Fault Injection"] = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(chaos_harness.orchestrator.execute())
    assert chaos_harness.events[-3:] == ["Phase 4: Fault Injection", "delete", "wait"]


def test_interrupted_create_preserves_unknown_resource_and_propagates_interrupt(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.command_errors["create"] = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(chaos_harness.orchestrator.execute())
    assert chaos_harness.events == [
        "version",
        "Phase 2: Baseline",
        "config",
        "plan",
        "create",
    ]


def test_cleanup_failure_returns_error_without_checking_recovery(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.command_errors["delete"] = subprocess.CalledProcessError(
        1, ["kubectl-test", "delete"]
    )

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events[-2:] == ["Phase 4: Fault Injection", "delete"]
    assert chaos_harness.events.count("delete") == 1


def test_monitor_and_cleanup_failures_are_both_reported(
    chaos_harness: _ChaosHarness, caplog: pytest.LogCaptureFixture
) -> None:
    chaos_harness.load_errors["Phase 4: Fault Injection"] = RuntimeError(
        "monitor failed"
    )
    chaos_harness.command_errors["delete"] = subprocess.CalledProcessError(
        1, ["kubectl-test", "delete"]
    )

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events[-2:] == ["Phase 4: Fault Injection", "delete"]
    assert "Failed to remove or verify chaos resource" in caplog.text
    assert (
        "Unexpected error during chaos loadtest execution (RuntimeError)" in caplog.text
    )


def test_missing_manifest_does_not_apply_or_remove_fault(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.orchestrator.manifest_path.unlink()

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events == []


def test_preflight_kubectl_failure_stops_before_fault_creation(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.command_errors["version"] = OSError("cannot launch kubectl")

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events == ["version"]


def test_failure_before_apply_does_not_remove_fault(
    chaos_harness: _ChaosHarness,
) -> None:
    chaos_harness.load_errors["Phase 2: Baseline"] = RuntimeError("baseline failed")

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events == ["version", "Phase 2: Baseline"]


def test_successful_execution_removes_fault_before_recovery(
    chaos_harness: _ChaosHarness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 0
    assert chaos_harness.events == [
        "version",
        "Phase 2: Baseline",
        "config",
        "plan",
        "create",
        "Phase 4: Fault Injection",
        "delete",
        "wait",
        "Phase 6: Recovery Verification",
    ]
    assert "Data loss         : NOT VERIFIED" in caplog.text
    assert "Zero data loss verified" not in caplog.text
    assert "DLQ Replay" not in caplog.text
    assert "Recovery availability assertion passed" in caplog.text


@pytest.mark.parametrize(("successes", "expected_exit"), [(7, 1), (8, 0)])
def test_recovery_success_threshold_is_preserved(
    chaos_harness: _ChaosHarness, successes: int, expected_exit: int
) -> None:
    chaos_harness.recovery_successes = successes

    assert asyncio.run(chaos_harness.orchestrator.execute()) == expected_exit
    assert chaos_harness.events[-3:] == [
        "delete",
        "wait",
        "Phase 6: Recovery Verification",
    ]


def test_recovery_failure_does_not_repeat_cleanup(chaos_harness: _ChaosHarness) -> None:
    chaos_harness.load_errors["Phase 6: Recovery Verification"] = RuntimeError(
        "recovery failed"
    )

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert chaos_harness.events[-3:] == [
        "delete",
        "wait",
        "Phase 6: Recovery Verification",
    ]
    assert chaos_harness.events.count("delete") == 1


def test_recovery_health_poll_retries_until_success(
    chaos_harness: _ChaosHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    statuses = iter([200, 0, 200])
    sleeps: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleeps.append(duration)

    monkeypatch.setattr(
        chaos_harness.orchestrator,
        "_send_http_request",
        lambda *_args, **_kw: (next(statuses), 0.0, None),
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 0
    assert sleeps == [1.0]
    assert chaos_harness.events[-3:] == [
        "delete",
        "wait",
        "Phase 6: Recovery Verification",
    ]


def test_recovery_health_poll_timeout_is_reported(
    chaos_harness: _ChaosHarness,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = iter([0.0, 16.0])
    monkeypatch.setattr(chaos, "time", SimpleNamespace(monotonic=lambda: next(clock)))

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 0
    assert "System recovery check timed out" in caplog.text
    assert chaos_harness.events[-3:] == [
        "delete",
        "wait",
        "Phase 6: Recovery Verification",
    ]


def test_report_rejects_missing_recovery_samples_and_does_not_show_100_percent(
    chaos_harness: _ChaosHarness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert not chaos_harness.orchestrator.phase7_assert_and_report()
    assert "No recovery requests" in caplog.text
    assert "100.0%" not in caplog.text
    assert "Data loss         : NOT VERIFIED" in caplog.text


def test_empty_load_phases_are_never_logged_as_fully_successful(
    chaos_harness: _ChaosHarness, caplog: pytest.LogCaptureFixture
) -> None:
    chaos_harness.request_counts = {
        "Phase 2: Baseline": 0,
        "Phase 4: Fault Injection": 0,
        "Phase 6: Recovery Verification": 0,
    }
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 1
    assert "Baseline completed: 0 requests, N/A success rate" in caplog.text
    assert "Fault phase completed: 0 requests, N/A success rate" in caplog.text
    assert (
        "Recovery verification load test: 0 requests, N/A success rate" in caplog.text
    )
    assert "No recovery requests" in caplog.text


def test_dry_run_does_not_apply_or_claim_unverified_checks(
    chaos_harness: _ChaosHarness,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    chaos_harness.orchestrator.dry_run = True
    chaos_harness.recovery_successes = 0
    monkeypatch.setattr(
        chaos_harness.orchestrator,
        "_send_http_request",
        lambda *_args, **_kw: (0, 0.0, "unreachable"),
    )
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert asyncio.run(chaos_harness.orchestrator.execute()) == 0
    assert chaos_harness.commands == []
    assert "Data loss         : NOT VERIFIED" in caplog.text
    assert "Recovery availability assertion skipped" in caplog.text
    assert "Zero data loss verified" not in caplog.text
    assert "System health endpoint responded successfully" not in caplog.text


@dataclass
class _FakeChaosAPI:
    orchestrator: chaos.ChaosLoadTestOrchestrator
    documents: list[dict[str, Any]]
    objects: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)
    create_failures: dict[str, str] = field(default_factory=dict)
    delete_failures: set[str] = field(default_factory=set)
    config_override: dict[str, object] | None = None
    parse_output: str | None = None
    calls: list[tuple[list[str], str | None, float | None]] = field(
        default_factory=list
    )
    deletes: list[tuple[tuple[str, str, str], str | None]] = field(default_factory=list)
    on_monitor: Callable[[], None] | None = None
    on_create: Callable[[], None] | None = None
    on_delete: Callable[[], None] | None = None
    wait_failure: bool = False

    def run(
        self,
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        input: str | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output and text
        self.calls.append((command.copy(), input, timeout))
        output = "ok"
        if "version" in command:
            pass
        elif "config" in command:
            output = json.dumps(
                self.config_override
                if self.config_override is not None
                else {
                    "current-context": "work",
                    "contexts": [
                        {
                            "name": "work",
                            "context": {"cluster": "cluster", "namespace": "qa"},
                        }
                    ],
                    "clusters": [
                        {
                            "name": "cluster",
                            "cluster": {"server": "https://cluster.invalid"},
                        }
                    ],
                }
            )
        elif "create" in command and "--dry-run=client" in command:
            namespace_flags = [
                part.split("=", 1)[1]
                for part in command
                if part.startswith("--namespace=")
            ]
            if namespace_flags and any(
                document.get("metadata", {}).get("namespace")
                not in (None, "", namespace_flags[0])
                for document in self.documents
            ):
                raise subprocess.CalledProcessError(
                    1, command, stderr="namespace does not match the provided namespace"
                )
            output = (
                self.parse_output
                if self.parse_output is not None
                else "\n".join(json.dumps(document) for document in self.documents)
                + "\n"
            )
        elif "create" in command:
            assert input is not None
            document = json.loads(input)
            metadata = document["metadata"]
            key = (document["kind"], metadata["namespace"], metadata["name"])
            failure = self.create_failures.get(metadata["name"])
            if key in self.objects:
                raise subprocess.CalledProcessError(1, command, stderr="AlreadyExists")
            if failure == "os":
                raise OSError("process could not start")
            metadata["uid"] = f"uid-{metadata['name']}"
            self.objects[key] = document
            if self.on_create is not None:
                self.on_create()
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, timeout or 1)
            if failure == "interrupt":
                raise KeyboardInterrupt()
            response = json.loads(json.dumps(document))
            if failure == "uid-missing":
                del response["metadata"]["uid"]
            elif failure == "wrong-name":
                response["metadata"]["name"] = "other"
            elif failure == "wrong-kind":
                response["kind"] = "PodChaos"
            elif failure == "wrong-namespace":
                response["metadata"]["namespace"] = "elsewhere"
            elif failure == "wrong-annotation":
                response["metadata"]["annotations"] = {}
            output = (
                "invalid response" if failure == "malformed" else json.dumps(response)
            )
        elif "apply" in command:
            for original in self.documents:
                document = json.loads(json.dumps(original))
                metadata = document["metadata"]
                metadata.setdefault("namespace", "qa")
                key = (document["kind"], metadata["namespace"], metadata["name"])
                metadata["uid"] = (
                    self.objects.get(key, {})
                    .get("metadata", {})
                    .get("uid", f"uid-{metadata['name']}")
                )
                self.objects[key] = document
        elif "delete" in command and "-f" in command and "-" not in command:
            for original in self.documents:
                metadata = original["metadata"]
                key = (
                    original["kind"],
                    metadata.get("namespace", "qa"),
                    metadata["name"],
                )
                self.objects.pop(key, None)
        elif "delete" in command:
            if self.on_delete is not None:
                self.on_delete()
            raw = next(
                arg.split("=", 1)[1] for arg in command if arg.startswith("--raw=")
            )
            namespace, resource, name = raw.split("/")[-3:]
            kind = {"podchaos": "PodChaos", "networkchaos": "NetworkChaos"}[resource]
            key = (kind, namespace, name)
            uid = json.loads(input or "{}").get("preconditions", {}).get("uid")
            self.deletes.append((key, uid))
            if name in self.delete_failures:
                raise subprocess.CalledProcessError(1, command, stderr="delete failed")
            current = self.objects.get(key)
            if current is None or current["metadata"].get("uid") != uid:
                raise subprocess.CalledProcessError(
                    1, command, stderr="UID mismatch or missing"
                )
            del self.objects[key]
        elif "wait" in command:
            if self.wait_failure:
                raise subprocess.CalledProcessError(1, command, stderr="wait timed out")
        else:
            raise AssertionError(f"Unexpected kubectl command: {command}")
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")


@pytest.fixture
def fake_chaos_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeChaosAPI:
    manifest = tmp_path / "fault.yaml"
    manifest.write_text(
        "fixtures are supplied by the mocked kubectl parser\n", encoding="utf-8"
    )
    orchestrator = chaos.ChaosLoadTestOrchestrator(str(manifest), 1, "http://target")
    api = _FakeChaosAPI(
        orchestrator,
        [
            {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "NetworkChaos",
                "metadata": {"name": "fault-a"},
            }
        ],
    )

    async def load(phase: str, _duration: float) -> chaos.PhaseMetrics:
        if phase.startswith("Phase 4") and api.on_monitor is not None:
            api.on_monitor()
        return chaos.PhaseMetrics(
            phase_name=phase, total_requests=10, successful_requests=10
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "kubectl-test")
    monkeypatch.setattr(subprocess, "run", api.run)
    monkeypatch.setattr(
        orchestrator, "_send_http_request", lambda *_args, **_kw: (200, 0.0, None)
    )
    monkeypatch.setattr(orchestrator, "_run_http_load", load)
    return api


def test_existing_fault_is_not_modified_or_deleted(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    key = ("NetworkChaos", "qa", "fault-a")
    existing = {"metadata": {"uid": "existing-uid"}, "spec": {"action": "existing"}}
    fake_chaos_api.objects[key] = json.loads(json.dumps(existing))

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects[key] == existing
    assert fake_chaos_api.deletes == []
    assert all("apply" not in command for command, _, _ in fake_chaos_api.calls)


def test_create_oserror_never_deletes_an_unconfirmed_object(
    fake_chaos_api: _FakeChaosAPI, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.create_failures["fault-a"] = "os"

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.deletes == []
    assert "manual" in caplog.text.lower()


def test_partial_create_cleans_only_confirmed_uid_and_preserves_existing(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    fake_chaos_api.documents.append(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "PodChaos",
            "metadata": {"name": "fault-b"},
        }
    )
    existing_key = ("PodChaos", "qa", "fault-b")
    existing = {"metadata": {"uid": "old-uid"}, "spec": {"action": "existing"}}
    fake_chaos_api.objects[existing_key] = json.loads(json.dumps(existing))

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {existing_key: existing}
    assert fake_chaos_api.deletes == [
        (("NetworkChaos", "qa", "fault-a"), "uid-fault-a")
    ]


@pytest.mark.parametrize("failure", ["timeout", "malformed"])
def test_ambiguous_create_is_left_for_manual_inspection(
    fake_chaos_api: _FakeChaosAPI, failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.create_failures["fault-a"] = failure

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert ("NetworkChaos", "qa", "fault-a") in fake_chaos_api.objects
    assert fake_chaos_api.deletes == []
    assert "manual" in caplog.text.lower()
    assert "NetworkChaos" in caplog.text
    assert "qa/fault-a" in caplog.text
    assert "work" in caplog.text


@pytest.mark.parametrize(
    "failure",
    ["uid-missing", "wrong-name", "wrong-kind", "wrong-namespace", "wrong-annotation"],
)
def test_unconfirmed_create_response_is_not_deleted(
    fake_chaos_api: _FakeChaosAPI, failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.create_failures["fault-a"] = failure

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert ("NetworkChaos", "qa", "fault-a") in fake_chaos_api.objects
    assert fake_chaos_api.deletes == []
    assert "manual inspection" in caplog.text.lower()


def test_ambiguous_second_creation_cleans_first_confirmed_resource(
    fake_chaos_api: _FakeChaosAPI, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.documents.append(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "PodChaos",
            "metadata": {"name": "fault-b"},
        }
    )
    fake_chaos_api.create_failures["fault-b"] = "timeout"

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert set(fake_chaos_api.objects) == {("PodChaos", "qa", "fault-b")}
    assert fake_chaos_api.deletes == [
        (("NetworkChaos", "qa", "fault-a"), "uid-fault-a")
    ]
    assert "PodChaos qa/fault-b in context work" in caplog.text


def test_unresolved_creation_blocks_reusing_orchestrator(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    fake_chaos_api.create_failures["fault-a"] = "timeout"
    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    calls = len(fake_chaos_api.calls)

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert len(fake_chaos_api.calls) == calls


def test_interrupted_create_does_not_delete_unknown_uid(
    fake_chaos_api: _FakeChaosAPI, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.create_failures["fault-a"] = "interrupt"

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(fake_chaos_api.orchestrator.execute())
    assert ("NetworkChaos", "qa", "fault-a") in fake_chaos_api.objects
    assert fake_chaos_api.deletes == []
    assert "manual" in caplog.text.lower()


def test_recreated_object_survives_uid_precondition_conflict(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    key = ("NetworkChaos", "qa", "fault-a")
    replacement = {"metadata": {"uid": "replacement-uid"}, "spec": {"action": "other"}}
    fake_chaos_api.on_monitor = lambda: fake_chaos_api.objects.__setitem__(
        key, replacement
    )

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects[key] == replacement
    assert fake_chaos_api.deletes == [(key, "uid-fault-a")]


def test_live_operations_are_context_bound_and_time_limited(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 0
    assert fake_chaos_api.objects == {}
    for command, _input, timeout in fake_chaos_api.calls:
        assert timeout is not None and 0 < timeout <= 120
        if "version" not in command and "config" not in command:
            assert "--context=work" in command
            assert "--server=https://cluster.invalid" in command
        if "create" in command:
            assert "--namespace=qa" in command


def test_explicit_foreign_namespace_is_rejected_before_any_create(
    fake_chaos_api: _FakeChaosAPI, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.documents[0]["metadata"]["namespace"] = "other"

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {}
    assert fake_chaos_api.deletes == []
    assert "must use the current context namespace" in caplog.text


def test_explicit_context_namespace_is_allowed(fake_chaos_api: _FakeChaosAPI) -> None:
    fake_chaos_api.documents[0]["metadata"]["namespace"] = "qa"

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 0
    assert fake_chaos_api.deletes == [
        (("NetworkChaos", "qa", "fault-a"), "uid-fault-a")
    ]


def test_parser_output_with_foreign_namespace_fails_closed(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    fake_chaos_api.parse_output = json.dumps(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "NetworkChaos",
            "metadata": {"name": "fault-a", "namespace": "other"},
        }
    )

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {}
    assert fake_chaos_api.deletes == []


def test_cli_help_explains_live_namespace_restriction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest", "--help"])

    with pytest.raises(SystemExit) as result:
        chaos.main()
    assert result.value.code == 0
    assert "live manifests must use the current context namespace" in " ".join(
        capsys.readouterr().out.lower().split()
    )


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"current-context": "work", "contexts": []},
        {
            "current-context": "work",
            "contexts": [{"name": "work", "context": {"cluster": "missing"}}],
            "clusters": [],
        },
        {
            "current-context": "work",
            "contexts": [{"name": "work", "context": {"cluster": "cluster"}}],
            "clusters": [{"name": "cluster", "cluster": {}}],
        },
        {
            "current-context": "work",
            "contexts": [{"name": "work", "context": {"cluster": "cluster"}}],
            "clusters": [
                {"name": "cluster", "cluster": {"server": "file:///etc/passwd"}}
            ],
        },
        {
            "current-context": "work",
            "contexts": [
                {
                    "name": "work",
                    "context": {"cluster": "cluster", "namespace": "../escape"},
                }
            ],
            "clusters": [
                {"name": "cluster", "cluster": {"server": "https://cluster.invalid"}}
            ],
        },
    ],
)
def test_invalid_cluster_configuration_fails_before_parsing_or_creation(
    fake_chaos_api: _FakeChaosAPI, config: dict[str, object]
) -> None:
    fake_chaos_api.config_override = config

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {}
    assert all(
        "create" not in command and "delete" not in command
        for command, _, _ in fake_chaos_api.calls
    )


@pytest.mark.parametrize("output", ["", "[]\n", '{"kind": "NetworkChaos"} trailing'])
def test_invalid_or_empty_parser_output_prevents_any_creation(
    fake_chaos_api: _FakeChaosAPI, output: str
) -> None:
    fake_chaos_api.parse_output = output

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {}
    assert fake_chaos_api.deletes == []


@pytest.mark.parametrize("case", ["too-many", "duplicate", "reserved-annotation"])
def test_manifest_is_fully_validated_before_the_first_create(
    fake_chaos_api: _FakeChaosAPI, case: str
) -> None:
    original = fake_chaos_api.documents[0]
    if case == "too-many":
        fake_chaos_api.documents = [original] * 17
    elif case == "duplicate":
        fake_chaos_api.documents.append(original)
    else:
        original["metadata"]["annotations"] = {
            "university-ecosystem.io/chaos-loadtest-run-id": "spoof"
        }

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {}
    assert fake_chaos_api.deletes == []


@pytest.mark.parametrize(
    "document",
    [
        {"apiVersion": "v1", "kind": "NetworkChaos", "metadata": {"name": "fault-a"}},
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "Secret",
            "metadata": {"name": "fault-a"},
        },
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "NetworkChaos",
            "metadata": {"name": "../escape"},
        },
    ],
)
def test_unsupported_manifest_fails_before_any_fault_creation(
    fake_chaos_api: _FakeChaosAPI, document: dict[str, object]
) -> None:
    fake_chaos_api.documents = [document]

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert fake_chaos_api.objects == {}
    assert fake_chaos_api.deletes == []


def test_cleanup_requires_confirmed_deletion(
    fake_chaos_api: _FakeChaosAPI, caplog: pytest.LogCaptureFixture
) -> None:
    fake_chaos_api.wait_failure = True

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert "Failed to" in caplog.text


def test_cleanup_continues_after_first_owned_resource_fails(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    fake_chaos_api.documents.append(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "PodChaos",
            "metadata": {"name": "fault-b"},
        }
    )
    fake_chaos_api.delete_failures.add("fault-a")

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    assert set(fake_chaos_api.objects) == {("NetworkChaos", "qa", "fault-a")}
    assert fake_chaos_api.deletes == [
        (("NetworkChaos", "qa", "fault-a"), "uid-fault-a"),
        (("PodChaos", "qa", "fault-b"), "uid-fault-b"),
    ]


@pytest.mark.parametrize("failure", ["timeout", "delete"])
def test_manual_recovery_evidence_identifies_resource_without_exposing_server_path(
    fake_chaos_api: _FakeChaosAPI, caplog: pytest.LogCaptureFixture, failure: str
) -> None:
    server = "https://cluster.invalid/private-prefix-should-not-appear"
    fake_chaos_api.config_override = {
        "current-context": "work",
        "contexts": [
            {"name": "work", "context": {"cluster": "cluster", "namespace": "qa"}}
        ],
        "clusters": [{"name": "cluster", "cluster": {"server": server}}],
    }
    if failure == "timeout":
        fake_chaos_api.create_failures["fault-a"] = "timeout"
    else:
        fake_chaos_api.delete_failures.add("fault-a")

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 1
    payload = next(
        payload
        for command, payload, _ in fake_chaos_api.calls
        if "create" in command and "--dry-run=client" not in command
    )
    assert payload is not None
    run_id = json.loads(payload)["metadata"]["annotations"][
        "university-ecosystem.io/chaos-loadtest-run-id"
    ]
    assert "NetworkChaos" in caplog.text
    assert "qa/fault-a" in caplog.text
    assert "work" in caplog.text
    assert "https://cluster.invalid" in caplog.text
    assert hashlib.sha256(server.encode()).hexdigest() in caplog.text
    assert run_id in caplog.text
    assert "private-prefix-should-not-appear" not in caplog.text
    if failure == "delete":
        assert "uid-fault-a" in caplog.text


def test_cleanup_attempts_all_guarded_deletions_before_any_wait(
    fake_chaos_api: _FakeChaosAPI,
) -> None:
    fake_chaos_api.documents.append(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "PodChaos",
            "metadata": {"name": "fault-b"},
        }
    )

    assert asyncio.run(fake_chaos_api.orchestrator.execute()) == 0
    cleanup = [
        ("delete" if "delete" in command else "wait", timeout)
        for command, _, timeout in fake_chaos_api.calls
        if "delete" in command or "wait" in command
    ]
    assert [operation for operation, _ in cleanup] == [
        "delete",
        "delete",
        "wait",
        "wait",
    ]
    assert sum(timeout for _, timeout in cleanup if timeout is not None) <= 24.0


@pytest.mark.parametrize("moment", ["create", "monitor", "cleanup"])
def test_sigterm_requests_shutdown_and_still_removes_confirmed_fault(
    fake_chaos_api: _FakeChaosAPI, monkeypatch: pytest.MonkeyPatch, moment: str
) -> None:
    signal_handler = Callable[[int, FrameType | None], Any] | int | None
    installed: dict[int, signal_handler] = {}
    original_signal = signal.signal

    def fake_signal(signum: int, handler: signal_handler) -> signal_handler:
        if signum != signal.SIGTERM:
            return original_signal(signum, handler)
        previous = installed.get(signum, signal.SIG_DFL)
        installed[signum] = handler
        return previous

    def terminate() -> None:
        handler = installed.get(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)

    if moment == "create":
        fake_chaos_api.on_create = terminate
    elif moment == "monitor":
        fake_chaos_api.on_monitor = terminate
    else:
        fake_chaos_api.on_delete = terminate
    monkeypatch.setattr(signal, "signal", fake_signal)
    monkeypatch.setattr(
        chaos,
        "ChaosLoadTestOrchestrator",
        lambda **_kwargs: fake_chaos_api.orchestrator,
    )
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest"])

    with pytest.raises(SystemExit) as result:
        chaos.main()
    assert result.value.code == 143
    if moment == "create":
        assert set(fake_chaos_api.objects) == {("NetworkChaos", "qa", "fault-a")}
        assert fake_chaos_api.deletes == []
    else:
        assert fake_chaos_api.objects == {}
        assert fake_chaos_api.deletes == [
            (("NetworkChaos", "qa", "fault-a"), "uid-fault-a")
        ]
    assert installed[signal.SIGTERM] == signal.SIG_DFL


def test_cli_restores_sigterm_handler_after_normal_run(
    fake_chaos_api: _FakeChaosAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(
        chaos,
        "ChaosLoadTestOrchestrator",
        lambda **_kwargs: fake_chaos_api.orchestrator,
    )
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest"])

    with pytest.raises(SystemExit) as result:
        chaos.main()
    assert result.value.code == 0
    assert signal.getsignal(signal.SIGTERM) == previous


def test_sigterm_from_event_loop_callback_cancels_monitor_promptly(
    fake_chaos_api: _FakeChaosAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed: dict[int, Callable[[int, FrameType | None], Any] | int | None] = {}
    original_signal = signal.signal
    timeouts: list[bool] = []

    def fake_signal(
        signum: int, handler: Callable[[int, FrameType | None], Any] | int | None
    ) -> Callable[[int, FrameType | None], Any] | int | None:
        if signum != signal.SIGTERM:
            return original_signal(signum, handler)
        previous = installed.get(signum, signal.SIG_DFL)
        installed[signum] = handler
        return previous

    async def load(phase: str, _duration: float) -> chaos.PhaseMetrics:
        if phase.startswith("Phase 4"):
            handler = installed[signal.SIGTERM]
            assert callable(handler)
            asyncio.get_running_loop().call_soon(handler, signal.SIGTERM, None)
            try:
                await asyncio.wait_for(asyncio.Future(), timeout=0.05)
            except TimeoutError:
                timeouts.append(True)
                raise
        return chaos.PhaseMetrics(
            phase_name=phase, total_requests=10, successful_requests=10
        )

    monkeypatch.setattr(signal, "signal", fake_signal)
    monkeypatch.setattr(fake_chaos_api.orchestrator, "_run_http_load", load)
    monkeypatch.setattr(
        chaos,
        "ChaosLoadTestOrchestrator",
        lambda **_kwargs: fake_chaos_api.orchestrator,
    )
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest"])

    with pytest.raises(SystemExit) as result:
        chaos.main()
    assert result.value.code == 143
    assert timeouts == []
    assert fake_chaos_api.objects == {}
    assert fake_chaos_api.deletes == [
        (("NetworkChaos", "qa", "fault-a"), "uid-fault-a")
    ]


def test_sigterm_before_event_loop_start_never_runs_kubectl(
    fake_chaos_api: _FakeChaosAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_signal = signal.signal
    installed = False

    def fake_signal(
        signum: int, handler: Callable[[int, FrameType | None], Any] | int | None
    ) -> Callable[[int, FrameType | None], Any] | int | None:
        nonlocal installed
        if signum != signal.SIGTERM:
            return original_signal(signum, handler)
        if not installed:
            installed = True
            assert callable(handler)
            handler(signal.SIGTERM, None)
        return signal.SIG_DFL

    monkeypatch.setattr(signal, "signal", fake_signal)
    monkeypatch.setattr(
        chaos,
        "ChaosLoadTestOrchestrator",
        lambda **_kwargs: fake_chaos_api.orchestrator,
    )
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest"])

    with pytest.raises(SystemExit) as result:
        chaos.main()
    assert result.value.code == 143
    assert fake_chaos_api.calls == []


def test_sigterm_before_kubectl_start_prevents_subprocess_launch(
    fake_chaos_api: _FakeChaosAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    def terminate_before_launch(_name: str) -> str:
        fake_chaos_api.orchestrator._request_termination(signal.SIGTERM, None)
        return "kubectl-test"

    monkeypatch.setattr(shutil, "which", terminate_before_launch)
    monkeypatch.setattr(
        chaos,
        "ChaosLoadTestOrchestrator",
        lambda **_kwargs: fake_chaos_api.orchestrator,
    )
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest"])

    with pytest.raises(SystemExit) as result:
        chaos.main()
    assert result.value.code == 143
    assert fake_chaos_api.calls == []


def test_cli_propagates_cancellation_not_caused_by_sigterm(
    fake_chaos_api: _FakeChaosAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = signal.getsignal(signal.SIGTERM)

    def cancel_execution(coroutine: Any) -> int:
        coroutine.close()
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "run", cancel_execution)
    monkeypatch.setattr(
        chaos,
        "ChaosLoadTestOrchestrator",
        lambda **_kwargs: fake_chaos_api.orchestrator,
    )
    monkeypatch.setattr(sys, "argv", ["chaos-loadtest"])

    with pytest.raises(asyncio.CancelledError):
        chaos.main()
    assert signal.getsignal(signal.SIGTERM) == previous
