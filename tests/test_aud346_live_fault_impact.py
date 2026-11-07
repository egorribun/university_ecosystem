from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from scripts.chaos import run_chaos_loadtest as chaos

IDENTITY = chaos._FaultIdentity(
    "PodChaos", "aud346", "aud346-live-pod-failure", "chaos-uid-1"
)
CLUSTER_ID = "a1b2c3d4e5f6"
RUN_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def _orchestrator() -> chaos.ChaosLoadTestOrchestrator:
    orchestrator = chaos.ChaosLoadTestOrchestrator(
        "unused.yaml",
        5,
        "http://127.0.0.1:18080/health",
        require_fault_impact=True,
    )
    orchestrator._context = f"kind-ue-gw-{CLUSTER_ID}"
    orchestrator._server = "https://127.0.0.1:6443"
    orchestrator._run_id = RUN_ID
    orchestrator._owned_faults = [IDENTITY]
    return orchestrator


def _injected_status() -> dict[str, object]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": IDENTITY.name,
            "namespace": IDENTITY.namespace,
            "uid": IDENTITY.uid,
            "annotations": {
                chaos._RUN_ANNOTATION: RUN_ID,
            },
        },
        "status": {
            "conditions": [
                {"type": "Selected", "status": "True"},
                {"type": "AllInjected", "status": "True"},
            ],
            "experiment": {
                "containerRecords": [
                    {
                        "id": "aud346/aud346-chaos-target-7c5c8c9c6d-abcde",
                        "phase": "Injected",
                        "injectedCount": 1,
                        "events": [{"operation": "Apply", "type": "Succeeded"}],
                    }
                ]
            },
        },
    }


def _set_status(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator: chaos.ChaosLoadTestOrchestrator,
    document: object,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "_run_kubectl",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["kubectl"], 0, json.dumps(document), ""
        ),
    )


def test_injection_status_is_uid_run_namespace_and_success_event_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = _orchestrator()
    status = _injected_status()
    _set_status(monkeypatch, orchestrator, status)

    assert orchestrator._fault_status_confirms_injection(IDENTITY)

    commands: list[list[str]] = []
    monkeypatch.setattr(
        orchestrator,
        "_run_kubectl",
        lambda command, **_kwargs: (
            commands.append(command)
            or subprocess.CompletedProcess(["kubectl"], 0, json.dumps(status), "")
        ),
    )
    assert orchestrator._fault_status_confirms_injection(IDENTITY)
    assert "--context=kind-ue-gw-a1b2c3d4e5f6" in commands[0]
    assert "--namespace=aud346" in commands[0]
    assert "podchaos.chaos-mesh.org" in commands[0]


def _prepare_receipt_assertions(orchestrator: chaos.ChaosLoadTestOrchestrator) -> None:
    orchestrator._proof_faults = [IDENTITY]
    orchestrator._owned_faults = []
    orchestrator._fault_status_confirmed = True
    orchestrator._fault_status_confirmed_during_monitor = True
    orchestrator._fault_status_confirmed_after_monitor = True
    orchestrator._recovery_probe_confirmed = True
    orchestrator._cleanup_verified = True
    orchestrator.results = {
        "phase2": _metrics("baseline", requests=10),
        "phase4": _metrics("fault", requests=10, failures=2),
        "phase6": _metrics("recovery", requests=10, failures=1),
    }


