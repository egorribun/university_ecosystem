"""Privacy and failure preservation for owned live transport diagnostics."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import live_transport_diagnostic as diagnostic


def line(record):
    return b"2026-11-17T00:00:00.000Z " + json.dumps(record).encode() + b"\n"


def gateway(error="EOF"):
    return {
        "service": "gateway",
        "msg": "Proxy error",
        "path": "/api/v1/auth/login",
        "err": error,
    }


@pytest.mark.parametrize(
    ("error", "category"),
    [
        ("EOF", "eof"),
        ("unexpected EOF", "eof"),
        ("context deadline exceeded", "timeout"),
        ("i/o timeout", "timeout"),
        ("dial: connection refused", "refused"),
        ("read: connection reset by peer", "reset"),
        ("lookup: no such host", "dns"),
        ("private secret payload", "other"),
    ],
)
def test_error_categories_are_closed(error, category):
    result = diagnostic.summarize("gateway", line(gateway(error)))
    assert result[category] == 1
    assert sum(result.values()) == 1
    assert error not in result


def test_caddy_only_counts_exact_login_transport_errors():
    record = {
        "logger": "http.log.error",
        "status": 502,
        "msg": "EOF",
        "request": {"method": "POST", "uri": "/api/v1/auth/login"},
    }
    assert diagnostic.summarize("caddy", line(record))["eof"] == 1
    for change in (
        {"logger": "http.log.access"},
        {"status": 200},
        {"request": {"method": "GET", "uri": "/api/v1/auth/login"}},
        {"request": {"method": "POST", "uri": "/api/v1/auth/login?secret=x"}},
    ):
        assert sum(diagnostic.summarize("caddy", line(record | change)).values()) == 0


def test_parser_rejects_foreign_malformed_partial_and_oversized_records():
    records = [
        line(gateway())[:-1],
        b"unstructured secret\n",
        b"2026-11-17T00:00:00Z {bad json}\n",
        line([]),
        line(gateway() | {"path": "/other"}),
        line(gateway() | {"service": "foreign"}),
        line(gateway() | {"msg": "untrusted"}),
        line(gateway() | {"err": {"private": "value"}}),
        line(gateway("x" * 4097)),
        line(gateway() | {"padding": "x" * 8192}),
    ]
    for record in records:
        assert sum(diagnostic.summarize("gateway", record).values()) == 0
    with pytest.raises(ValueError):
        diagnostic.summarize("foreign", b"")
    with pytest.raises(ValueError):
        diagnostic.summarize("gateway", b"x" * 65_537)


def test_counts_are_capped():
    assert diagnostic.summarize("gateway", line(gateway()) * 520)["eof"] == 512


def fake_live():
    return SimpleNamespace(
        LIVE_STACK_CORE="core",
        _run_live_playwright=Mock(),
        _caddy_probe_timestamp_argument=lambda value: str(value),
        _run_live_bounded_read=Mock(),
    )


def capture():
    return diagnostic.Capture(
        object(),
        (
            ("caddy", "a" * 64, "identity-a", "boot", 0),
            ("gateway", "b" * 64, "identity-b", "boot", 0),
        ),
        1000,
    )


def test_capture_rechecks_pins_and_emits_only_closed_counts(monkeypatch, capsys):
    live, owner, pinned = fake_live(), object(), capture()
    pins = Mock(return_value=pinned.pins)
    monkeypatch.setattr(diagnostic, "_pins", pins)
    monkeypatch.setattr(diagnostic.time, "time_ns", lambda: 2000_000_000)
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0,
        stdout=line(gateway("EOF private-token@example.invalid")),
        stderr=b"unstructured password secret\n",
    )
    diagnostic.emit_failure(live, owner, pinned)
    output = capsys.readouterr().out
    assert pins.call_count == 2
    assert "service=gateway scope=bounded-unmatched eof=1" in output
    assert "service=caddy scope=bounded-unmatched eof=0" in output
    for private in (
        "private-token",
        "password",
        "secret",
        "identity",
        "boot",
        "a" * 64,
    ):
        assert private not in output
    assert live._run_live_bounded_read.call_count == 2
    for call in live._run_live_bounded_read.call_args_list:
        assert call.args[0][:3] == ["docker", "logs", "--timestamps"]
        assert "--since" in call.args[0] and "--until" in call.args[0]
        assert call.kwargs["maximum_bytes"] == 65_536


@pytest.mark.parametrize("stage", ["before", "after", "read"])
def test_changed_pin_or_read_failure_discards_all_observations(
    stage, monkeypatch, capsys
):
    live, pinned = fake_live(), capture()
    sequence = [pinned.pins, pinned.pins]
    sequence[0 if stage == "before" else 1] = ()
    monkeypatch.setattr(diagnostic, "_pins", Mock(side_effect=sequence))
    monkeypatch.setattr(diagnostic.time, "time_ns", lambda: 2000_000_000)
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0,
        stdout=line(gateway()),
        stderr=b"",
    )
    if stage == "read":
        live._run_live_bounded_read.side_effect = RuntimeError("private secret")
    diagnostic.emit_failure(live, object(), pinned)
    expected = {"before": "prepins", "after": "postpins", "read": "logread-caddy"}
    assert capsys.readouterr().out == (
        f"live E2E transport diagnostic state=unavailable stage={expected[stage]}\n"
    )
    if stage == "before":
        live._run_live_bounded_read.assert_not_called()


def test_original_failure_and_arguments_survive_without_retry(monkeypatch):
    live = fake_live()
    owner = SimpleNamespace(stack="core")
    failure = RuntimeError("original")
    live._run_live_playwright.side_effect = failure
    monkeypatch.setattr(diagnostic, "prepare", Mock(return_value=None))
    emit = Mock()
    monkeypatch.setattr(diagnostic, "emit_failure", emit)
    arguments = {"mode": "core", "specs": ("unchanged",)}
    with pytest.raises(RuntimeError) as raised:
        diagnostic.run(live, owner, arguments)
    assert raised.value is failure
    live._run_live_playwright.assert_called_once_with(**arguments)
    emit.assert_called_once()


def test_success_and_noncore_do_not_emit(monkeypatch):
    live = fake_live()
    prepare, emit = Mock(return_value=None), Mock()
    monkeypatch.setattr(diagnostic, "prepare", prepare)
    monkeypatch.setattr(diagnostic, "emit_failure", emit)
    diagnostic.run(live, SimpleNamespace(stack="core"), {})
    emit.assert_not_called()
    prepare.reset_mock()
    diagnostic.run(live, SimpleNamespace(stack="full"), {})
    prepare.assert_not_called()
    emit.assert_not_called()


def test_e2e_both_original_paths_use_diagnostic_wrapper():
    tree = ast.parse(Path("scripts/live_stand.py").read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_e2e_locked"
    )
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    wrapped = [
        node for node in calls if node.func.id == "_run_live_playwright_diagnosed"
    ]
    assert len(wrapped) == 2
    for call in wrapped:
        assert len(call.args) == 1
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "owner"
        expected = {
            "cwd": "frontend",
            "environment": "playwright_environment",
            "mode": "mode",
            "specs": "selected_specs",
        }
        for keyword in call.keywords:
            assert isinstance(keyword.value, ast.Name)
            assert keyword.value.id == expected[keyword.arg]
    branches = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "selected_specs"
    ]
    assert len(branches) == 1
    selected_call = branches[0].body[0].value
    default_call = branches[0].orelse[0].value
    assert selected_call in wrapped and default_call in wrapped
    assert any(keyword.arg == "specs" for keyword in selected_call.keywords)
    assert not any(keyword.arg == "specs" for keyword in default_call.keywords)
    assert sorted(
        sorted(keyword.arg for keyword in call.keywords) for call in wrapped
    ) == [
        ["cwd", "environment", "mode"],
        ["cwd", "environment", "mode", "specs"],
    ]
    assert not any(node.func.id == "_run_live_playwright" for node in calls)
    assert any(node.func.id == "_verify_live_caddy_probe_log" for node in calls)


def test_pin_admission_requires_owned_inventory_and_running_boot(monkeypatch):
    live = fake_live()
    live.WORKTREE = object()
    live._assert_core_owner_unchanged = Mock()
    live._verify_stand_owner_compose_resources = Mock(return_value="signed")
    records = {
        service: SimpleNamespace(
            service=service,
            identity="digest-" + service,
            running=True,
            status="running",
        )
        for service in ("caddy", "gateway")
    }
    live._live_core_caddy_container_inventory = Mock(return_value=records)
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0,
        stdout=b'["2026-11-17T00:00:00Z",0]',
        stderr=b"",
    )
    owner, context = object(), object()
    pins = diagnostic._pins(live, owner, context, 100)
    assert len(pins) == 2
    assert live._assert_core_owner_unchanged.call_count == 2
    live._verify_stand_owner_compose_resources.assert_called_once_with(
        live.WORKTREE,
        owner,
        deadline=100,
        docker_context=context,
    )
    assert all(pin[3:] == ("2026-11-17T00:00:00Z", 0) for pin in pins)
    records["gateway"].running = False
    with pytest.raises(ValueError):
        diagnostic._pins(live, owner, context, 100)


@pytest.mark.parametrize(
    "boot",
    [b"{}", b"[]", b'["private",0]', b'["2026-11-17T00:00:00Z",true]'],
)
def test_pin_rejects_malformed_restart_evidence(boot):
    live = fake_live()
    live.WORKTREE = object()
    live._assert_core_owner_unchanged = Mock()
    live._verify_stand_owner_compose_resources = Mock()
    live._live_core_caddy_container_inventory = Mock(
        return_value={
            service: SimpleNamespace(
                service=service,
                identity="digest",
                running=True,
                status="running",
            )
            for service in ("caddy", "gateway")
        }
    )
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0,
        stdout=boot,
        stderr=b"",
    )
    with pytest.raises(ValueError):
        diagnostic._pins(live, object(), object(), 100)
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0,
        stdout=b'["2026-11-17T00:00:00Z",0]',
        stderr=b"",
    )
    assert len(diagnostic._pins(live, object(), object(), 100)) == 2


def test_admission_errors_are_secondary_and_private(monkeypatch, capsys):
    live = fake_live()
    live._new_live_docker_read_context = Mock(
        side_effect=RuntimeError("private password")
    )
    assert diagnostic.prepare(live, SimpleNamespace(stack="core")) == (
        diagnostic.Unavailable("admission-context")
    )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("until", [999, 3_601_001])
def test_invalid_window_never_reads_logs(until, monkeypatch, capsys):
    live = fake_live()
    monkeypatch.setattr(diagnostic.time, "time_ns", lambda: until * 1_000_000)
    diagnostic.emit_failure(live, object(), capture())
    live._run_live_bounded_read.assert_not_called()
    assert capsys.readouterr().out == (
        "live E2E transport diagnostic state=unavailable stage=capture-window\n"
    )


def test_stdout_failure_never_replaces_acceptance_failure(monkeypatch):
    live = fake_live()
    owner = SimpleNamespace(stack="core")
    failure = RuntimeError("original acceptance failure")
    live._run_live_playwright.side_effect = failure
    monkeypatch.setattr(diagnostic, "prepare", Mock(return_value=None))
    monkeypatch.setattr(
        "builtins.print", Mock(side_effect=OSError("private output failure"))
    )
    with pytest.raises(RuntimeError) as raised:
        diagnostic.run(live, owner, {})
    assert raised.value is failure
    live._run_live_playwright.assert_called_once_with()


def test_failed_admission_preserves_original_failure(monkeypatch, capsys):
    live = fake_live()
    failure = RuntimeError("original")
    live._run_live_playwright.side_effect = failure
    live._new_live_docker_read_context = Mock(
        side_effect=RuntimeError("private admission detail")
    )
    with pytest.raises(RuntimeError) as raised:
        diagnostic.run(live, SimpleNamespace(stack="core"), {})
    assert raised.value is failure
    live._run_live_playwright.assert_called_once_with()
    assert capsys.readouterr().out == (
        "live E2E transport diagnostic state=unavailable stage=admission-context\n"
    )


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_duplicate_owned_service_rejects_before_logs(count):
    live = fake_live()
    live.WORKTREE = object()
    live._assert_core_owner_unchanged = Mock()
    live._verify_stand_owner_compose_resources = Mock()
    live._live_core_caddy_container_inventory = Mock(
        return_value={
            str(index): SimpleNamespace(
                service="caddy",
                identity="digest",
                running=True,
                status="running",
            )
            for index in range(count)
        }
    )
    with pytest.raises(ValueError, match="ambiguous owned service"):
        diagnostic._pins(live, object(), object(), 100)
    live._run_live_bounded_read.assert_not_called()


def test_pin_admission_stage_is_retained_without_emitting(monkeypatch, capsys):
    live = fake_live()
    live._new_live_docker_read_context = Mock(return_value=object())
    monkeypatch.setattr(
        diagnostic, "_pins", Mock(side_effect=RuntimeError("private admission token"))
    )
    result = diagnostic.prepare(live, SimpleNamespace(stack="core"))
    assert result == diagnostic.Unavailable("admission-pins")
    assert capsys.readouterr().out == ""
    diagnostic.emit_failure(live, object(), result)
    assert capsys.readouterr().out == (
        "live E2E transport diagnostic state=unavailable stage=admission-pins\n"
    )
    live._run_live_bounded_read.assert_not_called()


@pytest.mark.parametrize("service", ["caddy", "gateway"])
@pytest.mark.parametrize("phase", ["logread", "parse"])
def test_service_failure_stage_remains_closed(service, phase, monkeypatch, capsys):
    live, pinned = fake_live(), capture()
    monkeypatch.setattr(diagnostic, "_pins", Mock(return_value=pinned.pins))
    monkeypatch.setattr(diagnostic.time, "time_ns", lambda: 2000_000_000)
    good = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    failed = (
        RuntimeError("private credential bytes")
        if phase == "logread"
        else SimpleNamespace(returncode=0, stdout=b"x" * 65_537, stderr=b"")
    )
    live._run_live_bounded_read.side_effect = (
        [failed] if service == "caddy" else [good, failed]
    )
    diagnostic.emit_failure(live, object(), pinned)
    assert capsys.readouterr().out == (
        f"live E2E transport diagnostic state=unavailable stage={phase}-{service}\n"
    )
    assert live._run_live_bounded_read.call_count == (1 if service == "caddy" else 2)


def test_unknown_stage_objects_are_never_formatted(capsys):
    class Private:
        def __str__(self):
            raise AssertionError("private stage must not be rendered")

        def __hash__(self):
            raise AssertionError("private stage must not be hashed")

    for stage in ("credential-value", Private()):
        diagnostic._emit_unavailable(stage)
        assert capsys.readouterr().out == (
            "live E2E transport diagnostic state=unavailable stage=internal\n"
        )
    diagnostic.emit_failure(fake_live(), object(), diagnostic.Unavailable("secret"))
    assert capsys.readouterr().out == (
        "live E2E transport diagnostic state=unavailable stage=internal\n"
    )


def test_missing_capture_has_no_reads(capsys):
    live = fake_live()
    diagnostic.emit_failure(live, object(), None)
    assert capsys.readouterr().out == (
        "live E2E transport diagnostic state=unavailable stage=capture-missing\n"
    )
    live._run_live_bounded_read.assert_not_called()


def test_output_failure_cannot_replace_original_error(monkeypatch):
    live, pinned = fake_live(), capture()
    owner = SimpleNamespace(stack="core")
    original = RuntimeError("original failure")
    live._run_live_playwright.side_effect = original
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0, stdout=b"", stderr=b""
    )
    monkeypatch.setattr(diagnostic, "prepare", Mock(return_value=pinned))
    monkeypatch.setattr(diagnostic, "_pins", Mock(return_value=pinned.pins))
    monkeypatch.setattr(diagnostic.time, "time_ns", lambda: 2000_000_000)
    # First observed line may already be emitted; output failures cannot undo it.
    output = Mock(side_effect=[None, OSError("private stdout failure"), None])
    monkeypatch.setattr("builtins.print", output)
    with pytest.raises(RuntimeError) as raised:
        diagnostic.run(live, owner, {})
    assert raised.value is original
    live._run_live_playwright.assert_called_once_with()
    assert output.call_args.args == (
        "live E2E transport diagnostic state=unavailable stage=output",
    )
