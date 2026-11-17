"""Control-plane tests; these do not substitute for real Valkey acceptance."""

from __future__ import annotations

import json
from ipaddress import IPv4Address
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from redis.exceptions import ResponseError

from scripts.quality import owned_valkey_ttl_characterization as target


def _record(owner):
    binding = [{"HostIp": "127.0.0.1", "HostPort": str(target.PORT)}]
    return {
        "Id": owner.container_id,
        "State": {"Running": True},
        "Config": {
            "Image": target.load_image_pin(),
            "Labels": {
                target.LABEL: "true",
                target.LABEL + ".run": owner.run,
                target.LABEL + ".attempt": owner.attempt,
                target.LABEL + ".job": owner.job,
            },
        },
        "HostConfig": {"PortBindings": {"6379/tcp": binding}},
        "NetworkSettings": {"Ports": {"6379/tcp": binding}},
        "Mounts": [],
    }


def test_valid_disposable_service_admission(monkeypatch):
    owner = target.Ownership("a" * 64, "123", "1", "valkey-ttl")
    runner = Mock(return_value=json.dumps(_record(owner)))
    monkeypatch.setattr(target, "inspect_output", runner)
    target.inspect_owned(owner)
    runner.assert_called_once_with(owner.container_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Id", "b" * 64),
        ("State", {"Running": False}),
        ("Mounts", [{"Source": "/unowned"}]),
        ("Config", {"Image": "valkey:latest", "Labels": {}}),
        (
            "HostConfig",
            {
                "PortBindings": {
                    "6379/tcp": [
                        {"HostIp": str(IPv4Address(0)), "HostPort": "6382"}
                    ]
                }
            },
        ),
        (
            "NetworkSettings",
            {"Ports": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6379"}]}},
        ),
    ],
)
def test_service_identity_mismatch_rejected(monkeypatch, field, value):
    owner = target.Ownership("a" * 64, "123", "1", "valkey-ttl")
    record = _record(owner)
    record[field] = value
    monkeypatch.setattr(
        target,
        "inspect_output",
        Mock(return_value=json.dumps(record)),
    )
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_owned(owner)


@pytest.mark.parametrize("label", ["run", "attempt", "job"])
def test_workflow_identity_mismatch_rejected(monkeypatch, label):
    owner = target.Ownership("a" * 64, "123", "1", "valkey-ttl")
    record = _record(owner)
    record["Config"]["Labels"][target.LABEL + "." + label] = "other"
    monkeypatch.setattr(
        target,
        "inspect_output",
        Mock(return_value=json.dumps(record)),
    )
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_owned(owner)


def test_invalid_container_never_invokes_docker(monkeypatch):
    runner = Mock()
    monkeypatch.setattr(target, "inspect_output", runner)
    with pytest.raises(target.Rejected):
        target.inspect_owned(target.Ownership("--host=external", "123", "1", "job"))
    runner.assert_not_called()


def test_denial_requires_unchanged_value_type_and_absolute_expiry(monkeypatch):
    state = (b"hash", b"serialized-original", 1234567890000)
    snapshot = Mock(return_value=state)
    monkeypatch.setattr(target, "snapshot", snapshot)
    client = Mock()
    client.eval.side_effect = ResponseError("ACL_REJECTED")
    target.expect_denial(Mock(), client, "owned:key", "600", "ACL_REJECTED")
    assert snapshot.call_count == 2


@pytest.mark.parametrize(
    "after",
    [
        (b"none", None, -2),
        (b"hash", b"changed", 1234567890000),
        (b"hash", b"serialized-original", -1),
        (b"hash", b"serialized-original", 1234567900000),
    ],
)
def test_provider_error_with_partial_write_is_not_accepted(monkeypatch, after):
    monkeypatch.setattr(
        target,
        "snapshot",
        Mock(side_effect=[(b"hash", b"serialized-original", 1234567890000), after]),
    )
    client = Mock()
    client.eval.side_effect = ResponseError("ACL_REJECTED")
    with pytest.raises(target.Rejected, match=r"^DENIAL_MUTATED_KEY$"):
        target.expect_denial(Mock(), client, "owned:key", "600", "ACL_REJECTED")