def test_success_receipt_emits_only_bound_normalized_observations(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="chaos_loadtest")
    orchestrator = _orchestrator()
    status = _injected_status()
    raw_event_text = "AUD346_RAW_EVENT_TEXT_MUST_NOT_APPEAR"
    status["status"]["experiment"]["containerRecords"][0]["events"][0]["message"] = (
        raw_event_text
    )
    _set_status(monkeypatch, orchestrator, status)
    assert orchestrator._fault_status_confirms_injection(IDENTITY)
    _prepare_receipt_assertions(orchestrator)

    assert orchestrator._emit_success_receipt()

    line = next(
        entry
        for entry in caplog.text.splitlines()
        if "AUD346_SUCCESS_RECEIPT " in entry
    )
    payload = line.split("AUD346_SUCCESS_RECEIPT ", 1)[1]
    receipt = json.loads(payload)
    fault = receipt["faults"][0]
    assert receipt["result"] == "pass"
    assert receipt["run_id"] == RUN_ID
    assert fault["api_version"] == "chaos-mesh.org/v1alpha1"
    assert fault["kind"] == IDENTITY.kind
    assert fault["namespace"] == IDENTITY.namespace
    assert fault["name"] == IDENTITY.name
    assert fault["uid"] == IDENTITY.uid
    assert fault["annotations"] == {chaos._RUN_ANNOTATION: RUN_ID}
    assert fault["status"]["conditions"] == [
        {"type": "Selected", "status": "True"},
        {"type": "AllInjected", "status": "True"},
    ]
    assert fault["status"]["records"] == [
        {
            "phase": "Injected",
            "injected_count": 1,
            "apply_event": {"operation": "Apply", "type": "Succeeded"},
        }
    ]
    assert receipt["status_windows"] == {
        "before_fault_traffic": True,
        "during_fault_traffic": True,
        "after_fault_traffic": True,
    }
    assert receipt["cleanup"]["uid_preconditioned_delete_verified"] is True
    assert receipt["cleanup"]["deleted_uids"] == [IDENTITY.uid]
    assert "AUD346_RAW_EVENT_TEXT_MUST_NOT_APPEAR" not in payload
    assert "127.0.0.1" not in payload
    assert "password" not in payload.casefold()


