"""Contract tests for the owned borrowed-session PostgreSQL proof."""

from __future__ import annotations

import json
import runpy
import secrets
from copy import deepcopy
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import AsyncMock, Mock
from xml.etree import ElementTree

import asyncpg
import pytest

from scripts.quality import run_aud363_borrowed_postgres as proof
from tests.fixtures.owned_baseline_postgres import _POSTGRES_IMAGE as _IMAGE

_MODULE = "tests.integration.test_aud363_454_borrowed_session_postgres"
_NAMES = (
    "test_read_committed_revalidation_respects_rls_and_preserves_dirty_uow",
    "test_borrowed_read_committed_broadcast_observes_committed_removal",
    "test_repeatable_read_cannot_authorize_or_publish",
    "test_typing_and_presence_progress_under_saturated_pool",
    "test_removal_committed_while_broadcast_prepares_is_not_delivered",
    "test_removal_during_inflight_send_bounds_exposure_to_that_broadcast",
)


def _report() -> ElementTree.Element:
    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(
        root, "testsuite", tests="6", skipped="0", failures="0", errors="0"
    )
    for name in _NAMES:
        ElementTree.SubElement(suite, "testcase", classname=_MODULE, name=name)
    return root


def _write_report(path: Path, root: ElementTree.Element) -> None:
    ElementTree.ElementTree(root).write(path, encoding="utf-8")


def test_report_accepts_the_six_named_passes(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    _write_report(report, _report())
    proof.validate_report(report)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "unexpected",
        "wrong-class",
        "skipped",
        "failure",
        "error",
        "summary-skip",
        "summary-failure",
        "summary-error",
        "summary-count",
        "missing-summary",
        "extra-suite",
        "wrong-root",
    ],
)
def test_report_rejects_incomplete_or_ambiguous_proof(
    tmp_path: Path, mutation: str
) -> None:
    root = _report()
    suite = root.find("testsuite")
    assert suite is not None
    cases = suite.findall("testcase")
    if mutation == "missing":
        suite.remove(cases[0])
    elif mutation == "duplicate":
        cases[0].set("name", cases[1].get("name", ""))
    elif mutation == "unexpected":
        suite.append(deepcopy(cases[0]))
    elif mutation == "wrong-class":
        cases[0].set("classname", "other.test_module")
    elif mutation in {"skipped", "failure", "error"}:
        ElementTree.SubElement(cases[0], mutation)
    elif mutation.startswith("summary-"):
        field = {
            "skip": "skipped",
            "failure": "failures",
            "error": "errors",
            "count": "tests",
        }[mutation.removeprefix("summary-")]
        suite.set(field, "1")
    elif mutation == "missing-summary":
        del suite.attrib["errors"]
    elif mutation == "extra-suite":
        ElementTree.SubElement(root, "testsuite")
    else:
        root.tag = "other"
    report = tmp_path / "junit.xml"
    _write_report(report, root)
    with pytest.raises(proof.ProofError):
        proof.validate_report(report)


@pytest.mark.parametrize(
    "content",
    [None, "not xml", "<!DOCTYPE x [<!ENTITY e 'x'>]><testsuites>&e;</testsuites>"],
)
def test_report_rejects_missing_malformed_or_unsafe_xml(
    tmp_path: Path, content: str | None
) -> None:
    report = tmp_path / "junit.xml"
    if content is not None:
        report.write_text(content, encoding="utf-8")
    with pytest.raises(proof.ProofError):
        proof.validate_report(report)


_ID = "a" * 64


def test_image_pin_matches_the_existing_postgres_fixture() -> None:
    assert proof._pinned_postgres_image() == _IMAGE


@pytest.mark.parametrize(
    "source",
    [
        None,
        "[invalid",
        "services: {}",
        "services: []",
        "services:\n  postgres:\n    image: 123",
        "services:\n  postgres:\n    image: other",
    ],
)
def test_image_pin_fails_closed_when_the_canonical_source_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str | None
) -> None:
    compose = tmp_path / "compose.yml"
    if source is not None:
        compose.write_text(source, encoding="utf-8")
    monkeypatch.setattr(proof, "_COMPOSE_FILE", compose)
    with pytest.raises(proof.ProofError, match="image pin"):
        proof._pinned_postgres_image()


def _service(password: str) -> dict:
    return {
        "Id": _ID,
        "State": {"Running": True},
        "Config": {
            "Image": _IMAGE,
            "Env": [
                "POSTGRES_USER=aud363_admin",
                f"POSTGRES_PASSWORD={password}",
                "POSTGRES_DB=postgres",
            ],
        },
        "HostConfig": {
            "PortBindings": {
                "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]
            },
            "Memory": 805306368,
            "MemorySwap": 805306368,
            "Binds": None,
            "Tmpfs": {"/var/lib/postgresql/data": "rw,size=268435456"},
        },
        "Mounts": [],
    }