def test_successful_command_cannot_satisfy_denial_control(monkeypatch):
    monkeypatch.setattr(target, "snapshot", Mock(return_value=(b"none", None, -2)))
    with pytest.raises(target.Rejected, match=r"^DENIAL_NOT_OBSERVED$"):
        target.expect_denial(Mock(), Mock(), "owned:key", "600", "ACL_REJECTED")


def test_unrelated_lua_error_cannot_satisfy_acl_denial(monkeypatch):
    monkeypatch.setattr(target, "snapshot", Mock(return_value=(b"none", None, -2)))
    client = Mock()
    client.eval.side_effect = ResponseError("SECRET_UNKNOWN_FUNCTION")
    with pytest.raises(target.Rejected, match=r"^UNEXPECTED_DENIAL$") as error:
        target.expect_denial(Mock(), client, "owned:key", "600", "ACL_REJECTED")
    assert "SECRET" not in str(error.value)


def test_generic_error_cannot_satisfy_server_acl_denial(monkeypatch):
    monkeypatch.setattr(target, "snapshot", Mock(return_value=(b"none", None, -2)))
    client = Mock()
    client.eval.side_effect = ResponseError("NOPERM synthetic wrong class")
    with pytest.raises(target.Rejected, match=r"^UNEXPECTED_DENIAL$"):
        target.expect_denial(Mock(), client, "owned:key", "600", "NOPERM")


def test_raw_queue_failure_disconnects_dedicated_socket():
    from unittest.mock import MagicMock

    connection = Mock()
    connection.read_response.return_value = b"NOT_OK"
    transaction = Mock(connection=connection)
    context = MagicMock()
    context.__enter__.return_value = transaction
    client = Mock()
    client.client.return_value = context
    with pytest.raises(target.Rejected, match=r"^QUEUE_CONTROL_FAILED$"):
        target.transaction_control(Mock(), client, "owned:key", Mock())
    connection.disconnect.assert_called_once_with()
    context.__exit__.assert_called_once()


def test_acl_setup_failure_still_cleans_owned_fixture():
    admin = Mock()
    admin.exists.return_value = 0

    def command(*args):
        if args[:2] == ("ACL", "GETUSER"):
            return None
        if args[:2] == ("ACL", "SETUSER"):
            raise ResponseError("PRIVATE_SETUP_FAILURE")
        return 1

    admin.execute_command.side_effect = command
    with pytest.raises(ResponseError):
        target.characterize(admin, Mock())
    assert any(
        call.args[:2] == ("ACL", "DELUSER")
        for call in admin.execute_command.call_args_list
    )
    admin.delete.assert_called_once()


def test_ownership_change_prevents_all_cleanup():
    admin = Mock()
    admin.exists.return_value = 0
    admin.execute_command.side_effect = [None, ResponseError("PRIVATE_SETUP_FAILURE")]
    check_owner = Mock(side_effect=[None, None, target.Rejected("SERVER_REPLACED")])
    with pytest.raises(target.Rejected, match=r"^SERVER_REPLACED$"):
        target.characterize(admin, check_owner)
    assert not any(
        call.args[:2] == ("ACL", "DELUSER")
        for call in admin.execute_command.call_args_list
    )
    admin.delete.assert_not_called()


def test_collision_does_not_delete_foreign_keys_or_user():
    admin = Mock()
    admin.execute_command.return_value = {"foreign": True}
    with pytest.raises(target.Rejected, match=r"^USER_COLLISION$"):
        target.characterize(admin, Mock())
    admin.delete.assert_not_called()
    assert len(admin.execute_command.call_args_list) == 1


@pytest.mark.parametrize(
    "section,field", [("HostConfig", "PortBindings"), ("NetworkSettings", "Ports")]
)
def test_extra_published_port_is_rejected(monkeypatch, section, field):
    owner = target.Ownership("a" * 64, "123", "1", "valkey-ttl")
    record = _record(owner)
    record[section][field]["9999/tcp"] = [
        {"HostIp": str(IPv4Address(0)), "HostPort": "9999"}
    ]
    monkeypatch.setattr(
        target, "inspect_output", Mock(return_value=json.dumps(record))
    )
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_owned(owner)


