"""Runtime contracts for the temporary authenticated go-jose capture."""

from __future__ import annotations

import ast
import base64
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/reusable-security-audit.yml"
STEP = "Capture authenticated approved go-jose checksums"
MODULE = "github.com/go-jose/go-jose/v4"
VERSION = "v4.1.7"
CANARY = "PRIVATE_CAPTURE_CANARY"
FAILURE = "approved go-jose checksum capture failed\n"


@pytest.fixture
def probe(tmp_path: Path):
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["govulncheck"]
    matches = [step for step in job["steps"] if step.get("name") == STEP]
    assert len(matches) == 1
    lines = matches[0]["run"].splitlines()
    assert lines[0] == "python -I -B <<'PY'"
    assert lines[-1] == "PY"
    source = "\n".join(lines[1:-1]) + "\n"
    tree = ast.parse(source)
    assert isinstance(tree.body[-1], ast.Try)
    assert all(
        isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef))
        for node in tree.body[:-1]
    )
    entrypoint = ast.FunctionDef(
        name="_entrypoint",
        args=ast.arguments(
            posonlyargs=[],
            args=[],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=[tree.body[-1]],
        decorator_list=[],
        returns=None,
        type_comment=None,
        type_params=[],
    )
    definitions = ast.Module(
        body=[*tree.body[:-1], entrypoint],
        type_ignores=[],
    )
    path = tmp_path / "capture_under_test.py"
    path.write_text(
        ast.unparse(ast.fix_missing_locations(definitions)) + "\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("capture_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.workflow = workflow
    module.job = job
    module.step = matches[0]
    module.source = source
    return module


def _json(value) -> bytes:
    return json.dumps(value).encode("utf-8")


def _metadata() -> dict:
    checksum = "h1:" + base64.b64encode(bytes(32)).decode("ascii")
    return {
        "Path": MODULE,
        "Version": VERSION,
        "Sum": checksum,
        "GoModSum": checksum,
        "Info": "/private/" + CANARY,
        "Dir": "/private/" + CANARY,
        "Zip": "/private/" + CANARY,
        "GoMod": "/private/" + CANARY,
        "Origin": {"URL": CANARY},
    }


def _settings(environment) -> dict:
    return {
        "GOVERSION": "go1.26.10",
        "GOMOD": "/dev/null",
        "GOWORK": "off",
        "GOTOOLCHAIN": "local",
        "GOPATH": environment["GOPATH"],
        "GOMODCACHE": environment["GOMODCACHE"],
        "GOSUMDB": "sum.golang.org",
        "GONOSUMDB": "",
        "GOPRIVATE": "",
        "GONOPROXY": "",
        "GOINSECURE": "",
        "GOFLAGS": "",
        "GOPROXY": "https://proxy.golang.org,direct",
        "GOAUTH": "netrc",
    }


@pytest.fixture
def prepared(probe, tmp_path: Path, monkeypatch):
    workspace = tmp_path / "checkout"
    runner = tmp_path / "runner"
    workspace.mkdir()
    runner.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNNER_TEMP", str(runner))
    monkeypatch.setattr(
        probe,
        "shutil",
        SimpleNamespace(which=lambda name: sys.executable),
    )
    monkeypatch.setattr(probe, "sys", SimpleNamespace(version_info=(3, 14)))
    calls = []

    def invoke(command, cwd, environment, seconds):
        calls.append((list(command), Path(cwd), dict(environment), seconds))
        assert not Path(cwd).is_relative_to(workspace)
        assert list(Path(cwd).iterdir()) == []
        assert not Path(environment["GOMODCACHE"]).exists()
        if command[1] == "env":
            return _json(_settings(environment))
        assert command[1:] == ["mod", "download", "-json", MODULE + "@" + VERSION]
        return _json(_metadata())

    monkeypatch.setattr(probe, "bounded", invoke)
    return SimpleNamespace(
        probe=probe,
        workspace=workspace,
        runner=runner,
        calls=calls,
        invoke=invoke,
    )


def _entry(probe):
    output, errors = io.StringIO(), io.StringIO()
    probe.sys = SimpleNamespace(
        version_info=(3, 14),
        stderr=errors,
        exit=sys.exit,
    )
    status = 0
    with redirect_stdout(output), redirect_stderr(errors):
        try:
            probe._entrypoint()
        except SystemExit as error:
            status = error.code
    return status, output.getvalue(), errors.getvalue()


def test_workflow_keeps_capture_pinned_isolated_and_blocking(probe) -> None:
    steps = probe.job["steps"]
    index = steps.index(probe.step)
    assert probe.workflow["permissions"] == {"contents": "read"}
    assert probe.job["needs"] == "policy-integrity"
    assert probe.job["runs-on"] == "ubuntu-24.04"
    assert "continue-on-error" not in probe.job
    assert steps[index - 2]["name"] == "Set up Go"
    assert steps[index - 2]["uses"] == (
        "actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e"
    )
    assert steps[index - 2]["with"]["go-version"] == "1.26.10"
    assert steps[index - 1] == {
        "name": "Set up Python for approved go-jose checksum capture",
        "uses": "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "timeout-minutes": 5,
        "with": {"python-version": "3.14"},
    }
    assert steps[index + 1]["name"] == "Install govulncheck"
    assert set(probe.step) == {"name", "timeout-minutes", "shell", "run"}
    assert probe.step["timeout-minutes"] == 2
    assert probe.step["shell"] == "bash"
    assert probe.LIMIT == 65_536
    assert (probe.MODULE, probe.VERSION) == (MODULE, VERSION)
    assert "shell=False" in probe.source
    assert "start_new_session=True" in probe.source
    assert "process.returncode is None" in probe.source
    assert "process.poll(" not in probe.source
    assert "process.wait(timeout=5)" in probe.source


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        b"{}",
        b"[]",
        b"{} {}",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1,"x":2}',
        b'{"outer":{"x":1,"x":2}}',
    ],
)
def test_parser_or_metadata_rejects_invalid_documents(probe, payload) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        if payload in (b"{}", b"[]"):
            probe.validate_metadata(payload)
        else:
            probe.decode_json(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Path", "github.com/go-jose/go-jose/v3"),
        ("Version", "v4.1.6"),
        ("Path", None),
        ("Sum", None),
        ("GoModSum", None),
        ("Error", ""),
        ("Reuse", False),
    ],
)
def test_identity_missing_values_and_error_fields_fail(probe, field, value) -> None:
    metadata = _metadata()
    metadata[field] = value
    with pytest.raises(ValueError):
        probe.validate_metadata(_json(metadata))


