"""Offline diagnostics tests: no real service, socket or Kubernetes commands."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.chaos import aud346_failure_diagnostics as diagnostics

PRIVATE = "PRIVATE_SENTINEL_do_not_emit_private-user@example.invalid"


def pod_document() -> dict:
    return {
        "items": [
            {
                "metadata": {
                    "namespace": "aud346",
                    "name": "aud346-chaos-target-abc-def",
                    "labels": {"app.kubernetes.io/name": "aud346-chaos-target"},
                    "annotations": {"private": PRIVATE},
                },
                "spec": {"containers": [{"name": "http", "image": "private/image"}]},
                "status": {
                    "phase": "Running",
                    "conditions": [
                        {"type": "Ready", "status": "False", "message": PRIVATE}
                    ],
                    "containerStatuses": [
                        {
                            "name": "http",
                            "ready": False,
                            "restartCount": 3,
                            "state": {
                                "waiting": {"reason": PRIVATE, "message": PRIVATE}
                            },
                        }
                    ],
                },
            }
        ]
    }


def test_target_closed_schema_and_no_private_fields() -> None:
    result = diagnostics.target_snapshot(json.dumps(pod_document()).encode())
    assert result == {
        "observation": "matched",
        "phase": "Running",
        "ready": False,
        "container_ready": False,
        "container_state": "waiting",
        "restart_count": 3,
    }
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"invalid",
        b"[]",
        b"null",
        b"{}",
        b'{"items":null}',
        b"x" * 65537,
        b"[" * 1000,
    ],
)
def test_malformed_target_fails_closed(payload: bytes) -> None:
    assert diagnostics.target_snapshot(payload)["observation"] == "unavailable"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x["items"].append(x["items"][0]),
        lambda x: x["items"][0]["metadata"].update(namespace=PRIVATE),
        lambda x: x["items"][0]["metadata"].update(name=PRIVATE),
        lambda x: x["items"][0]["metadata"].update(labels={}),
        lambda x: x["items"][0].update(metadata=None),
        lambda x: x["items"][0].update(status=None),
    ],
)
def test_target_identity_or_shape_mismatch(mutate) -> None:
    document = pod_document()
    mutate(document)
    assert (
        diagnostics.target_snapshot(json.dumps(document).encode())["observation"]
        == "unavailable"
    )


def test_arbitrary_target_values_are_not_echoed() -> None:
    document = pod_document()
    status = document["items"][0]["status"]
    status.update(phase=PRIVATE, conditions=[{"type": "Ready", "status": PRIVATE}])
    container = status["containerStatuses"][0]
    container.update(ready=PRIVATE, restartCount=True, state={PRIVATE: {}})
    result = diagnostics.target_snapshot(json.dumps(document).encode())
    assert result == {
        "observation": "matched",
        "phase": "unknown",
        "ready": None,
        "container_ready": None,
        "container_state": "unknown",
        "restart_count": None,
    }


def test_fault_absence_is_only_snapshot_not_uid_deletion_proof() -> None:
    assert diagnostics.fault_snapshot(b"") == {"observation": "absent_at_snapshot"}
    fault = {
        "kind": "PodChaos",
        "metadata": {
            "name": "aud346-live-pod-failure",
            "namespace": "aud346",
            "uid": PRIVATE,
        },
        "status": {"secret": PRIVATE},
    }
    assert diagnostics.fault_snapshot(json.dumps(fault).encode()) == {
        "observation": "present_at_snapshot"
    }
    fault["metadata"]["namespace"] = PRIVATE
    assert diagnostics.fault_snapshot(json.dumps(fault).encode()) == {
        "observation": "unavailable"
    }


def test_private_regular_log_tail_is_bounded_and_categorized(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    log = tmp_path / "port-forward.log"
    log.write_bytes(
        b"private prefix" * 6000
        + b"\nport-forward exited; restarting\nconnection refused "
        + PRIVATE.encode()
        + b"\nlost connection to pod\nForwarding from 127.0.0.1:1 -> 80\n"
    )
    log.chmod(0o600)
    result = diagnostics.transport_snapshot(tmp_path, "alive")
    assert result == {
        "supervisor": "alive",
        "log": "read",
        "tail_truncated": True,
        "restarts_in_tail": 1,
        "connection_refused_in_tail": True,
        "lost_connection_in_tail": True,
        "forwarding_in_tail": True,
    }
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize(
    "kind",
    ["symlink", "fifo", "directory", "public", "hardlink", "missing", "parent_symlink"],
)
def test_refuses_nonprivate_or_special_log_paths(tmp_path: Path, kind: str) -> None:
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    log = directory / "port-forward.log"
    target = tmp_path / "target"
    target.write_text(PRIVATE)
    target.chmod(0o600)
    if kind == "symlink":
        log.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(log, 0o600)
    elif kind == "directory":
        log.mkdir()
    elif kind == "public":
        log.write_text(PRIVATE)
        log.chmod(0o644)
    elif kind == "hardlink":
        os.link(target, log)
    elif kind == "parent_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(directory)
        directory = alias
    result = diagnostics.transport_snapshot(directory, PRIVATE)
    assert result == {
        "supervisor": "unknown",
        "log": "unavailable",
        "tail_truncated": None,
        "restarts_in_tail": None,
        "connection_refused_in_tail": None,
        "lost_connection_in_tail": None,
        "forwarding_in_tail": None,
    }
    assert target.read_text() == PRIVATE


def test_record_binding_is_strict_and_input_is_bounded(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
    diagnostics.main(
        [
            "fault",
            "--run-id",
            "aaaaaaaaaaaa",
            "--exit-status",
            "143",
            "--phase",
            "proof",
            "--input-status",
            "ok",
        ]
    )
    line = capsys.readouterr().out
    record = json.loads(line.split(" ", 1)[1])
    assert set(record) == {
        "schema",
        "kind",
        "run_id",
        "github_sha",
        "github_run_id",
        "github_run_attempt",
        "harness_exit_status",
        "failure_phase",
        "observation",
    }
    assert record["github_sha"] == "a" * 40
    assert record["harness_exit_status"] == 143
    assert record["observation"] == {"observation": "absent_at_snapshot"}
    for variable in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        monkeypatch.setenv(variable, PRIVATE)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(PRIVATE.encode())))
    diagnostics.main(
        [
            "fault",
            "--run-id",
            "aaaaaaaaaaaa",
            "--exit-status",
            "1",
            "--phase",
            "proof",
            "--input-status",
            "unavailable",
        ]
    )
    line = capsys.readouterr().out
    assert PRIVATE not in line
    assert json.loads(line.split(" ", 1)[1])["github_sha"] is None


def shell_functions() -> str:
    script = (ROOT / "scripts/chaos/aud346_live_kind_proof.sh").read_text()
    start = script.index("diagnostic_bounded() {")
    end = script.index("trap cleanup EXIT", start)
    return script[start:end]


@pytest.mark.parametrize("status", [1, 124, 130, 143])
@pytest.mark.parametrize("diagnostic_failure", [False, True])
@pytest.mark.parametrize("teardown_failure", [False, True])
def test_actual_cleanup_preserves_original_exit_and_runs_after_diagnostics(
    tmp_path: Path, status: int, diagnostic_failure: bool, teardown_failure: bool
) -> None:
    # Only extracted functions run; ALL external/resource operations are shell stubs.
    program = f"""set -euo pipefail
