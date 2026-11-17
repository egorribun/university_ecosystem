"""Privacy and failure preservation for owned live transport diagnostics."""

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
        "service": "gateway", "msg": "Proxy error",
        "path": "/api/v1/auth/login", "err": error,
    }


@pytest.mark.parametrize(
    ("error", "category"),
    [
        ("EOF", "eof"), ("unexpected EOF", "eof"),
        ("context deadline exceeded", "timeout"), ("i/o timeout", "timeout"),
        ("dial: connection refused", "refused"),
        ("read: connection reset by peer", "reset"),
        ("lookup: no such host", "dns"), ("private secret payload", "other"),
    ],
)
def test_error_categories_are_closed(error, category):
    result = diagnostic.summarize("gateway", line(gateway(error)))
    assert result[category] == 1
    assert sum(result.values()) == 1
    assert error not in result


def test_caddy_only_counts_exact_login_transport_errors():
    record = {
        "logger": "http.log.error", "status": 502, "msg": "EOF",
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
        line(gateway())[:-1], b"unstructured secret\n",
        b"2026-11-17T00:00:00Z {bad json}\n",
        line([]), line(gateway() | {"path": "/other"}),
        line(gateway() | {"service": "foreign"}),
        line(gateway() | {"msg": "untrusted"}),
        line(gateway() | {"err": {"private": "value"}}),
        line(gateway("x" * 4097)), line(gateway() | {"padding": "x" * 8192}),
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


def test_failure_capture_rechecks_pins_and_emits_only_closed_counts(
    monkeypatch, capsys
):
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
        "private-token", "password", "secret", "identity", "boot", "a" * 64
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
        returncode=0, stdout=line(gateway()), stderr=b"",
    )
    if stage == "read":
        live._run_live_bounded_read.side_effect = RuntimeError("private secret")
    diagnostic.emit_failure(live, object(), pinned)
    assert capsys.readouterr().out == (
        "live E2E transport diagnostic state=unavailable\n"
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
    source = Path("scripts/live_stand.py").read_text()
    section = source.split("def _e2e_locked(", 1)[1].split("\ndef e2e(", 1)[0]
    assert section.count("_run_live_playwright_diagnosed(owner,") == 2
    assert "_run_live_playwright(" not in section
    assert "_verify_live_caddy_probe_log(" in section


def test_pin_admission_requires_owned_inventory_and_running_boot(monkeypatch):
    live = fake_live()
    live.WORKTREE = object()
    live._assert_core_owner_unchanged = Mock()
    live._verify_stand_owner_compose_resources = Mock(return_value="signed")
    records = {
        service: SimpleNamespace(
            service=service, identity="digest-" + service,
            running=True, status="running",
        )
        for service in ("caddy", "gateway")
    }
    live._live_core_caddy_container_inventory = Mock(return_value=records)
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0, stdout=b'["2026-11-17T00:00:00Z",0]', stderr=b"",
    )
    owner, context = object(), object()
    pins = diagnostic._pins(live, owner, context, 100)
    assert len(pins) == 2
    assert live._assert_core_owner_unchanged.call_count == 2
    live._verify_stand_owner_compose_resources.assert_called_once_with(
        live.WORKTREE, owner, deadline=100, docker_context=context,
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
    live._live_core_caddy_container_inventory = Mock(return_value={
        "caddy": SimpleNamespace(
            service="caddy", identity="digest", running=True, status="running",
        ),
    })
    live._run_live_bounded_read.return_value = SimpleNamespace(
        returncode=0, stdout=boot, stderr=b"",
    )
    with pytest.raises(ValueError):
        diagnostic._pins(live, object(), object(), 100)


def test_admission_errors_are_secondary_and_private(monkeypatch, capsys):
    live = fake_live()
    live._new_live_docker_read_context = Mock(
        side_effect=RuntimeError("private password")
    )
    assert diagnostic.prepare(live, SimpleNamespace(stack="core")) is None
    assert capsys.readouterr().out == ""