@pytest.mark.parametrize("key", ["Path", "Version", "Sum", "GoModSum"])
def test_missing_required_metadata_keys_fail(probe, key) -> None:
    metadata = _metadata()
    del metadata[key]
    with pytest.raises(ValueError):
        probe.validate_metadata(_json(metadata))


@pytest.mark.parametrize("field", ["Sum", "GoModSum"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        0,
        True,
        "sha256:AAAA",
        "h1:",
        "h1:" + base64.b64encode(bytes(31)).decode("ascii"),
        "h1:" + base64.b64encode(bytes(33)).decode("ascii"),
        "h1:" + "A" * 42 + "B=",
        "h1:" + "A" * 43 + "==",
        "h1:" + "A" * 43 + "=\n",
    ],
)
def test_checksums_require_canonical_32_byte_h1(probe, field, value) -> None:
    metadata = _metadata()
    metadata[field] = value
    with pytest.raises(ValueError):
        probe.validate_metadata(_json(metadata))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GOSUMDB", "off"),
        ("GOSUMDB", "sum.golang.org https://example.invalid"),
        ("GOVERSION", "go1.27.3"),
        ("GOMOD", "/private/go.mod"),
        ("GOWORK", "/private/go.work"),
        ("GOTOOLCHAIN", "auto"),
        ("GOPATH", "/private/cache"),
        ("GOMODCACHE", "/private/cache"),
        ("GONOSUMDB", "*"),
        ("GOPRIVATE", "*"),
        ("GONOPROXY", "*"),
        ("GOINSECURE", "*"),
        ("GOFLAGS", "-modfile=/private/go.mod"),
        ("GOPROXY", "direct"),
        ("GOAUTH", "unapproved-helper"),
        ("UNEXPECTED", CANARY),
    ],
)
def test_unsafe_configuration_stops_before_download(
    prepared,
    monkeypatch,
    key,
    value,
) -> None:
    def altered(command, cwd, environment, seconds):
        data = json.loads(prepared.invoke(command, cwd, environment, seconds))
        data[key] = value
        return _json(data)

    monkeypatch.setattr(prepared.probe, "bounded", altered)
    with pytest.raises(ValueError):
        prepared.probe.capture()
    assert len(prepared.calls) == 1
    assert list(prepared.runner.iterdir()) == []


def test_capture_uses_fresh_state_and_emits_only_four_fields(prepared) -> None:
    before = dict(os.environ)
    status, output, errors = _entry(prepared.probe)
    expected = {key: _metadata()[key] for key in ("Path", "Version", "Sum", "GoModSum")}
    assert status == 0 and errors == ""
    assert json.loads(output) == expected
    assert output.count("\n") == 1
    assert CANARY not in output
    assert len(prepared.calls) == 2
    first, second = prepared.calls
    assert (first[3], second[3]) == (10, 60)
    assert first[1] == second[1]
    assert second[2]["GOPROXY"] == "https://proxy.golang.org"
    assert second[2]["GOAUTH"] == "off"
    assert second[2]["GOWORK"] == "off"
    assert second[2]["GOTOOLCHAIN"] == "local"
    assert Path(second[2]["GOPATH"]).parent == first[1].parent
    assert Path(second[2]["GOMODCACHE"]).parent == first[1].parent
    assert not first[1].exists()
    assert list(prepared.runner.iterdir()) == []
    assert dict(os.environ) == before


