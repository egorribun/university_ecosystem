"""Privacy and failure contracts for the additive disposition reproduction."""

import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality import disposition_contract_diagnostic as diagnostic

pytest_plugins = ("pytester",)


def test_source_ids_require_exact_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = b"def test_owned():\n    pass\n"
    path = tmp_path / "owned.py"
    path.write_bytes(data)
    expected = hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data,
        usedforsecurity=False,
    ).digest()
    monkeypatch.setattr(diagnostic, "_TARGETS", {"owned.py": ("baseline", expected)})
    assert diagnostic.source_catalog(tmp_path) == {
        ("owned.py", "test_owned"): ("baseline", 1)
    }
    path.write_bytes(data + b"\n")
    with pytest.raises(ValueError, match="source identity mismatch"):
        diagnostic.source_catalog(tmp_path)


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_reporter_never_emits_parameters_or_failure_payload(
    tmp_path: Path, phase: str
) -> None:
    private = "synthetic-private-parameter"
    nodeid = "owned.py::test_owned[" + private + "]"
    recorder = diagnostic.Recorder(
        tmp_path, {("owned.py", "test_owned"): ("baseline", 17)}
    )
    recorder.pytest_collection_modifyitems(
        [
            SimpleNamespace(
                nodeid=nodeid,
                path=tmp_path / "owned.py",
                originalname="test_owned",
                cls=None,
            )
        ]
    )
    recorder.pytest_runtest_logreport(
        SimpleNamespace(
            nodeid=nodeid,
            when=phase,
            outcome="failed",
            longrepr=private,
            capstdout=private,
            capstderr=private,
        )
    )
    summary = recorder.summary(1)
    assert summary["failure_ids"] == [
        {"module": "baseline", "line": 17, "phase": phase}
    ]
    assert summary["report_counts"][phase]["failed"] == 1
    encoded = json.dumps(summary)
    assert private not in encoded
    assert "test_owned" not in encoded
    assert "owned.py" not in encoded


def test_unknown_and_excessive_identities_are_not_exported(tmp_path: Path) -> None:
    recorder = diagnostic.Recorder(tmp_path, {})
    recorder.pytest_runtest_logreport(
        SimpleNamespace(nodeid="unmapped", when="call", outcome="failed")
    )
    recorder.pytest_collectreport(SimpleNamespace(failed=True))
    assert recorder.summary(1)["unmapped_report_count"] == 1
    assert recorder.summary(1)["collection_failure_count"] == 1
    assert recorder.summary(1)["failure_ids"] == []
    for index in range(diagnostic._MAX_FAILURE_IDS + 2):
        nodeid = str(index)
        recorder.items[nodeid] = ("baseline", index + 1)
        recorder.pytest_runtest_logreport(
            SimpleNamespace(nodeid=nodeid, when="call", outcome="failed")
        )
    summary = recorder.summary(1)
    assert len(summary["failure_ids"]) == diagnostic._MAX_FAILURE_IDS
    assert summary["truncated"] is True


@pytest.mark.parametrize("exit_code", list(pytest.ExitCode))
def test_reproduction_preserves_pytest_exit_and_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: pytest.ExitCode
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(diagnostic.sys, "path", list(diagnostic.sys.path))
    monkeypatch.setattr(diagnostic, "source_catalog", lambda root: {})
    calls = []

    def run(arguments, *, plugins):
        calls.append((arguments, plugins))
        return exit_code

    monkeypatch.setattr(pytest, "main", run)
    code, summary = diagnostic.reproduce(tmp_path)
    assert code == int(exit_code)
    assert summary["pytest_exit_code"] == int(exit_code)
    assert len(calls) == 1
    assert calls[0][0] == list(diagnostic._TARGETS)
    assert len(calls[0][1]) == 1
    assert isinstance(calls[0][1][0], diagnostic.Recorder)


