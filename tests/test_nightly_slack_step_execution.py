"""Executable proof of the nightly Slack notification steps (AUD-384).

The original defect read a step-level ``env`` value in the step's own ``if``,
which GitHub evaluates before that env is applied, so Slack never ran. The
current workflow records the configuration state as a step output in a prior
step and gates delivery on that output. These tests run the real ``run`` bodies
under bash against a loopback HTTP receiver and evaluate the real ``if``
clauses for both the configured and unconfigured paths. The hosted delivery
proof with the owner-held webhook is separate and is not claimed here.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NIGHTLY = REPOSITORY_ROOT / ".github" / "workflows" / "nightly-full-gate.yml"
DETECT_NAME = "Detect optional Slack notification configuration"
SEND_NAME = "Send optional Slack notification"
SEND_IF = (
    "${{ !cancelled() && steps.trusted_source.outcome == 'success' "
    "&& steps.slack_config.outputs.configured == 'true' }}"
)
DETECT_IF = "${{ !cancelled() && steps.trusted_source.outcome == 'success' }}"
SECRET_ENV = {"SLACK_WEBHOOK_URL": "${{ secrets.SLACK_WEBHOOK_URL }}"}
RUN_URL = "https://github.example.invalid/owner/repo/actions/runs/1"


def _bash() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_dir = Path(git).resolve().parent
            for candidate in (
                git_dir / "bash.exe",
                git_dir.parent / "bin" / "bash.exe",
            ):
                if candidate.is_file():
                    return str(candidate)
    executable = shutil.which("bash")
    if not executable:
        pytest.fail("Bash is required to execute the nightly Slack step bodies")
    return executable


def _notify_job() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load(NIGHTLY.read_text(encoding="utf-8"))
    job: dict[str, Any] = workflow["jobs"]["notify-failure"]
    return job


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        step for step in job["steps"] if step.get("name") == name
    ]
    assert len(matches) == 1, name
    return matches[0]


@dataclass(frozen=True)
class Context:
    """Values that the workflow's ``if`` expressions read."""

    cancelled: bool
    trusted_source: str
    slack_configured: str


def _evaluate_condition(expression: str, context: Context) -> bool:
    """Evaluate the workflow's notification-step ``if`` clauses locally.

    Unknown clauses fail the test instead of being guessed, so the evaluator
    cannot silently accept a changed condition.
    """
    assert expression.startswith("${{") and expression.endswith("}}")
    clauses = [part.strip() for part in expression[3:-2].split("&&")]
    results: list[bool] = []
    for clause in clauses:
        if clause == "!cancelled()":
            results.append(not context.cancelled)
        elif clause == "steps.trusted_source.outcome == 'success'":
            results.append(context.trusted_source == "success")
        elif clause == "steps.slack_config.outputs.configured == 'true'":
            results.append(context.slack_configured == "true")
        else:
            pytest.fail(f"unexpected clause in the Slack step condition: {clause!r}")
    return all(results)


@pytest.fixture
def receiver() -> Iterator[dict[str, Any]]:
    """A loopback webhook that records each POST and answers with a status."""
    state: dict[str, Any] = {
        "status": 200,
        "requests": [],
        "response_body": b"",
        "disconnect": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            state["requests"].append(
                {
                    "path": self.path,
                    "body": body,
                    "type": self.headers.get("Content-Type"),
                }
            )
            if state["disconnect"]:
                self.close_connection = True
                return
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(state["response_body"])))
            self.end_headers()
            self.wfile.write(state["response_body"])

        def log_message(self, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    try:
        yield {"url": f"http://{host}:{port}/hooks/loopback-receiver", "state": state}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _assert_loopback_webhook(webhook: str) -> None:
    # These tests must never accept an actual webhook or make an external call.
    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]+/hooks/loopback-receiver", webhook):
        pytest.fail("Only the synthetic loopback webhook is permitted")