@pytest.mark.parametrize("failure", ["config", "download", "metadata", "cleanup"])
def test_failures_never_emit_metadata_or_private_details(
    prepared,
    monkeypatch,
    failure,
) -> None:
    def failing(command, cwd, environment, seconds):
        data = prepared.invoke(command, cwd, environment, seconds)
        if command[1] == "env" and failure == "config":
            settings = json.loads(data)
            settings["GOSUMDB"] = CANARY
            return _json(settings)
        if command[1] == "mod" and failure == "download":
            raise OSError(CANARY)
        if command[1] == "mod" and failure == "metadata":
            metadata = json.loads(data)
            metadata["Error"] = CANARY
            return _json(metadata)
        return data

    monkeypatch.setattr(prepared.probe, "bounded", failing)
    if failure == "cleanup":
        original = prepared.probe.tempfile.TemporaryDirectory

        @contextmanager
        def bad_cleanup(*args, **kwargs):
            with original(*args, **kwargs) as directory:
                yield directory
            raise OSError(CANARY)

        monkeypatch.setattr(
            prepared.probe,
            "tempfile",
            SimpleNamespace(TemporaryDirectory=bad_cleanup),
        )
    status, output, errors = _entry(prepared.probe)
    assert status == 1 and output == "" and errors == FAILURE
    assert CANARY not in output + errors
    assert list(prepared.runner.iterdir()) == []


def test_read_only_download_cache_is_removed(prepared, monkeypatch) -> None:
    def download(command, cwd, environment, seconds):
        data = prepared.invoke(command, cwd, environment, seconds)
        if command[1] == "mod":
            directory = Path(environment["GOMODCACHE"]) / "readonly"
            directory.mkdir(parents=True)
            target = directory / "fixture.txt"
            target.write_text(CANARY, encoding="utf-8")
            target.chmod(0o444)
            directory.chmod(0o555)
        return data

    monkeypatch.setattr(prepared.probe, "bounded", download)
    prepared.probe.capture()
    assert list(prepared.runner.iterdir()) == []


def _local(probe, code: str, directory: Path, seconds: float = 5):
    return probe.bounded(
        [sys.executable, "-I", "-B", "-c", code],
        directory,
        os.environ.copy(),
        seconds,
    )


def test_waited_success_is_reaped_and_never_signalled(probe, tmp_path) -> None:
    with patch.object(probe.os, "killpg", wraps=os.killpg) as kill:
        output = _local(probe, "import os; print(os.getpid())", tmp_path)
    kill.assert_not_called()
    with pytest.raises(ChildProcessError):
        os.waitpid(int(output), os.WNOHANG)


def test_waited_nonzero_exit_is_not_signalled_or_leaked(
    probe,
    tmp_path,
    capsys,
) -> None:
    pid_file = tmp_path / "pid.txt"
    code = (
        "import os,pathlib,sys;"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()));"
        f"sys.stdout.write({CANARY!r});sys.stderr.write({CANARY!r});"
        "sys.exit(7)"
    )
    with patch.object(probe.os, "killpg", wraps=os.killpg) as kill:
        with pytest.raises(ValueError):
            _local(probe, code, tmp_path)
    kill.assert_not_called()
    with pytest.raises(ChildProcessError):
        os.waitpid(int(pid_file.read_text(encoding="utf-8")), os.WNOHANG)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_output_exactly_at_limit_is_accepted(probe, tmp_path) -> None:
    output = _local(probe, "import os; os.write(1,b'x'*65536)", tmp_path)
    assert output == b"x" * 65_536


@pytest.mark.parametrize(
    "stdout,stderr",
    [(65_537, 0), (0, 65_537), (32_768, 32_769)],
)
def test_output_caps_kill_and_reap_unreaped_leader(
    probe,
    tmp_path,
    stdout,
    stderr,
    capsys,
) -> None:
    code = (
        "import os,time;"
        f"os.write(1,b'x'*{stdout});os.write(2,b'x'*{stderr});"
        "time.sleep(30)"
    )
    with patch.object(probe.os, "killpg", wraps=os.killpg) as kill:
        with pytest.raises(ValueError):
            _local(probe, code, tmp_path)
    assert kill.call_count == 1
    pid, sent_signal = kill.call_args.args
    assert sent_signal == signal.SIGKILL
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    "code",
    [
        "import time; time.sleep(30)",
        "import os,time; os.close(1); os.close(2); time.sleep(30)",
        "import os,time\nfor _ in range(1000):\n os.write(1,b'x');time.sleep(.01)",
    ],
)
def test_deadline_covers_streaming_and_closed_pipes(probe, tmp_path, code) -> None:
    started = time.monotonic()
    with patch.object(probe.os, "killpg", wraps=os.killpg) as kill:
        with pytest.raises((TimeoutError, subprocess.TimeoutExpired)):
            _local(probe, code, tmp_path, seconds=0.3)
    assert time.monotonic() - started < 7
    assert kill.call_count == 1
    pid, sent_signal = kill.call_args.args
    assert sent_signal == signal.SIGKILL
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


def test_checkout_overlap_fails_before_any_go_command(
    prepared,
    monkeypatch,
) -> None:
    overlap = prepared.workspace / "runner"
    overlap.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(overlap))
    with pytest.raises(ValueError):
        prepared.probe.capture()
    assert prepared.calls == []
    assert list(overlap.iterdir()) == []