def test_duplicate_collection_ids_are_unmapped(tmp_path: Path) -> None:
    recorder = diagnostic.Recorder(
        tmp_path, {("owned.py", "test_owned"): ("baseline", 17)}
    )
    item = SimpleNamespace(
        nodeid="owned.py::test_owned",
        path=tmp_path / "owned.py",
        originalname="test_owned",
        cls=None,
    )
    recorder.pytest_collection_modifyitems([item, item])
    recorder.pytest_runtest_logreport(
        SimpleNamespace(nodeid=item.nodeid, when="call", outcome="failed")
    )
    assert recorder.summary(1)["failure_ids"] == []
    assert recorder.summary(1)["unmapped_report_count"] == 1


@pytest.mark.parametrize(
    "mutation",
    ["extra", "raw_module", "raw_phase", "bool_line", "negative_count", "exit_drift"],
)
def test_closed_receipt_rejects_payload_fields(tmp_path: Path, mutation: str) -> None:
    summary = diagnostic.Recorder(tmp_path, {}).summary(1)
    summary["failure_ids"] = [{"module": "baseline", "line": 17, "phase": "call"}]
    if mutation == "extra":
        summary["raw"] = "synthetic-private"
    elif mutation == "raw_module":
        summary["failure_ids"][0]["module"] = "synthetic-private"
    elif mutation == "raw_phase":
        summary["failure_ids"][0]["phase"] = "synthetic-private"
    elif mutation == "bool_line":
        summary["failure_ids"][0]["line"] = True
    elif mutation == "negative_count":
        summary["unmapped_report_count"] = -1
    else:
        summary["pytest_exit_code"] = 0
    with pytest.raises(ValueError, match="summary invalid"):
        diagnostic.encode_summary(summary, 1)


def test_real_child_mutes_streams_fds_capture_and_atexit(
    pytester: pytest.Pytester,
) -> None:
    root = Path(__file__).resolve().parents[1]
    subject = pytester.path / "subject"
    subject.mkdir()
    (subject / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    payload = (
        "import atexit, os, sys\n"
        "def test_owned():\n"
        "    print('synthetic-canary-stream')\n"
        "    print('synthetic-canary-stderr', file=sys.stderr)\n"
        "    os.write(1, b'synthetic-canary-fd1')\n"
        "    os.write(2, b'synthetic-canary-fd2')\n"
        "    atexit.register(os.write, 1, b'synthetic-canary-atexit')\n"
        "    assert False, 'synthetic-canary-assertion'\n"
    )
    (subject / "test_owned.py").write_text(payload, encoding="utf-8")
    script = pytester.makepyfile(
        runner=(
            "import hashlib, os, sys\n"
            f"sys.path.insert(0, {str(root)!r})\n"
            "from scripts.quality import disposition_contract_diagnostic as d\n"
            f"os.environ['GITHUB_WORKSPACE'] = {str(pytester.path)!r}\n"
            f"data = {payload.encode()!r}\n"
            "digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\\0' + data,"
            " usedforsecurity=False).digest()\n"
            "d._TARGETS = {'test_owned.py': ('baseline', digest)}\n"
            f"raise SystemExit(d.main(['--subject-root', {str(subject)!r}]))\n"
        )
    )
    result = pytester.run(sys.executable, script, timeout=30)
    assert result.ret == 1
    output = result.stdout.str()
    assert "synthetic-canary" not in output
    assert result.stderr.str() == ""
    receipt = json.loads(output)
    assert receipt["pytest_exit_code"] == 1
    assert receipt["report_counts"]["call"]["failed"] == 1
    assert receipt["failure_ids"] == [
        {"module": "baseline", "line": 2, "phase": "call"}
    ]


@pytest.mark.parametrize("code", range(7))
@pytest.mark.parametrize("output_failure", [False, True])
def test_main_fd_protocol_and_output_failure_preserve_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    output_failure: bool,
) -> None:
    root = tmp_path / "subject"
    root.mkdir()
    calls = []
    output = bytearray()

    def write(fd, data):
        assert fd == 9
        if output_failure:
            raise OSError("synthetic private output error")
        count = min(7, len(data))
        output.extend(data[:count])
        return count

    fake_os = SimpleNamespace(
        dup=lambda fd: calls.append(("dup", fd)) or 9,
        set_inheritable=lambda fd, value: calls.append(("inherit", fd, value)),
        open=lambda path, flags: calls.append(("open", path, flags)) or 10,
        dup2=lambda source, target: calls.append(("dup2", source, target)),
        close=lambda fd: calls.append(("close", fd)),
        write=write,
        environ={"GITHUB_WORKSPACE": str(tmp_path)},
        devnull="/dev/null",
        O_WRONLY=1,
    )
    monkeypatch.setattr(diagnostic, "os", fake_os)
    monkeypatch.setattr(
        diagnostic,
        "sys",
        SimpleNamespace(stdout=None, stderr=None, argv=["reporter"]),
    )
    monkeypatch.setattr(
        diagnostic, "open", lambda *args, **kwargs: io.StringIO(), raising=False
    )

    def reproduce(subject):
        assert subject == root
        assert calls == [
            ("dup", 1),
            ("inherit", 9, False),
            ("open", "/dev/null", 1),
            ("dup2", 10, 1),
            ("dup2", 10, 2),
            ("close", 10),
        ]
        return code, diagnostic.Recorder(root, {}).summary(code)

    monkeypatch.setattr(diagnostic, "reproduce", reproduce)
    result = diagnostic.main(["--subject-root", str(root)])
    assert result == (3 if output_failure and code == 0 else code)
    assert calls[-1] == ("close", 9)
    if output_failure:
        assert output == b""
    else:
        assert json.loads(output)["pytest_exit_code"] == code
        assert len(output) <= diagnostic._MAX_OUTPUT_BYTES + 1