RUN_ID=aaaaaaaaaaaa
ROOT_DIR={ROOT}
WORK_DIR={tmp_path}/aud346-kind.test
WORK_PREFIX={tmp_path}/aud346-kind.
RUNNER_TMP={tmp_path}
DIAG_DIR=$WORK_DIR/diagnostics
STATE_FILE=$WORK_DIR/state
PORT_FORWARD_PID=12345
KIND_CREATE_PID=""
CLUSTER_OWNED=1
CLUSTER_CREATE_STARTED=1
CLUSTER_NAME=ue-gw-$RUN_ID
CONTEXT=kind-$CLUSTER_NAME
TARGET_NAMESPACE=aud346
PROOF_STARTED=1
PROOF_FINISHED=0
WORK_DEADLINE=$((SECONDS+100))
log() {{ printf '%s\\n' "$*" >&2; }}
kill() {{ echo stop-forward; }}
wait() {{ :; }}
run_kind_owner_cleanup() {{ echo teardown >&2; return {1 if teardown_failure else 0}; }}
rm() {{ echo remove >&2; }}
{shell_functions()}
emit_failure_diagnostics() {{ echo diagnostics >&2; return {1 if diagnostic_failure else 0}; }}
trap cleanup EXIT
exit {status}
"""
    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=program,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == status
    assert result.stderr.index("diagnostics") < result.stderr.index("teardown")
    assert ("remove\n" in result.stderr) is not teardown_failure
    assert (
        '"cleanup":"failed"' in result.stderr
        if teardown_failure
        else '"cleanup":"completed"' in result.stderr
    )


def test_small_log_and_nonprivate_directory(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    log = tmp_path / "port-forward.log"
    log.write_bytes(b"\xff\x00" + PRIVATE.encode())
    log.chmod(0o600)
    result = diagnostics.transport_snapshot(tmp_path, "not_running")
    assert result["tail_truncated"] is False
    assert result["restarts_in_tail"] == 0
    assert result["connection_refused_in_tail"] is False
    tmp_path.chmod(0o755)
    assert (
        diagnostics.transport_snapshot(tmp_path, "not_started")["log"] == "unavailable"
    )


@pytest.mark.parametrize(
    "run_id,exit_status", [(PRIVATE, "1"), ("a" * 12, "0"), ("a" * 12, "256")]
)
def test_cli_rejects_invalid_binding(run_id: str, exit_status: str) -> None:
    with pytest.raises(ValueError, match="invalid binding"):
        diagnostics.main(
            [
                "fault",
                "--run-id",
                run_id,
                "--exit-status",
                exit_status,
                "--phase",
                "proof",
            ]
        )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("target", b"!bad-base64"),
        ("target", b"eA==" * 30000),
        ("fault", b"AA=="),
        ("transport", b""),
    ],
)
def test_cli_handles_invalid_oversized_or_binary_input(
    monkeypatch, capsys, kind: str, payload: bytes
) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload)))
    diagnostics.main(
        [
            kind,
            "--run-id",
            "a" * 12,
            "--exit-status",
            "1",
            "--phase",
            "proof",
            "--input-status",
            "ok",
        ]
    )
    output = capsys.readouterr().out
    assert "unavailable" in output
    assert len(output) < 2000


def test_cli_entrypoint_transport(monkeypatch, capsys, tmp_path: Path) -> None:
    import runpy

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "diagnostics",
            "transport",
            "--run-id",
            "a" * 12,
            "--exit-status",
            "1",
            "--phase",
            "post_proof_health",
            "--directory",
            str(tmp_path),
        ],
    )
    runpy.run_path(
        str(ROOT / "scripts/chaos/aud346_failure_diagnostics.py"), run_name="__main__"
    )
    result = json.loads(capsys.readouterr().out.split(" ", 1)[1])
    assert result["failure_phase"] == "post_proof_health"
    assert result["observation"]["log"] == "unavailable"


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "malformed",
        "binary",
        "oversized",
        "kubectl_failure",
        "kubectl_timeout",
        "term_resistant",
        "helper_failure",
        "deadline",
        "success",
        "setup_failure",
        "post_proof",
    ],
)
def test_real_diagnostic_and_cleanup_functions_with_only_fake_commands(
    tmp_path: Path, mode: str
) -> None:
    binary = tmp_path / "bin"
    binary.mkdir()
    work = tmp_path / "aud346-kind.test"
    directory = work / "diagnostics"
    directory.mkdir(parents=True, mode=0o700)
    log = directory / "port-forward.log"
    log.write_text("port-forward exited; restarting\nconnection refused " + PRIVATE)
    log.chmod(0o600)
    fixture = tmp_path / "fixture"
    fixture.write_text(json.dumps(pod_document()))
    if mode == "malformed":
        fixture.write_text(PRIVATE)
    elif mode == "binary":
        fixture.write_bytes(b"\x00")
    elif mode == "oversized":
        fixture.write_bytes(b"x" * 70000)
    kubectl = binary / "kubectl"
    kubectl.write_text(f'''#!/bin/bash
printf '%s\\n' "{PRIVATE}" >&2
printf 'probe\\n' >> '{tmp_path}/calls'
if [[ "{mode}" == kubectl_timeout ]]; then sleep 4; fi
if [[ "{mode}" == term_resistant ]]; then trap "" TERM; sleep 20; fi
if [[ "{mode}" == kubectl_failure ]]; then exit 1; fi
if [[ "$*" == *"get pods"* || "{mode}" == binary ]]; then cat '{fixture}'; fi
''')
    kubectl.chmod(0o700)
    if mode == "helper_failure":
        helper = binary / "python3"
        helper.write_text(f"#!/bin/bash\nprintf '%s\\n' '{PRIVATE}' >&2\nexit 9\n")
        helper.chmod(0o700)
    program = f"""set -euo pipefail