def test_raw_queue_acknowledgements_precede_acl_change():
    from unittest.mock import MagicMock

    connection = Mock()
    connection.read_response.side_effect = [
        b"OK",
        b"QUEUED",
        b"QUEUED",
        [0, target.NoPermissionError("denied")],
    ]
    context = MagicMock()
    context.__enter__.return_value = Mock(connection=connection)
    client = Mock()
    client.client.return_value = context
    admin = Mock()
    admin.execute_command.return_value = 1234567890000
    admin.hget.return_value = b"partial"

    def permissions(*denied):
        assert denied == ("-expire",)
        assert connection.read_response.call_count == 3

    target.transaction_control(admin, client, "owned:key", permissions)
    assert [call.args for call in connection.send_command.call_args_list] == [
        ("MULTI",),
        ("HSET", "owned:key", "value", "partial"),
        ("EXPIRE", "owned:key", 1200),
        ("EXEC",),
    ]
    connection.disconnect.assert_called_once_with()


def test_client_close_failure_does_not_skip_owned_cleanup(monkeypatch):
    admin = Mock()
    admin.exists.return_value = 0
    admin.execute_command.side_effect = lambda *args: (
        None if args[:2] == ("ACL", "GETUSER") else 1
    )
    admin.hset.side_effect = RuntimeError("PRIVATE_SETUP_FAILURE")
    client = Mock()
    client.close.side_effect = RuntimeError("PRIVATE_CLOSE_FAILURE")
    monkeypatch.setattr(target.redis, "Redis", Mock(return_value=client))
    with pytest.raises(target.Rejected, match=r"^CLIENT_CLEANUP_REJECTED$") as error:
        target.characterize(admin, Mock())
    assert "PRIVATE" not in str(error.value)
    assert any(
        call.args[:2] == ("ACL", "DELUSER")
        for call in admin.execute_command.call_args_list
    )
    admin.delete.assert_called_once()


def _socket_transport(monkeypatch, response):
    reader = Mock()
    reader.read = AsyncMock(side_effect=[response, b""])
    writer = Mock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(target.asyncio, "open_unix_connection", connect)
    monkeypatch.setattr(
        target.os,
        "lstat",
        Mock(return_value=SimpleNamespace(st_mode=target.stat.S_IFSOCK)),
    )
    return reader, writer, connect


def test_fixed_socket_request_and_positive_framing(monkeypatch):
    _, writer, connect = _socket_transport(
        monkeypatch, b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    )
    assert target.inspect_output("a" * 64) == "{}"
    connect.assert_awaited_once_with(path="/var/run/docker.sock", limit=16384)
    writer.write.assert_called_once_with(
        b"GET /v1.47/containers/"
        + b"a" * 64
        + b"/json HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n"
    )
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.parametrize(
    "response",
    [
        b"HTTP/1.0 302 Found\r\nLocation: http://other\r\n\r\n{}",
        b"HTTP/1.0 500 Error\r\n\r\n{}",
        b"HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\n{}",
        b"HTTP/1.0 200 OK\r\nContent-Length: 1\r\n\r\n{}",
        b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
        b"HTTP/1.0 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n",
        b"HTTP/1.0 200 OK\r\n Invalid: folded\r\n\r\n{}",
        b"HTTP/1.0 200 OK\r\nContent-Length: invalid\r\n\r\n{}",
        b"HTTP/1.0 200 OK\r\n\r\n" + b"x" * 131073,
        b"HTTP/1.0 200 OK\r\nX-Large: " + b"x" * 16384 + b"\r\n\r\n{}",
    ],
)
def test_http_rejection_never_follows_redirect_or_retries(monkeypatch, response):
    _, writer, connect = _socket_transport(monkeypatch, response)
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_output("a" * 64)
    assert connect.await_count == 1
    writer.close.assert_called_once_with()