@pytest.mark.parametrize("exception", [OSError, RuntimeError, KeyboardInterrupt])
def test_entrypoint_never_renders_bootstrap_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    exception: type[BaseException],
) -> None:
    def fail():
        raise exception("synthetic private bootstrap message")

    monkeypatch.setattr(diagnostic, "main", fail)
    assert diagnostic.entrypoint() == 3
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    "failure",
    [
        "dup",
        "inherit",
        "null_open",
        "stdout_dup",
        "stderr_dup",
        "stdout_open",
        "stderr_open",
    ],
)
def test_bootstrap_failure_closes_owned_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    capsys: pytest.CaptureFixture,
) -> None:
    calls = []
    streams = []

    def operation(name, result=None):
        calls.append(name)
        if name == failure:
            raise OSError("synthetic private bootstrap message")
        return result

    def python_open(*args, **kwargs):
        name = "stdout_open" if not streams else "stderr_open"
        operation(name)
        stream = io.StringIO()
        streams.append(stream)
        return stream

    fake_os = SimpleNamespace(
        dup=lambda fd: operation("dup", 9),
        set_inheritable=lambda fd, value: operation("inherit"),
        open=lambda path, flags: operation("null_open", 10),
        dup2=lambda source, target: operation(
            "stdout_dup" if target == 1 else "stderr_dup"
        ),
        close=lambda fd: calls.append(("close", fd)),
        devnull="/dev/null",
        O_WRONLY=1,
    )
    monkeypatch.setattr(diagnostic, "os", fake_os)
    monkeypatch.setattr(
        diagnostic,
        "sys",
        SimpleNamespace(stdout=None, stderr=None, argv=["reporter"]),
    )
    monkeypatch.setattr(diagnostic, "open", python_open, raising=False)

    def forbidden_reproduce(root):
        pytest.fail("bootstrap failure must not execute tests")

    monkeypatch.setattr(diagnostic, "reproduce", forbidden_reproduce)
    assert diagnostic.entrypoint() == 3
    closes = [call for call in calls if isinstance(call, tuple)]
    expected = [] if failure == "dup" else [("close", 9)]
    if failure in {"stdout_dup", "stderr_dup", "stdout_open", "stderr_open"}:
        expected.insert(0, ("close", 10))
    assert closes == expected
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("code", [-1, 7, True, "6"])
def test_receipt_rejects_unsupported_exit_codes(tmp_path: Path, code: object) -> None:
    summary = diagnostic.Recorder(tmp_path, {}).summary(1)
    summary["pytest_exit_code"] = code
    with pytest.raises(ValueError, match="summary invalid"):
        diagnostic.encode_summary(summary, code)