def _run_detect(tmp_path: Path, webhook: str, detect: dict[str, Any]) -> str:
    if webhook:
        _assert_loopback_webhook(webhook)
    output = tmp_path / "github_output.txt"
    output.write_text("", encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SLACK_WEBHOOK_URL": webhook,
        "GITHUB_OUTPUT": str(output),
    }
    completed = subprocess.run(  # noqa: S603  # fixed argv: Git Bash runs a repository workflow step body
        [_bash(), "-c", detect["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    lines = output.read_text(encoding="utf-8").splitlines()
    configured = "true" if webhook else "false"
    assert lines == [f"configured={configured}"]
    return configured


def _run_send(
    tmp_path: Path, webhook: str, send: dict[str, Any]
) -> subprocess.CompletedProcess[str]:
    _assert_loopback_webhook(webhook)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SLACK_WEBHOOK_URL": webhook,
        "GITHUB_SERVER_URL": "https://github.example.invalid",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "1",
    }
    return subprocess.run(  # noqa: S603  # fixed argv: Git Bash runs a repository workflow step body
        [_bash(), "-c", send["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _run_optional_notification(
    tmp_path: Path,
    webhook: str,
    *,
    cancelled: bool = False,
    trusted_source: str = "success",
) -> tuple[str, subprocess.CompletedProcess[str] | None]:
    """Run each real body only when its actual workflow condition permits it.

    This deliberately models only the listed clauses, not the hosted runner.
    """
    job = _notify_job()
    detect = _step(job, DETECT_NAME)
    send = _step(job, SEND_NAME)
    configured = ""
    context = Context(cancelled, trusted_source, configured)
    if _evaluate_condition(detect["if"], context):
        configured = _run_detect(tmp_path, webhook, detect)
    context = Context(cancelled, trusted_source, configured)
    if _evaluate_condition(send["if"], context):
        return configured, _run_send(tmp_path, webhook, send)
    return configured, None


def test_send_condition_has_no_env_or_secrets_reference() -> None:
    send = _step(_notify_job(), SEND_NAME)

    assert send["if"] == SEND_IF
    assert "env." not in send["if"]
    assert "secrets." not in send["if"]
    assert "--connect-timeout 10" in send["run"]
    assert "--max-time 30" in send["run"]


def test_unconfigured_path_records_false_and_does_not_attempt_send(
    tmp_path: Path, receiver: dict[str, Any]
) -> None:
    configured, completed = _run_optional_notification(tmp_path, webhook="")

    assert configured == "false"
    assert completed is None
    assert receiver["state"]["requests"] == []


def test_configured_path_records_true_and_delivers_a_failure_notice(
    tmp_path: Path, receiver: dict[str, Any]
) -> None:
    configured, completed = _run_optional_notification(
        tmp_path, webhook=receiver["url"]
    )
    assert configured == "true"
    assert completed is not None

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    requests = receiver["state"]["requests"]
    assert len(requests) == 1
    assert requests[0]["path"] == "/hooks/loopback-receiver"
    assert requests[0]["type"] == "application/json"
    payload = json.loads(requests[0]["body"])
    assert payload == {"text": f"Nightly full quality gate failed: {RUN_URL}"}


def test_rejected_notification_fails_the_step(
    tmp_path: Path, receiver: dict[str, Any]
) -> None:
    receiver["state"]["status"] = 500

    configured, completed = _run_optional_notification(
        tmp_path, webhook=receiver["url"]
    )

    assert configured == "true"
    assert completed is not None
    assert completed.returncode != 0
    assert len(receiver["state"]["requests"]) == 1
    assert receiver["url"] not in completed.stdout
    assert receiver["url"] not in completed.stderr


@pytest.mark.parametrize("status", [200, 400, 500])
def test_notification_discards_reflected_response_body(
    tmp_path: Path, receiver: dict[str, Any], status: int
) -> None:
    receiver["state"]["status"] = status
    marker = "response-body-must-not-be-logged"
    receiver["state"]["response_body"] = f"{marker} {receiver['url']}".encode()

    configured, completed = _run_optional_notification(tmp_path, receiver["url"])

    assert configured == "true"
    assert completed is not None
    assert (completed.returncode == 0) is (status == 200)
    assert len(receiver["state"]["requests"]) == 1
    if completed.stdout:
        pytest.fail("The webhook response body was written to stdout")
    if receiver["url"] in completed.stderr or marker in completed.stderr:
        pytest.fail("The webhook response body was written to stderr")


def test_transport_failure_does_not_echo_the_webhook(
    tmp_path: Path, receiver: dict[str, Any]
) -> None:
    receiver["state"]["disconnect"] = True

    configured, completed = _run_optional_notification(tmp_path, receiver["url"])

    assert configured == "true"
    assert completed is not None
    assert completed.returncode != 0
    assert len(receiver["state"]["requests"]) == 1
    assert completed.stdout == ""
    assert completed.stderr
    if receiver["url"] in completed.stderr:
        pytest.fail("A transport error wrote the webhook to stderr")


@pytest.mark.parametrize(
    ("cancelled", "trusted_source"), [(True, "success"), (False, "failure")]
)
def test_cancelled_or_untrusted_run_skips_detection_and_send(
    tmp_path: Path,
    receiver: dict[str, Any],
    cancelled: bool,
    trusted_source: str,
) -> None:
    configured, completed = _run_optional_notification(
        tmp_path, receiver["url"], cancelled=cancelled, trusted_source=trusted_source
    )

    assert configured == ""
    assert completed is None
    assert receiver["state"]["requests"] == []


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        # The condition reads the trusted-source outcome and the recorded
        # configuration only, so a failed issue step cannot suppress Slack.
        (Context(False, "success", "true"), True),
        (Context(False, "failure", "true"), False),
        (Context(True, "success", "true"), False),
        (Context(False, "success", "false"), False),
    ],
)
def test_send_condition_truth_table(context: Context, expected: bool) -> None:
    assert (
        _evaluate_condition(_step(_notify_job(), SEND_NAME)["if"], context) is expected
    )


def test_configuration_detection_is_gated_only_on_the_trusted_source() -> None:
    job = _notify_job()
    detect = _step(job, DETECT_NAME)
    send = _step(job, SEND_NAME)
    trusted = [step for step in job["steps"] if step.get("id") == "trusted_source"]

    assert len(trusted) == 1
    assert job["steps"].index(trusted[0]) < job["steps"].index(detect)
    assert job["steps"].index(detect) < job["steps"].index(send)
    assert detect["if"] == DETECT_IF
    assert detect["id"] == "slack_config"
    assert "continue-on-error" not in detect
    assert detect["env"] == SECRET_ENV
    assert send["env"] == SECRET_ENV