def test_malformed_id_never_opens_socket(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(target.asyncio, "open_unix_connection", connect)
    with pytest.raises(target.Rejected):
        target.inspect_output("../unowned?path=other")
    connect.assert_not_awaited()


def test_non_socket_path_never_connects(monkeypatch):
    _, _, connect = _socket_transport(monkeypatch, b"")
    target.os.lstat.return_value.st_mode = target.stat.S_IFREG
    with pytest.raises(target.Rejected):
        target.inspect_output("a" * 64)
    connect.assert_not_awaited()


def test_read_timeout_closes_socket_and_redacts(monkeypatch):
    reader, writer, _ = _socket_transport(monkeypatch, b"")
    reader.read.side_effect = TimeoutError("PRIVATE_SOCKET_DETAIL")
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$") as error:
        target.inspect_output("a" * 64)
    assert "PRIVATE" not in str(error.value)
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once()


def test_close_delimited_http10_response(monkeypatch):
    _socket_transport(monkeypatch, b"HTTP/1.0 200 OK\r\n\r\n{}")
    assert target.inspect_output("a" * 64) == "{}"


def test_total_transport_budget_is_bounded(monkeypatch):
    reader, writer, _ = _socket_transport(monkeypatch, b"")
    reader.read.side_effect = [b"x" * 65536, b"x" * 65536, b"x" * 16385]
    with pytest.raises(target.Rejected):
        target.inspect_output("a" * 64)
    assert reader.read.call_args.args == (16385,)
    writer.close.assert_called_once_with()


@pytest.mark.parametrize("phase", ["connect", "read"])
def test_scheduled_deadline_cancels_pending_operation(monkeypatch, phase):
    reader, writer, connect = _socket_transport(monkeypatch, b"")
    original_timeout = target.asyncio.timeout
    budgets = []
    cancelled = []

    def controlled_timeout(seconds):
        budgets.append(seconds)
        return original_timeout(0 if seconds == 10 else seconds)

    async def pending(*args, **kwargs):
        try:
            await target.asyncio.Future()
        finally:
            cancelled.append(phase)

    monkeypatch.setattr(target.asyncio, "timeout", controlled_timeout)
    if phase == "connect":
        connect.side_effect = pending
    else:
        reader.read.side_effect = pending
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_output("a" * 64)
    assert cancelled == [phase]
    assert budgets[0] == 10
    if phase == "read":
        assert budgets == [10, 1]
        writer.close.assert_called_once_with()
        writer.wait_closed.assert_awaited_once()


def test_close_exception_still_attempts_bounded_wait(monkeypatch):
    _, writer, _ = _socket_transport(monkeypatch, b"HTTP/1.0 200 OK\r\n\r\n{}")
    writer.close.side_effect = OSError("PRIVATE_CLOSE")
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_output("a" * 64)
    writer.wait_closed.assert_awaited_once()


def test_duplicate_container_identity_is_rejected(monkeypatch):
    owner = target.Ownership("a" * 64, "123", "1", "valkey-ttl")
    payload = json.dumps(_record(owner))
    payload = '{"Id": "foreign",' + payload[1:]
    monkeypatch.setattr(target, "inspect_output", Mock(return_value=payload))
    with pytest.raises(target.Rejected, match=r"^OWNERSHIP_REJECTED$"):
        target.inspect_owned(owner)


def test_owned_workflow_is_source_bound_and_additive():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (root / ".github/workflows/valkey-ttl-characterization.yml").read_text()
    )
    trigger = workflow.get("on", workflow.get(True))
    assert set(trigger) == {"pull_request"}
    assert trigger["pull_request"]["branches"] == ["egorribun"]
    assert set(trigger["pull_request"]["paths"]) == {
        ".github/workflows/valkey-ttl-characterization.yml",
        "scripts/quality/owned_valkey_ttl_characterization.py",
        "tests/test_owned_valkey_ttl_characterization.py",
        "pyproject.toml",
        "uv.lock",
        "docker-compose.yml",
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"characterize"}
    job = workflow["jobs"]["characterize"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 15
    assert "continue-on-error" not in job
    assert set(job["services"]) == {"valkey"}
    service = job["services"]["valkey"]
    assert service["image"] == target.load_image_pin()
    assert service["ports"] == ["127.0.0.1:6382:6379"]
    for label in [
        "university-ecosystem.valkey-ttl-acceptance=true",
        "university-ecosystem.valkey-ttl-acceptance.run=${{ github.run_id }}",
        "university-ecosystem.valkey-ttl-acceptance.attempt=${{ github.run_attempt }}",
        "university-ecosystem.valkey-ttl-acceptance.job=characterize",
    ]:
        assert "--label " + label in service["options"]
    steps = job["steps"]
    assert steps[-1]["run"] == (
        "uv run --no-sync python scripts/quality/owned_valkey_ttl_characterization.py"
    )
    assert steps[-2]["run"] == "uv sync --frozen"
    assert all("continue-on-error" not in step for step in steps)


def _pin_fixture(tmp_path):
    import json

    pin = target.load_image_pin()
    compose = {
        "services": {
            "valkey": {"image": pin},
            "revocation-valkey": {"image": pin},
        }
    }
    workflow = {"jobs": {"characterize": {"services": {"valkey": {"image": pin}}}}
    path = tmp_path / ".github/workflows"
    path.mkdir(parents=True)
    (tmp_path / "docker-compose.yml").write_text(json.dumps(compose))
    (path / "valkey-ttl-characterization.yml").write_text(json.dumps(workflow))
    return pin, compose, workflow


def test_canonical_pin_positive_and_fixed_repository_anchor(tmp_path):
    from pathlib import Path

    pin, _, _ = _pin_fixture(tmp_path)
    assert target._image_pin(tmp_path) == pin
    assert target.load_image_pin() == target._image_pin(
        Path(target.__file__).resolve().parents[2]
    )


@pytest.mark.parametrize(
    "path",
    ["docker-compose.yml", ".github/workflows/valkey-ttl-characterization.yml"],
)
def test_pin_missing_document_rejected(tmp_path, path):
    _pin_fixture(tmp_path)
    (tmp_path / path).unlink()
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        "cache-missing",
        "cache-type",
        "cache-tag-only",
        "cache-version",
        "revocation-missing",
        "revocation-mismatch",
        "workflow-missing",
        "workflow-mismatch",
        "cache-digest-drift",
    ],
)
def test_pin_shape_or_cross_source_mismatch_rejected(tmp_path, change):
    pin, compose, workflow = _pin_fixture(tmp_path)
    if change == "cache-missing":
        del compose["services"]["valkey"]["image"]
    elif change == "cache-type":
        compose["services"]["valkey"]["image"] = 7
    elif change == "cache-tag-only":
        compose["services"]["valkey"]["image"] = "valkey/valkey:9.1.2-alpine"
    elif change == "cache-version":
        compose["services"]["valkey"]["image"] = pin.replace("9.1.2", "9.1.3")
    elif change == "revocation-missing":
        del compose["services"]["revocation-valkey"]
    elif change == "revocation-mismatch":
        compose["services"]["revocation-valkey"]["image"] = "valkey:latest"
    elif change == "workflow-missing":
        del workflow["jobs"]["characterize"]["services"]["valkey"]
    elif change == "workflow-mismatch":
        workflow["jobs"]["characterize"]["services"]["valkey"]["image"] = (
            "valkey:latest"
        )
    else:
        old = pin[-1]
        compose["services"]["valkey"]["image"] = pin[:-1] + ("1" if old == "0" else "0")
    (tmp_path / "docker-compose.yml").write_text(json.dumps(compose))
    (tmp_path / ".github/workflows/valkey-ttl-characterization.yml").write_text(
        json.dumps(workflow)
    )
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)