def _mock_inspect(
    monkeypatch: pytest.MonkeyPatch, output: str, status: int = 0
) -> Mock:
    monkeypatch.setattr(proof.shutil, "which", lambda _name: "docker")
    run = Mock(return_value=CompletedProcess([], status, stdout=output, stderr=""))
    monkeypatch.setattr(proof.subprocess, "run", run)
    return run


def test_service_inspection_uses_the_exact_runner_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "x" * 16
    run = _mock_inspect(monkeypatch, json.dumps([_service(password)]))
    assert proof.inspect_service(_ID) == password
    args, kwargs = run.call_args
    assert args[0] == ["docker", "inspect", _ID]
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 15


@pytest.mark.parametrize(
    "mutation",
    [
        "id",
        "image",
        "stopped",
        "host",
        "port",
        "extra-binding",
        "volume",
        "bind",
        "tmpfs",
        "memory",
        "swap",
        "user",
        "db",
        "password",
        "duplicate-password",
        "environment-not-list",
        "environment-invalid-entry",
        "missing-field",
        "multiple-records",
    ],
)
def test_service_inspection_rejects_an_unowned_or_changed_service(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    password = "x" * 16
    record = _service(password)
    host = record["HostConfig"]
    bindings = host["PortBindings"]["5432/tcp"]
    env = record["Config"]["Env"]
    if mutation == "id":
        record["Id"] = "b" * 64
    elif mutation == "image":
        record["Config"]["Image"] = "other-image"
    elif mutation == "stopped":
        record["State"]["Running"] = False
    elif mutation == "host":
        bindings[0]["HostIp"] = "::"
    elif mutation == "port":
        bindings[0]["HostPort"] = "5432"
    elif mutation == "extra-binding":
        bindings.append({"HostIp": "::", "HostPort": "15432"})
    elif mutation == "volume":
        record["Mounts"].append({"Type": "volume"})
    elif mutation == "bind":
        host["Binds"] = ["/host:/data"]
    elif mutation == "tmpfs":
        host["Tmpfs"] = {}
    elif mutation == "memory":
        host["Memory"] = 805306369
    elif mutation == "swap":
        host["MemorySwap"] = -1
    elif mutation == "user":
        env[0] = "POSTGRES_USER=postgres"
    elif mutation == "db":
        env[2] = "POSTGRES_DB=other"
    elif mutation == "password":
        env[1] = "POSTGRES_PASSWORD="
    elif mutation == "duplicate-password":
        env.append("POSTGRES_PASSWORD=other")
    elif mutation == "environment-not-list":
        record["Config"]["Env"] = None
    elif mutation == "environment-invalid-entry":
        env.append(None)
    elif mutation == "missing-field":
        del record["HostConfig"]
    records = [record, record] if mutation == "multiple-records" else [record]
    _mock_inspect(monkeypatch, json.dumps(records))
    with pytest.raises(proof.ProofError):
        proof.inspect_service(_ID)


@pytest.mark.parametrize(
    "failure", ["bad-id", "no-docker", "status", "invalid-json", "timeout"]
)
def test_service_inspection_fails_closed_without_leaking_diagnostics(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    run = _mock_inspect(monkeypatch, "sensitive diagnostic", status=1)
    container_id = "bad" if failure == "bad-id" else _ID
    if failure == "no-docker":
        monkeypatch.setattr(proof.shutil, "which", lambda _name: None)
    elif failure == "invalid-json":
        run.return_value.returncode = 0
    elif failure == "timeout":
        run.side_effect = TimeoutExpired("sensitive diagnostic", 15)
    with pytest.raises(proof.ProofError) as caught:
        proof.inspect_service(container_id)
    assert "sensitive diagnostic" not in str(caught.value)


def _admin_connection() -> AsyncMock:
    connection = AsyncMock()
    connection.fetchrow.side_effect = [
        ("postgres", "aud363_admin", True),
        (True, False, False, False, False, False, False),
    ]
    connection.fetchval.return_value = 0
    return connection


@pytest.mark.asyncio
async def test_bootstrap_creates_only_a_fresh_restricted_role_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_password, role_password = "p" * 24, "a" * 64
    connection = _admin_connection()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(proof.asyncpg, "connect", connect)

    await proof.bootstrap(admin_password, role_password)

    connect.assert_awaited_once_with(
        host="127.0.0.1",
        port=15432,
        user="aud363_admin",
        password=admin_password,
        database="postgres",
        timeout=5,
    )
    statements = [call.args[0] for call in connection.execute.await_args_list]
    assert len(statements) == 3
    assert statements[0].startswith("CREATE ROLE audit_ws_reader LOGIN NOSUPERUSER")
    assert all(
        keyword in statements[0]
        for keyword in (
            "NOCREATEDB",
            "NOCREATEROLE",
            "NOINHERIT",
            "NOREPLICATION",
            "NOBYPASSRLS",
        )
    )
    assert (
        "CREATE DATABASE audit_ws_borrowed OWNER audit_ws_reader TEMPLATE template0"
        == statements[1]
    )
    assert statements[2] == "REVOKE ALL ON DATABASE audit_ws_borrowed FROM PUBLIC"
    assert all(
        "DROP" not in statement and "IF NOT EXISTS" not in statement
        for statement in statements
    )
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "bad-password",
        "connect",
        "admin-identity",
        "role-collision",
        "db-collision",
        "role-privileges",
        "membership",
    ],
)
async def test_bootstrap_rejects_unowned_or_failed_setup_without_cleanup(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    valid_password = secrets.token_hex(32)
    role_password = valid_password[:-1] if failure == "bad-password" else valid_password
    connection = _admin_connection()
    connect = AsyncMock(return_value=connection)
    if failure == "connect":
        connect.side_effect = OSError("sensitive connection diagnostic")
    elif failure == "admin-identity":
        connection.fetchrow.side_effect = [("postgres", "other", True)]
    elif failure == "role-collision":
        connection.execute.side_effect = asyncpg.DuplicateObjectError(
            "sensitive collision"
        )
    elif failure == "db-collision":
        connection.execute.side_effect = [
            None,
            asyncpg.DuplicateDatabaseError("sensitive collision"),
        ]
    elif failure == "role-privileges":
        connection.fetchrow.side_effect = [
            ("postgres", "aud363_admin", True),
            (True, True, False, False, False, False, False),
        ]
    elif failure == "membership":
        connection.fetchval.return_value = 1
    monkeypatch.setattr(proof.asyncpg, "connect", connect)

    with pytest.raises(proof.ProofError) as caught:
        await proof.bootstrap("p" * 24, role_password)

    assert "sensitive" not in str(caught.value)
    assert all(
        "DROP" not in call.args[0] for call in connection.execute.await_args_list
    )
    if failure in {"bad-password", "connect"}:
        connection.close.assert_not_awaited()
    else:
        connection.close.assert_awaited_once()


def test_pytest_child_is_isolated_and_runs_all_six_named_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stale_keys = (
        "DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET",
        "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL",
        "USE_TESTCONTAINERS_POSTGRES",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_TESTRUNUID",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PYTHONOPTIMIZE",
        "AUD363_ADMIN_PASSWORD",
        "AUD363_POSTGRES_CONTAINER_ID",
    )
    for key in stale_keys:
        monkeypatch.setenv(key, "stale")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        report_arg = next(arg for arg in args if arg.startswith("--junitxml="))
        _write_report(Path(report_arg.removeprefix("--junitxml=")), _report())
        return CompletedProcess(
            args, 0, stdout="sensitive stdout", stderr="sensitive stderr"
        )

    monkeypatch.setattr(proof.subprocess, "run", run)
    role_password = "a" * 64
    proof.run_proof(role_password, tmp_path)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:3] == [proof.sys.executable, "-m", "pytest"]
    assert [arg.split("::", 1)[1] for arg in args if "::" in arg] == list(_NAMES)
    assert role_password not in " ".join(args)
    assert "-n" in args and "0" in args
    assert "xfail_strict=true" in args
    assert kwargs["timeout"] == 180
    assert kwargs["stdout"] == proof.subprocess.DEVNULL
    assert kwargs["stderr"] == proof.subprocess.DEVNULL
    child = kwargs["env"]
    assert all(key not in child for key in stale_keys)
    assert child["AUD363_WS_DISPOSABLE"] == "1"
    assert child["AUD363_WS_DISPOSABLE_PG_URL"].endswith(
        "@127.0.0.1:15432/audit_ws_borrowed"
    )
    assert role_password in child["AUD363_WS_DISPOSABLE_PG_URL"]
    assert not capsys.readouterr().out