export PATH='{binary}':"$PATH"
RUN_ID=aaaaaaaaaaaa
ROOT_DIR='{ROOT}'
WORK_DIR='{work}'
WORK_PREFIX='{tmp_path}/aud346-kind.'
RUNNER_TMP='{tmp_path}'
DIAG_DIR='{directory}'
STATE_FILE=$WORK_DIR/state
PORT_FORWARD_PID=12345
KIND_CREATE_PID=""
CLUSTER_OWNED=1
CLUSTER_CREATE_STARTED=1
CLUSTER_NAME=ue-gw-$RUN_ID
CONTEXT=kind-$CLUSTER_NAME
TARGET_NAMESPACE=aud346
PROOF_STARTED={0 if mode == "setup_failure" else 1}
PROOF_FINISHED={1 if mode == "post_proof" else 0}
WORK_DEADLINE=$((SECONDS+{0 if mode == "deadline" else 3 if mode == "term_resistant" else 100}))
log() {{ printf '%s\\n' "$*" >&2; }}
kill() {{ :; }}
wait() {{ :; }}
run_kind_owner_cleanup() {{ echo teardown >&2; }}
{shell_functions()}
trap cleanup EXIT
/bin/bash -c 'exit {0 if mode == "success" else 1}' -- PRIVATE_CALLER_SENTINEL
"""
    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=program,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=8,
        check=False,
    )
    assert result.returncode == (0 if mode == "success" else 1)
    assert PRIVATE not in result.stdout
    assert "Traceback" not in result.stdout
    assert "PRIVATE_CALLER_SENTINEL" not in result.stdout
    assert "Killed" not in result.stdout
    assert not work.exists()
    lines = result.stdout.splitlines()
    records = [
        json.loads(line.split(" ", 1)[1])
        for line in lines
        if line.startswith("AUD346_FAILURE_DIAGNOSTIC ")
    ]
    if mode in ("success", "setup_failure"):
        assert records == []
        assert not (tmp_path / "calls").exists()
        return
    assert records[-1]["kind"] == "cleanup"
    assert records[-1]["cleanup"] == "completed"
    assert lines[0].startswith("AUD346_FAILURE_DIAGNOSTIC ")
    assert lines.index("teardown") > 0
    if mode in ("deadline", "helper_failure", "kubectl_timeout", "term_resistant"):
        assert any(record["kind"] == "collection" for record in records)
    else:
        assert [record["kind"] for record in records] == [
            "transport",
            "target",
            "fault",
            "cleanup",
        ]
        target = records[1]["observation"]
        assert target["observation"] == (
            "matched" if mode in ("normal", "post_proof") else "unavailable"
        )
        if mode == "binary":
            assert records[2]["observation"] == {"observation": "unavailable"}
        if mode == "post_proof":
            assert records[0]["failure_phase"] == "post_proof_health"