@pytest.mark.parametrize(
    "document",
    [
        "services: [",
        "services: null",
        "services: {valkey: {image: first, image: second}}",
        "base: &pin {image: ignored}\nservices: {valkey: *pin}",
        "services: {valkey: {<<: {image: ignored}}}",
    ],
)
def test_pin_malformed_duplicate_alias_or_merge_rejected(tmp_path, document):
    _pin_fixture(tmp_path)
    (tmp_path / "docker-compose.yml").write_text(document)
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)


def test_pin_oversize_and_nonregular_file_rejected(tmp_path):
    _pin_fixture(tmp_path)
    path = tmp_path / "docker-compose.yml"
    path.write_bytes(b"x" * 131073)
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)
    path.unlink()
    path.mkdir()
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)


def test_unspecified_ipv4_fixture_preserves_wildcard_semantics():
    address = IPv4Address(0)
    assert address.is_unspecified
    assert address.version == 4
    assert not address.is_loopback
    assert address.packed == bytes(4)


def test_pin_invalid_utf8_rejected(tmp_path):
    _pin_fixture(tmp_path)
    (tmp_path / "docker-compose.yml").write_bytes(bytes([255]))
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)


def test_pin_symlink_rejected(tmp_path):
    _pin_fixture(tmp_path)
    path = tmp_path / "docker-compose.yml"
    alternate = tmp_path / "alternate.yml"
    path.rename(alternate)
    path.symlink_to(alternate)
    with pytest.raises(target.Rejected, match=r"^IMAGE_PIN_REJECTED$"):
        target._image_pin(tmp_path)
