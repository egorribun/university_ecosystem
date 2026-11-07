"""Source-bound regressions for malformed hook input and missing stop checks."""

from __future__ import annotations

import importlib
import io
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[2] / ".agents" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

runner = importlib.import_module("runner")
common = importlib.import_module("common")
pre_tool_safety = importlib.import_module("pre_tool_safety")
stop_gate = importlib.import_module("stop_quality_gate")
harness = importlib.import_module("verify_harness")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " \n\t",
        "{",
        "null",
        "[]",
        "{}",
        '{"toolCall": null}',
        '{"toolCall": []}',
        '{"toolCall": {}}',
        '{"toolCall": {"name": "", "args": {}}}',
        '{"toolCall": {"name": [], "args": {}}}',
        '{"toolCall": {"name": "run_command", "args": null}}',
        '{"toolCall": {"name": "run_command", "args": {}}}',
        '{"toolCall": {"name": "run_command", "args": {"cmd": "  "}}}',
        '{"toolCall": {"name": "run_command", "args": {"cmd": 42}}}',
        '{"toolCall": {"name": "write_to_file", "args": {}}}',
        '{"toolCall": {"name": "write_to_file", "args": {"path": "  "}}}',
        '{"toolCall": {"name": "write_to_file", "args": {"path": 42}}}',
        '{"toolCall": {"name": "run_command", "args": '
        '{"cmd": "rm -rf /", "cmd": "git status"}}}',
        '{"toolCall": {"name": "run_command", "tool_name": "write_to_file", '
        '"args": {"cmd": "git status", "path": ".agents/hooks.json"}}}',
        '{"toolCall": {"name": "run_command", "args": '
        '{"CommandLine": "git status", "cmd": "rm -rf /"}}}',
        '{"toolCall": {"name": "write_to_file", "args": '
        '{"TargetFile": "notes.txt", "path": ".agents/hooks.json"}}}',
        '{"toolCall": {"name": "run_command", "args": {"cmd": "git status"}}, '
        '"tool_call": {"name": "unrecognized_tool", "args": {}}}',
        '{"toolCall": {"name": "run_command", "args": {"cmd": "git status"}, '
        '"arguments": {"cmd": "rm -rf /"}}}',
    ],
)
def test_pre_tool_runner_denies_empty_malformed_or_unrecognized_payload(
    raw: str, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(sys, "argv", ["runner.py", "pre-tool"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))

    assert runner.main() == 0

    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "deny"
    assert response["reason"]


@pytest.mark.parametrize("event", ["stop", "stop-gate", "quality-gate"])
def test_stop_event_with_empty_input_returns_stop_block(
    event: str, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(sys, "argv", ["runner.py", event])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(
        runner,
        "evaluate_stop",
        lambda _: pytest.fail("must not evaluate an empty payload"),
    )

    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "continue"


def test_stop_quality_gate_alias_returns_stop_block_on_exception(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(sys, "argv", ["runner.py", "quality-gate"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    def fail(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("isolated failure")

    monkeypatch.setattr(runner, "evaluate_stop", fail)
    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "continue"


def test_unknown_event_failure_remains_denied(monkeypatch: Any) -> None:
    monkeypatch.setattr(sys, "argv", ["runner.py", "unknown-event"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    responses: list[dict[str, Any]] = []

    def fail_once(response: dict[str, Any]) -> None:
        if not responses:
            responses.append(response)
            raise RuntimeError("isolated first write failure")
        responses.append(response)

    monkeypatch.setattr(runner, "write_json_stdout", fail_once)
    assert runner.main() == 0
    assert responses[-1]["decision"] == "deny"


def test_interactive_stdin_is_rejected_without_waiting_for_input(
    monkeypatch: Any,
) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

        def read(self, *args: Any, **kwargs: Any) -> str:
            pytest.fail("a hook must not block waiting on a terminal")

    monkeypatch.setattr(sys, "stdin", Terminal())
    assert "__hook_parse_error__" in common.read_json_stdin()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "toolCall": {
                    "name": "run_command",
                    "args": {"CommandLine": "git status"},
                }
            },
            "allow",
        ),
        (
            {
                "tool_call": {
                    "tool_name": "exec_command",
                    "arguments": {"cmd": "git status"},
                }
            },
            "allow",
        ),
        (
            {
                "toolCall": {
                    "name": "run_command",
                    "args": {"CommandLine": "git push --force origin egorribun"},
                }
            },
            "deny",
        ),
        (
            {
                "toolCall": {
                    "name": "write_to_file",
                    "args": {"TargetFile": "notes.txt"},
                }
            },
            "allow",
        ),
        (
            {
                "toolCall": {
                    "name": "replace_file_content",
                    "args": {"TargetFile": ".agents/hooks.json"},
                }
            },
            "deny",
        ),
        ({"toolCall": {"name": "view_file", "args": {"path": "notes.txt"}}}, "allow"),
        ({"toolCall": {"name": "unrecognized_tool", "args": {}}}, "allow"),
    ],
)
def test_pre_tool_keeps_supported_payloads_and_safety_decisions(
    payload: dict[str, Any], expected: str, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(pre_tool_safety, "find_repo_root", lambda: tmp_path)
    assert pre_tool_safety.evaluate_pre_tool(payload)["decision"] == expected


def test_pre_tool_direct_entry_rejects_non_object_payload() -> None:
    payload: Any = None
    assert pre_tool_safety.evaluate_pre_tool(payload)["decision"] == "deny"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "toolCall": {"name": "run_command", "args": {"cmd": "git status"}},
            "tool_call": {"name": "run_command", "args": {"cmd": "git status"}},
        },
        {
            "toolCall": {
                "name": "run_command",
                "tool_name": "run_command",
                "args": {"cmd": "git status"},
            }
        },
        {
            "toolCall": {
                "name": "run_command",
                "args": {"cmd": "git status"},
                "arguments": {"cmd": "git status"},
            }
        },
        {
            "toolCall": {
                "name": "run_command",
                "args": {"cmd": "git status", "CommandLine": "git status"},
            }
        },
        {
            "toolCall": {
                "name": "write_to_file",
                "args": {"path": "notes.txt", "TargetFile": "notes.txt"},
            }
        },
    ],
)
def test_pre_tool_accepts_matching_compatible_aliases(
    payload: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(pre_tool_safety, "find_repo_root", lambda: tmp_path)
    assert pre_tool_safety.evaluate_pre_tool(payload)["decision"] == "allow"


def test_runner_cli_uses_fail_closed_decisions_in_isolated_workspace(
    tmp_path: Path,
) -> None:
    isolated_hooks = tmp_path / ".agents" / "hooks"
    isolated_hooks.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    for name in (
        "common.py",
        "pre_tool_safety.py",
        "post_tool_linter.py",
        "stop_quality_gate.py",
        "runner.py",
    ):
        shutil.copyfile(HOOKS_DIR / name, isolated_hooks / name)
    (isolated_hooks / ".gate_state.json").write_text(
        '{"history": [], "latest_by_file": {}}', encoding="utf-8"
    )
    for event, payload, decision in (
        ("pre-tool", {}, "deny"),
        (
            "pre-tool",
            {"toolCall": {"name": "run_command", "args": {"cmd": "git status"}}},
            "allow",
        ),
        ("stop", {}, "continue"),
    ):
        code, response, stderr = harness.run_hook_cli(
            event, payload, timeout=5, workspace=tmp_path
        )
        assert code == 0, stderr
        assert response["decision"] == decision
        if event == "stop":
            assert all(
                directory in response["reason"].lower()
                for directory in ("app", "frontend", "services")
            )


@pytest.mark.parametrize(
    ("directory", "check_name"),
    [
        ("app", "check_python_subsystem"),
        ("frontend", "check_frontend_subsystem"),
        ("services", "check_services_subsystem"),
    ],
)
@pytest.mark.parametrize("missing_kind", ["absent", "file"])
def test_stop_subsystems_reject_missing_or_non_directory_inputs(
    directory: str, check_name: str, missing_kind: str, tmp_path: Path, monkeypatch: Any
) -> None:
    if missing_kind == "file":
        (tmp_path / directory).write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(stop_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(
        stop_gate,
        "run_process",
        lambda *args, **kwargs: pytest.fail("must not run a check without inputs"),
    )

    ok, reason = getattr(stop_gate, check_name)(tmp_path)

    assert not ok
    assert directory in reason.lower()


@pytest.mark.parametrize(
    ("directory", "check_name"),
    [
        ("app", "check_python_subsystem"),
        ("frontend", "check_frontend_subsystem"),
        ("services", "check_services_subsystem"),
    ],
)
def test_stop_subsystems_reject_empty_required_inputs(
    directory: str, check_name: str, tmp_path: Path, monkeypatch: Any
) -> None:
    (tmp_path / directory).mkdir()
    monkeypatch.setattr(stop_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(
        stop_gate,
        "run_process",
        lambda *args, **kwargs: pytest.fail("must not run a check without inputs"),
    )

    ok, reason = getattr(stop_gate, check_name)(tmp_path)

    assert not ok
    assert reason


def test_stop_decision_blocks_if_all_required_directories_are_missing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(stop_gate, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(stop_gate, "check_gate_state_errors", lambda: (True, ""))
    monkeypatch.setattr(stop_gate, "find_executable", lambda _: True)

    result = stop_gate.evaluate_stop({})

    assert result["decision"] == "continue"
    assert all(
        directory in result["reason"].lower()
        for directory in ("app", "frontend", "services")
    )


def test_stop_runs_configured_checks_on_nonempty_isolated_fixture(
    tmp_path: Path, monkeypatch: Any
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "example.py").write_text("value = 1\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "tsconfig.json").write_text("{}", encoding="utf-8")
    service = tmp_path / "services" / "example"
    service.mkdir(parents=True)
    (service / "go.mod").write_text("module example.invalid\n", encoding="utf-8")
    calls: list[tuple[list[str], Path]] = []

    def fake_run(
        command: list[str], *, cwd: Path, timeout: int
    ) -> tuple[int, str, str]:
        calls.append((command, cwd))
        return 0, "", ""

    monkeypatch.setattr(stop_gate, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(stop_gate, "check_gate_state_errors", lambda: (True, ""))
    monkeypatch.setattr(stop_gate, "find_executable", lambda _: True)
    monkeypatch.setattr(stop_gate, "run_process", fake_run)

    result = stop_gate.evaluate_stop({})

    assert result["decision"] == "allow"
    assert {cwd for _, cwd in calls} == {tmp_path, frontend, service}
    assert len(calls) == 3
    assert any(command[-2:] == ["check", "app/"] for command, _ in calls)
    assert any("tsc" in " ".join(command) for command, _ in calls)
    assert any(command == ["go", "vet", "./..."] for command, _ in calls)