@pytest.mark.parametrize(
    "failure",
    ["invalid-password", "exit", "timeout", "oserror", "missing-report", "bad-report"],
)
def test_pytest_child_fails_closed_and_does_not_print_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    def run(args, **_kwargs):
        if failure == "timeout":
            raise TimeoutExpired("sensitive command", 180, output="sensitive output")
        if failure == "oserror":
            raise OSError("sensitive diagnostic")
        if failure == "bad-report":
            report_arg = next(arg for arg in args if arg.startswith("--junitxml="))
            Path(report_arg.removeprefix("--junitxml=")).write_text(
                "bad report", encoding="utf-8"
            )
        return CompletedProcess(
            args, 1 if failure == "exit" else 0, stdout="sensitive output"
        )

    monkeypatch.setattr(proof.subprocess, "run", run)
    with pytest.raises(proof.ProofError) as caught:
        proof.run_proof("bad" if failure == "invalid-password" else "a" * 64, tmp_path)
    assert "sensitive" not in str(caught.value)
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_main_rechecks_service_before_running_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUD363_POSTGRES_CONTAINER_ID", _ID)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(proof.secrets, "token_hex", lambda _n: "a" * 64)
    order = []
    inspect = Mock(side_effect=lambda *_args: (order.append("inspect"), "p" * 24)[1])
    provision = AsyncMock(side_effect=lambda *_args: order.append("bootstrap"))
    run = Mock(side_effect=lambda *_args: order.append("pytest"))
    monkeypatch.setattr(proof, "inspect_service", inspect)
    monkeypatch.setattr(proof, "bootstrap", provision)
    monkeypatch.setattr(proof, "run_proof", run)

    assert proof.main() == 0
    assert order == ["inspect", "bootstrap", "inspect", "pytest"]
    assert inspect.call_count == 2
    provision.assert_awaited_once_with("p" * 24, "a" * 64)
    run.assert_called_once_with("a" * 64, tmp_path)
    captured = capsys.readouterr()
    assert "a" * 64 not in captured.out + captured.err
    assert "p" * 24 not in captured.out + captured.err