def test_success_receipt_is_not_emitted_without_validated_status(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    orchestrator = _orchestrator()
    status = _injected_status()
    status["metadata"]["uid"] = "replacement-uid"
    _set_status(monkeypatch, orchestrator, status)
    assert not orchestrator._fault_status_confirms_injection(IDENTITY)
    _prepare_receipt_assertions(orchestrator)
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert not orchestrator._emit_success_receipt()
    assert "AUD346_SUCCESS_RECEIPT" not in caplog.text


@pytest.mark.parametrize(
    "mutate",
    [
        lambda status: status["metadata"].update(uid="replacement-uid"),
        lambda status: status["metadata"]["annotations"].update(
            {chaos._RUN_ANNOTATION: "another-run"}
        ),
        lambda status: status["status"]["conditions"][0].update(status="False"),
        lambda status: status["status"]["conditions"][1].update(status="False"),
        lambda status: status["status"]["conditions"].append(
            {"type": "Selected", "status": "False"}
        ),
        lambda status: status["status"]["experiment"]["containerRecords"][0].update(
            phase="Not Injected"
        ),
        lambda status: status["status"]["experiment"]["containerRecords"][0]["events"][
            0
        ].update(type="Failed"),
        lambda status: status["status"]["experiment"]["containerRecords"][0].update(
            id="other-namespace/other-pod"
        ),
        lambda status: status["status"]["experiment"]["containerRecords"][0].update(
            injectedCount=0
        ),
    ],
    ids=[
        "uid",
        "run-id",
        "selected",
        "injected",
        "duplicate-selected",
        "phase",
        "event",
        "namespace",
        "count",
    ],
)
def test_injection_status_fails_closed_on_mismatched_receipt(
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    orchestrator = _orchestrator()
    status = deepcopy(_injected_status())
    mutate(status)
    _set_status(monkeypatch, orchestrator, status)

    assert not orchestrator._fault_status_confirms_injection(IDENTITY)


def _metrics(phase: str, *, requests: int, failures: int = 0) -> chaos.PhaseMetrics:
    return chaos.PhaseMetrics(
        phase_name=phase,
        total_requests=requests,
        successful_requests=requests - failures,
        failed_requests=failures,
    )


def test_live_assertion_requires_injection_degradation_and_recovery(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="chaos_loadtest")
    orchestrator = _orchestrator()
    orchestrator._fault_status_confirmed = True
    orchestrator._fault_status_confirmed_during_monitor = True
    orchestrator._fault_status_confirmed_after_monitor = True
    orchestrator._recovery_probe_confirmed = True
    orchestrator.results = {
        "phase2": _metrics("baseline", requests=10),
        "phase4": _metrics("fault", requests=10, failures=2),
        "phase6": _metrics("recovery", requests=10),
    }

    assert orchestrator.phase7_assert_and_report()
    assert "Causal fault-impact assertion passed" in caplog.text

    orchestrator.results["phase4"] = _metrics("fault", requests=10, failures=1)
    assert not orchestrator.phase7_assert_and_report()
    assert "No qualifying target degradation was observed" in caplog.text

    orchestrator.results["phase4"] = _metrics("fault", requests=10)
    assert not orchestrator.phase7_assert_and_report()

    orchestrator.results["phase4"] = _metrics("fault", requests=0)
    assert not orchestrator.phase7_assert_and_report()

    orchestrator.results["phase4"] = _metrics("fault", requests=10, failures=2)
    orchestrator.results["phase6"] = _metrics("recovery", requests=10, failures=3)
    assert not orchestrator.phase7_assert_and_report()
    assert "Post-recovery success rate below threshold" in caplog.text


def test_live_assertion_requires_a_recovered_health_probe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="chaos_loadtest")
    orchestrator = _orchestrator()
    orchestrator._fault_status_confirmed = True
    orchestrator._fault_status_confirmed_during_monitor = True
    orchestrator._fault_status_confirmed_after_monitor = True
    orchestrator.results = {
        "phase2": _metrics("baseline", requests=10),
        "phase4": _metrics("fault", requests=10, failures=2),
        "phase6": _metrics("recovery", requests=10),
    }

    assert not orchestrator.phase7_assert_and_report()
    assert "health probe did not recover" in caplog.text

    orchestrator._recovery_probe_confirmed = True
    assert orchestrator.phase7_assert_and_report()


def test_recovery_phase_records_successful_health_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = _orchestrator()
    monkeypatch.setattr(
        orchestrator,
        "_send_http_request",
        lambda *_args, **_kwargs: (200, 1.0, None),
    )

    async def successful_load(_phase: str, _duration: float) -> chaos.PhaseMetrics:
        return _metrics("recovery", requests=10)

    monkeypatch.setattr(orchestrator, "_run_http_load", successful_load)

    asyncio.run(orchestrator.phase6_verify_recovery())

    assert orchestrator._recovery_probe_confirmed


@pytest.mark.parametrize(
    ("status_results", "expected"),
    [([True, True], True), ([True, False, True], False)],
    ids=["status-stays-injected", "status-drops-during-traffic"],
)
def test_fault_status_is_rechecked_during_measured_traffic(
    monkeypatch: pytest.MonkeyPatch,
    status_results: list[bool],
    expected: bool,
) -> None:
    orchestrator = _orchestrator()
    orchestrator.duration = 0.05
    started = asyncio.Event()
    observed_during_traffic: list[bool] = []
    outcomes = iter(status_results)

    async def fake_load(_phase: str, _duration: float) -> chaos.PhaseMetrics:
        started.set()
        await asyncio.sleep(0.05)
        return _metrics("fault", requests=10, failures=2)

    def status_is_injected() -> bool:
        assert started.is_set()
        observed_during_traffic.append(True)
        return next(outcomes, True)

    monkeypatch.setattr(chaos, "_FAULT_STATUS_MONITOR_INTERVAL_SEC", 0.005)
    monkeypatch.setattr(orchestrator, "_run_http_load", fake_load)
    monkeypatch.setattr(orchestrator, "_all_owned_faults_confirmed", status_is_injected)

    asyncio.run(orchestrator.phase4_monitor_fault())

    assert len(observed_during_traffic) >= 2
    assert orchestrator._fault_status_confirmed_during_monitor is expected


def test_missing_injection_status_still_cleans_up_before_failure() -> None:
    orchestrator = _orchestrator()
    orchestrator._owned_faults = []
    events: list[str] = []
    identity = IDENTITY

    def preflight() -> bool:
        return True

    async def baseline() -> chaos.PhaseMetrics:
        events.append("baseline")
        orchestrator.results["phase2"] = _metrics("baseline", requests=10)
        return orchestrator.results["phase2"]

    def apply() -> bool:
        events.append("create")
        orchestrator._owned_faults = [identity]
        return True

    async def missing_status() -> bool:
        events.append("status")
        return False

    def cleanup() -> bool:
        events.append("cleanup")
        orchestrator._owned_faults = []
        return True

    async def should_not_monitor(_phase: str, _duration: float) -> chaos.PhaseMetrics:
        events.append("monitor")
        return _metrics("fault", requests=10)

    orchestrator.phase1_preflight = preflight
    orchestrator.phase2_baseline_load = baseline
    orchestrator.phase3_apply_fault = apply
    orchestrator._wait_for_injection_status = missing_status
    orchestrator.phase4_monitor_fault = should_not_monitor
    orchestrator.phase5_remove_fault = cleanup

    assert asyncio.run(orchestrator.execute()) == 1
    assert events == ["baseline", "create", "status", "cleanup"]


def test_status_loss_during_fault_traffic_still_cleans_up_before_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = _orchestrator()
    orchestrator.duration = 0.05
    orchestrator._owned_faults = []
    events: list[str] = []
    statuses = iter([True, False, True])

    orchestrator.phase1_preflight = lambda: True

    async def baseline() -> chaos.PhaseMetrics:
        events.append("baseline")
        metrics = _metrics("baseline", requests=10)
        orchestrator.results["phase2"] = metrics
        return metrics

    def apply() -> bool:
        events.append("create")
        orchestrator._owned_faults = [IDENTITY]
        return True

    async def injection_ready() -> bool:
        orchestrator._fault_status_confirmed = True
        return True

    def status_is_injected() -> bool:
        return next(statuses, True)

    async def load(_phase: str, _duration: float) -> chaos.PhaseMetrics:
        events.append("monitor")
        await asyncio.sleep(0.05)
        return _metrics("fault", requests=10, failures=2)

    def cleanup() -> bool:
        events.append("cleanup")
        orchestrator._owned_faults = []
        return True

    async def recovery() -> chaos.PhaseMetrics:
        events.append("recovery")
        metrics = _metrics("recovery", requests=10)
        orchestrator.results["phase6"] = metrics
        return metrics

    orchestrator.phase2_baseline_load = baseline
    orchestrator.phase3_apply_fault = apply
    orchestrator._wait_for_injection_status = injection_ready
    orchestrator.phase5_remove_fault = cleanup
    orchestrator.phase6_verify_recovery = recovery
    monkeypatch.setattr(chaos, "_FAULT_STATUS_MONITOR_INTERVAL_SEC", 0.005)
    monkeypatch.setattr(orchestrator, "_run_http_load", load)
    monkeypatch.setattr(orchestrator, "_all_owned_faults_confirmed", status_is_injected)

    assert asyncio.run(orchestrator.execute()) == 1
    assert events == ["baseline", "create", "monitor", "cleanup", "recovery"]


def test_unhealthy_baseline_prevents_fault_creation() -> None:
    orchestrator = _orchestrator()
    orchestrator._owned_faults = []
    events: list[str] = []

    orchestrator.phase1_preflight = lambda: True

    async def unhealthy_baseline() -> chaos.PhaseMetrics:
        orchestrator.results["phase2"] = _metrics("baseline", requests=10, failures=1)
        return orchestrator.results["phase2"]

    orchestrator.phase2_baseline_load = unhealthy_baseline
    orchestrator.phase3_apply_fault = lambda: events.append("create") or True

    assert asyncio.run(orchestrator.execute()) == 1
    assert events == []


def test_dry_run_still_reports_recovery_not_evaluated() -> None:
    orchestrator = chaos.ChaosLoadTestOrchestrator(
        "unused.yaml",
        5,
        "http://127.0.0.1:18080/health",
        dry_run=True,
    )

    assert orchestrator._report_dry_run()


def test_require_fault_impact_rejects_dry_run() -> None:
    orchestrator = chaos.ChaosLoadTestOrchestrator(
        "unused.yaml",
        5,
        "http://127.0.0.1:18080/health",
        dry_run=True,
        require_fault_impact=True,
    )

    assert asyncio.run(orchestrator.execute()) == 1