@pytest.mark.parametrize(
    "failure",
    ["id", "temp", "inspect", "bootstrap", "reinspect", "admin-changed", "pytest"],
)
def test_main_fails_closed_without_exposing_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    monkeypatch.setenv("AUD363_POSTGRES_CONTAINER_ID", "" if failure == "id" else _ID)
    monkeypatch.setenv(
        "RUNNER_TEMP", str(tmp_path / "missing" if failure == "temp" else tmp_path)
    )
    monkeypatch.setattr(proof.secrets, "token_hex", lambda _n: "a" * 64)
    inspect = Mock(return_value="p" * 24)
    provision = AsyncMock()
    run = Mock()
    if failure == "inspect":
        inspect.side_effect = proof.ProofError("sensitive detail")
    elif failure == "bootstrap":
        provision.side_effect = proof.ProofError("sensitive detail")
    elif failure == "reinspect":
        inspect.side_effect = ["p" * 24, proof.ProofError("sensitive detail")]
    elif failure == "admin-changed":
        inspect.side_effect = ["p" * 24, "q" * 24]
    elif failure == "pytest":
        run.side_effect = proof.ProofError("sensitive detail")
    monkeypatch.setattr(proof, "inspect_service", inspect)
    monkeypatch.setattr(proof, "bootstrap", provision)
    monkeypatch.setattr(proof, "run_proof", run)

    assert proof.main() == 1
    assert "sensitive" not in capsys.readouterr().err
    if failure != "pytest":
        run.assert_not_called()


def test_cli_rejects_missing_configuration_without_connecting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AUD363_POSTGRES_CONTAINER_ID", raising=False)
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(proof.__file__, run_name="__main__")
    assert caught.value.code == 1
    assert "OWNED_POSTGRES_REJECTED" in capsys.readouterr().err


def test_workflow_binds_the_owned_service_and_proof_step() -> None:
    import shlex

    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (root / ".github/workflows/reusable-backend-tests.yml").read_text(
            encoding="utf-8"
        )
    )
    job = workflow["jobs"]["integration-tests"]
    service = job["services"]["aud363"]
    assert service["image"] == _IMAGE
    assert set(service["env"]) == {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}
    assert service["env"]["POSTGRES_USER"] == "aud363_admin"
    assert service["env"]["POSTGRES_DB"] == "postgres"
    assert service["env"]["POSTGRES_PASSWORD"]
    assert service["ports"] == ["127.0.0.1:15432:5432"]
    assert shlex.split(service["options"]) == [
        "--memory",
        "768m",
        "--memory-swap",
        "768m",
        "--tmpfs",
        "/var/lib/postgresql/data:rw,size=268435456",
        "--health-cmd",
        "pg_isready -U aud363_admin -d postgres",
        "--health-interval",
        "10s",
        "--health-timeout",
        "5s",
        "--health-retries",
        "5",
    ]
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    selected = "Verify borrowed-session PostgreSQL proofs (AUD-363 and AUD-454)"
    assert names.count(selected) == 1
    assert (
        names.index("Install dependencies")
        < names.index(selected)
        < names.index("Wait for PostgreSQL")
    )
    step = steps[names.index(selected)]
    assert step["timeout-minutes"] == 5
    assert step["env"] == {
        "AUD363_POSTGRES_CONTAINER_ID": "${{ job.services.aud363.id }}"
    }
    assert step["run"] == (
        "uv run --frozen --no-sync python scripts/quality/run_aud363_borrowed_postgres.py"
    )
