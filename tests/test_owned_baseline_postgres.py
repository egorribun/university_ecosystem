"""Executable ownership, cleanup and default-DB isolation controls; no Docker."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import psycopg
import pytest
import requests
import sqlalchemy as sa
from docker.errors import NotFound

from tests.fixtures import owned_baseline_postgres as owned

# Scope the same default-DB protections to these database-free contract tests.
initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard

pytest_plugins = ["pytester"]

_ROOT = Path(__file__).resolve().parents[1]
_RECEIPT = _ROOT / "tests/integration/test_aud262_receipt_schema_postgres.py"
_CONTAINER_ID = "c" * 64
_IMAGE_ID = "sha256:" + "d" * 64


class FakeDocker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.data: dict = {}
        self.removed = False
        self.fail_stage: str | None = None
        self.uncertain_absent = False

    def inspect_image(self, image):
        self.calls.append(("image", image))
        if self.fail_stage == "image":
            raise RuntimeError("private driver detail")
        return {
            "Id": _IMAGE_ID,
            "RepoDigests": [f"pgvector/pgvector@{owned._IMAGE_DIGEST}"],
        }

    def create_host_config(self, **kwargs):
        self.calls.append(("host", kwargs))
        return kwargs

    def create_container(self, **kwargs):
        self.calls.append(("create", None))
        if self.fail_stage == "create":
            raise RuntimeError("private driver detail")
        assert kwargs["image"] == _IMAGE_ID
        assert kwargs["use_config_proxy"] is False
        assert kwargs["host_config"] == {
            "port_bindings": {5432: ("127.0.0.1",)},
            "restart_policy": {"Name": "no"},
            "auto_remove": False,
        }
        assert kwargs["ports"] == [5432]
        assert kwargs["command"] == [
            "postgres",
            "-c",
            "lock_timeout=10s",
            "-c",
            "statement_timeout=60s",
            "-c",
            "idle_in_transaction_session_timeout=60s",
        ]
        assert set(kwargs["environment"]) == {
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
        }
        self.data = {
            "Id": _CONTAINER_ID,
            "Image": _IMAGE_ID,
            "Config": {"Image": _IMAGE_ID, "Labels": kwargs["labels"]},
            "HostConfig": {
                "Privileged": False,
                "Binds": None,
                "NetworkMode": "default",
                "PortBindings": {
                    "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]
                },
            },
            "NetworkSettings": {
                "Ports": {
                    "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]
                }
            },
            "State": {"Running": False},
        }
        if self.fail_stage == "null-response":
            return None
        if self.fail_stage == "list-response":
            return []
        if self.fail_stage == "missing-id":
            return {}
        if self.fail_stage == "non-string-id":
            return {"Id": 123}
        return {"Id": "short" if self.fail_stage == "id" else _CONTAINER_ID}

    def inspect_container(self, container_id):
        self.calls.append(("inspect", container_id))
        assert container_id == _CONTAINER_ID
        if self.removed:
            raise NotFound("absent")
        if self.fail_stage == "inspect":
            raise RuntimeError("private driver detail")
        return copy.deepcopy(self.data)

    def start(self, container_id):
        self.calls.append(("start", container_id))
        assert container_id == _CONTAINER_ID
        self.data["State"]["Running"] = True
        if self.fail_stage == "start":
            raise RuntimeError("private driver detail")

    def remove_container(self, container_id, **kwargs):
        self.calls.append(("remove", container_id))
        assert container_id == _CONTAINER_ID
        assert kwargs == {"force": True, "v": True}
        if self.fail_stage == "remove":
            self.removed = self.uncertain_absent
            raise RuntimeError("private driver detail")
        self.removed = self.fail_stage != "still-present"

    def close(self):
        self.calls.append(("close", None))
        if self.fail_stage == "close":
            raise RuntimeError("private driver detail")


def _fake_lifecycle(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    client = FakeDocker()
    monkeypatch.setattr(owned, "_new_docker_client", lambda: client)
    monkeypatch.setattr(owned, "_wait_ready", lambda _url: None)
    return client


def test_local_client_ignores_operator_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS_VERIFY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NETRC",
    ):
        monkeypatch.setenv(key, "untrusted-operator-value")
    factory = Mock()
    factory.return_value._general_configs = {}
    monkeypatch.setattr(owned.docker, "APIClient", factory)
    assert owned._new_docker_client() is factory.return_value
    factory.assert_called_once_with(
        base_url="unix:///var/run/docker.sock",
        version=owned.DEFAULT_DOCKER_API_VERSION,
        timeout=15,
    )
    assert factory.return_value.trust_env is False
    assert factory.return_value.max_redirects == 0


@pytest.mark.parametrize("version", ["0.0.0", "7.2.1"])
def test_unsupported_sdk_version_never_constructs_a_client(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    factory = Mock()
    monkeypatch.setattr(owned.docker, "__version__", version)
    monkeypatch.setattr(owned.docker, "APIClient", factory)
    with pytest.raises(owned.OwnedPostgresError, match="version unsupported"):
        owned._new_docker_client()
    factory.assert_not_called()


def test_unsupported_api_version_never_constructs_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock()
    monkeypatch.setattr(owned, "DEFAULT_DOCKER_API_VERSION", "unsupported")
    monkeypatch.setattr(owned.docker, "APIClient", factory)
    with pytest.raises(owned.OwnedPostgresError, match="version unsupported"):
        owned._new_docker_client()
    factory.assert_not_called()


@pytest.mark.parametrize("configuration", [None, [], "unsupported"])
@pytest.mark.parametrize("close_fails", [False, True])
def test_unsupported_client_config_is_closed_before_any_request(
    monkeypatch: pytest.MonkeyPatch, configuration: object, close_fails: bool
) -> None:
    client = Mock()
    client._general_configs = configuration
    if close_fails:
        client.close.side_effect = RuntimeError("private driver detail")
    monkeypatch.setattr(owned.docker, "APIClient", lambda **_kwargs: client)
    with pytest.raises(
        owned.OwnedPostgresError, match="configuration unsupported"
    ) as error:
        owned._new_docker_client()
    assert "private driver detail" not in str(error.value)
    assert ("client close failed" in str(error.value)) is close_fails
    client.close.assert_called_once_with()
    assert client.method_calls == [("close", (), {})]


def test_real_sdk_session_disables_netrc_proxies_retries_and_redirect_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from docker.api import client as docker_client

    configuration = {
        "HttpHeaders": {
            "Authorization": f"Probe {uuid4()}",
            "X-Operator-Config-Probe": uuid4().hex,
        }
    }
    monkeypatch.setattr(
        docker_client.config, "load_general_config", lambda: configuration
    )
    monkeypatch.setattr(docker_client.auth, "load_config", lambda **_kwargs: {})
    forbidden = Mock(side_effect=AssertionError("ambient auth/proxy lookup"))
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", forbidden)
    monkeypatch.setattr(requests.sessions, "get_environ_proxies", forbidden)
    client = owned._new_docker_client()
    try:
        assert "HttpHeaders" in configuration
        assert client._general_configs is not configuration
        adapter = client.get_adapter(client.base_url)
        assert adapter.max_retries.total == 0
        assert adapter.max_retries.read is False
        calls: list[str] = []

        def redirect(request, **kwargs):
            assert kwargs["timeout"] == 15
            assert "Authorization" not in request.headers
            assert "X-Operator-Config-Probe" not in request.headers
            calls.append(request.method)
            response = requests.Response()
            response.status_code = 307
            response.url = request.url
            response.request = request
            response.headers["Location"] = client.base_url + "/not-authorized"
            response._content = b""
            return response

        # Exercise the real Requests/SDK session, but replace the transport
        # before any send. No Unix socket, daemon, registry or database is used.
        monkeypatch.setattr(adapter, "send", redirect)
        with pytest.raises(requests.TooManyRedirects):
            client._post(client.base_url + "/owned-isolation-probe", json={})
        assert calls == ["POST"]
        forbidden.assert_not_called()
    finally:
        client.close()


def test_owned_server_requires_acknowledged_identity_and_exact_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_lifecycle(monkeypatch)
    with owned.owned_postgres_server() as server:
        assert server.container_id == _CONTAINER_ID
        assert server.url.host == "127.0.0.1"
        assert server.url.port == 15432
        assert server.url.database == "postgres"
        assert server.url.query["options"] == (
            "-c lock_timeout=10s -c statement_timeout=60s "
            "-c idle_in_transaction_session_timeout=60s"
        )
        assert server.url.password not in repr(server)
        assert [name for name, _ in client.calls] == [
            "image",
            "host",
            "create",
            "inspect",
            "start",
            "inspect",
        ]
    assert [name for name, _ in client.calls][-4:] == [
        "inspect",
        "remove",
        "inspect",
        "close",
    ]
    assert client.removed is True


def test_closed_lease_cannot_create_a_database_or_repeat_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_lifecycle(monkeypatch)
    scratch = Mock(side_effect=AssertionError("scratch must not be entered"))
    monkeypatch.setattr(owned, "_owned_scratch_database", scratch)
    with owned.owned_postgres_server() as server:
        server._lease.close()
        server._lease.close()
        with pytest.raises(owned.OwnedPostgresError, match="not active"):
            with owned.committed_baseline(server):
                pytest.fail("closed lease admitted")
    assert client.calls.count(("remove", _CONTAINER_ID)) == 1
    assert client.calls.count(("close", None)) == 1
    scratch.assert_not_called()


@pytest.mark.parametrize(
    "stage",
    [
        "image",
        "create",
        "id",
        "null-response",
        "list-response",
        "missing-id",
        "non-string-id",
    ],
)
def test_unacknowledged_creation_never_guesses_cleanup_or_retries(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    client = _fake_lifecycle(monkeypatch)
    client.fail_stage = stage
    with pytest.raises(owned.OwnedPostgresError) as failed:
        with owned.owned_postgres_server():
            pytest.fail("unverified server admitted")
    assert "private driver detail" not in str(failed.value)
    assert not any(name in {"start", "remove"} for name, _ in client.calls)
    assert sum(name == "create" for name, _ in client.calls) <= 1
    assert client.calls[-1] == ("close", None)


@pytest.mark.parametrize("stage", ["start", "readiness"])
def test_failure_after_acknowledgement_removes_only_verified_owned_container(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    client = _fake_lifecycle(monkeypatch)
    if stage == "start":
        client.fail_stage = stage
    else:

        def fail_readiness(_url):
            raise owned.OwnedPostgresError("readiness test failure")

        monkeypatch.setattr(owned, "_wait_ready", fail_readiness)
    with pytest.raises(owned.OwnedPostgresError):
        with owned.owned_postgres_server():
            pytest.fail("unready server admitted")
    assert client.calls.count(("remove", _CONTAINER_ID)) == 1
    assert client.calls[-1] == ("close", None)


@pytest.mark.parametrize(
    "path, value",
    [
        (("Id",), "e" * 64),
        (("Image",), "sha256:" + "e" * 64),
        (("Config", "Image"), "other-image"),
        (("Config", "Labels"), {}),
        (("HostConfig", "Privileged"), True),
        (("HostConfig", "Binds"), ["/operator:/data"]),
        (("HostConfig", "NetworkMode"), "host"),
        (("HostConfig", "PortBindings"), {}),
    ],
)
def test_identity_drift_refuses_removal(
    monkeypatch: pytest.MonkeyPatch, path: tuple[str, ...], value: object
) -> None:
    client = _fake_lifecycle(monkeypatch)
    with pytest.raises(owned.OwnedPostgresError, match="identity unverified"):
        with owned.owned_postgres_server():
            target = client.data
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
    assert not any(name == "remove" for name, _ in client.calls)
    assert client.calls[-1] == ("close", None)


@pytest.mark.parametrize("absent", [False, True])
def test_uncertain_remove_is_read_back_once_but_never_retried(
    monkeypatch: pytest.MonkeyPatch, absent: bool
) -> None:
    client = _fake_lifecycle(monkeypatch)
    with pytest.raises(owned.OwnedPostgresError, match="response uncertain") as failed:
        with owned.owned_postgres_server():
            client.fail_stage = "remove"
            client.uncertain_absent = absent
    expected = "absence confirmed" if absent else "container still present"
    assert expected in str(failed.value)
    assert "private driver detail" not in str(failed.value)
    assert client.calls.count(("remove", _CONTAINER_ID)) == 1
    assert [name for name, _ in client.calls][-3:] == ["remove", "inspect", "close"]


@pytest.mark.parametrize("stage", ["inspect", "still-present", "close"])
def test_cleanup_failures_are_opaque_and_close_is_attempted(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    client = _fake_lifecycle(monkeypatch)
    with pytest.raises(owned.OwnedPostgresError) as failed:
        with owned.owned_postgres_server():
            client.fail_stage = stage
    assert "private driver detail" not in str(failed.value)
    assert client.calls[-1] == ("close", None)


def test_cleanup_failure_does_not_replace_original_test_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_lifecycle(monkeypatch)
    with pytest.raises(ValueError, match="original assertion") as failed:
        with owned.owned_postgres_server():
            client.fail_stage = "remove"
            raise ValueError("original assertion")
    assert failed.value.__notes__ == [
        "Owned PostgreSQL server cleanup failed: "
        "Owned PostgreSQL removal response uncertain; container still present"
    ]
    assert client.calls.count(("remove", _CONTAINER_ID)) == 1
    assert client.calls[-1] == ("close", None)


@pytest.mark.parametrize("invalid", ["image-id", "digest"])
def test_unverified_image_never_creates_a_container(
    monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    client = _fake_lifecycle(monkeypatch)
    image = {
        "Id": _IMAGE_ID,
        "RepoDigests": [f"pgvector/pgvector@{owned._IMAGE_DIGEST}"],
    }
    image["Id" if invalid == "image-id" else "RepoDigests"] = "wrong"
    monkeypatch.setattr(client, "inspect_image", lambda _image: image)
    with pytest.raises(owned.OwnedPostgresError, match="pinned image"):
        with owned.owned_postgres_server():
            pytest.fail("unverified image admitted")
    assert client.calls == [("close", None)]


@pytest.mark.parametrize("invalid", ["address", "port", "extra", "stopped"])
def test_unverified_runtime_binding_fails_before_database_admission(
    monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    client = _fake_lifecycle(monkeypatch)
    original_start = client.start

    def start(container_id):
        original_start(container_id)
        ports = client.data["NetworkSettings"]["Ports"]
        if invalid == "address":
            ports["5432/tcp"][0]["HostIp"] = "192.0.2.1"
        elif invalid == "port":
            ports["5432/tcp"][0]["HostPort"] = "65536"
        elif invalid == "extra":
            ports["1234/tcp"] = []
        else:
            client.data["State"]["Running"] = False

    monkeypatch.setattr(client, "start", start)
    with pytest.raises(owned.OwnedPostgresError, match="loopback binding"):
        with owned.owned_postgres_server():
            pytest.fail("unverified binding admitted")
    assert client.calls.count(("remove", _CONTAINER_ID)) == 1
    assert client.calls[-1] == ("close", None)


@pytest.mark.parametrize("invalid", ["url", "identity", "nonce", "binding"])
def test_scratch_admission_rechecks_active_lease_not_operator_url(
    monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    client = _fake_lifecycle(monkeypatch)
    scratch = Mock(side_effect=AssertionError("scratch must not be entered"))
    monkeypatch.setattr(owned, "_owned_scratch_database", scratch)
    with owned.owned_postgres_server() as server:
        if invalid == "url":
            server = replace(server, url=server.url.set(host="192.0.2.1"))
        elif invalid == "identity":
            server = replace(server, container_id="e" * 64)
        elif invalid == "nonce":
            server = replace(server, owner_nonce="not-acknowledged")
        else:
            client.data["NetworkSettings"]["Ports"]["5432/tcp"][0][
                "HostPort"
            ] = "15433"
        with pytest.raises(owned.OwnedPostgresError):
            with owned.committed_baseline(server):
                pytest.fail("unowned scratch database admitted")
    scratch.assert_not_called()


def test_baseline_is_actually_called_and_committed_before_yield_then_disposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_lifecycle(monkeypatch)
    events: list[str] = []
    connection = Mock()
    connection.scalar.side_effect = ["10s", "1min"]
    migration = Mock()
    migration.upgrade.side_effect = lambda: events.append("upgrade")

    @contextmanager
    def scratch(url):
        assert sa.engine.make_url(url).host == "127.0.0.1"
        events.append("scratch")
        yield (
            sa.engine.make_url(url)
            .set(database="acknowledged_test_database")
            .render_as_string(hide_password=False)
        )
        events.append("drop")

    @contextmanager
    def begin():
        events.append("begin")
        yield connection
        events.append("commit")

    @contextmanager
    def operations(_context):
        events.append("operations")
        yield

    engine = Mock()
    engine.begin = begin
    engine.dispose.side_effect = lambda: events.append("dispose")
    monkeypatch.setattr(owned, "_owned_scratch_database", scratch)
    monkeypatch.setattr(owned, "load_baseline", lambda: migration)
    monkeypatch.setattr(owned.sa, "create_engine", lambda *_a, **_k: engine)
    monkeypatch.setattr(owned.MigrationContext, "configure", lambda _c: object())
    monkeypatch.setattr(owned.Operations, "context", operations)
    with owned.owned_postgres_server() as server:
        with owned.committed_baseline(server) as baseline:
            assert baseline.migration is migration
            assert baseline.transaction_timeouts == ("10s", "1min")
            assert baseline.url.database == "acknowledged_test_database"
            events.append("yield")
    assert events == [
        "scratch",
        "begin",
        "operations",
        "upgrade",
        "commit",
        "yield",
        "dispose",
        "drop",
    ]
    migration.upgrade.assert_called_once_with()
    assert client.calls.count(("remove", _CONTAINER_ID)) == 1


def test_readiness_checks_database_identity_and_version_without_operator_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.execute.return_value.fetchone.return_value = (
        "postgres",
        "baseline_admin",
        170006,
    )
    connect = Mock(return_value=connection)
    monkeypatch.setattr(owned.psycopg, "connect", connect)
    url = sa.URL.create(
        "postgresql+psycopg",
        username="baseline_admin",
        password=uuid4().hex,
        host="127.0.0.1",
        port=15432,
        database="postgres",
    )
    owned._wait_ready(url)
    connect.assert_called_once_with(
        host="127.0.0.1",
        port=15432,
        user="baseline_admin",
        password=url.password,
        dbname="postgres",
        connect_timeout=5,
        options="-c statement_timeout=5s",
        autocommit=True,
    )
    connection.execute.assert_called_once_with(
        "SELECT current_database(), current_user, "
        "current_setting('server_version_num')::integer"
    )


@pytest.mark.parametrize(
    "row, reason",
    [
        (None, "identity mismatch"),
        (("other", "baseline_admin", 170006), "identity mismatch"),
        (("postgres", "other", 170006), "identity mismatch"),
        (("postgres", "baseline_admin", 160006), "version 17"),
        (("postgres", "baseline_admin", 180001), "version 17"),
    ],
)
def test_readiness_rejects_wrong_identity_or_major_version(
    monkeypatch: pytest.MonkeyPatch, row: object, reason: str
) -> None:
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.execute.return_value.fetchone.return_value = row
    connect = Mock(return_value=connection)
    monkeypatch.setattr(owned.psycopg, "connect", connect)
    url = sa.URL.create(
        "postgresql+psycopg",
        host="127.0.0.1",
        port=15432,
        username="baseline_admin",
        database="postgres",
    )
    with pytest.raises(owned.OwnedPostgresError, match=reason):
        owned._wait_ready(url)
    assert connect.call_count == 1


def test_readiness_query_failure_does_not_echo_driver_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = Mock(side_effect=psycopg.ProgrammingError("private driver detail"))
    monkeypatch.setattr(owned.psycopg, "connect", connect)
    url = sa.URL.create(
        "postgresql+psycopg",
        host="127.0.0.1",
        port=15432,
        username="baseline_admin",
        database="postgres",
    )
    with pytest.raises(owned.OwnedPostgresError, match="query failed") as failed:
        owned._wait_ready(url)
    assert "private driver detail" not in str(failed.value)
    assert connect.call_count == 1


def test_readiness_retry_budget_is_not_an_unbounded_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((0, 0, 91))
    monkeypatch.setattr(owned.time, "monotonic", lambda: next(ticks))
    sleep = Mock()
    monkeypatch.setattr(owned.time, "sleep", sleep)
    connect = Mock(side_effect=psycopg.OperationalError("private driver detail"))
    monkeypatch.setattr(owned.psycopg, "connect", connect)
    url = sa.URL.create(
        "postgresql+psycopg",
        host="127.0.0.1",
        port=15432,
        username="baseline_admin",
        database="postgres",
    )
    with pytest.raises(owned.OwnedPostgresError, match="deadline exceeded") as failed:
        owned._wait_ready(url)
    assert "private driver detail" not in str(failed.value)
    assert connect.call_count == 1
    sleep.assert_called_once_with(0.25)


@pytest.mark.parametrize("target", ["init", "reset", "proxy"])
def test_default_database_guard_executes_fail_fast_sentinels(target: str) -> None:
    from app.core import database
    from tests.fixtures.database import database as fixtures

    with pytest.raises(AssertionError, match="blocked default database"):
        with owned.forbid_default_database():
            if target == "init":
                database.init_database()
            elif target == "reset":
                fixtures._require_safe_database_reset("not-an-authority")
            else:
                database.engine._get_current_object()


def test_default_engine_connection_sentinel_precedes_real_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import database

    engine = sa.create_engine("sqlite://", poolclass=sa.pool.NullPool)
    previous = database._engine
    try:
        monkeypatch.setattr(database, "_engine", Mock(sync_engine=engine))
        with pytest.raises(
            AssertionError, match="blocked default database: connection"
        ):
            with owned.forbid_default_database():
                engine.connect()
    finally:
        monkeypatch.setattr(database, "_engine", previous)
        engine.dispose()


@pytest.mark.asyncio
async def test_default_database_cleanup_sentinel_is_executable() -> None:
    from tests.fixtures.database import database as fixtures

    with pytest.raises(AssertionError, match="blocked default database: cleanup"):
        with owned.forbid_default_database():
            await fixtures._clear_mapped_database_rows(is_postgresql=True)


_EARLY_GUARD_PLUGIN = r"""
import json
import os
import sys
import docker
import pytest
import sqlalchemy as sa

events = []
original_profile = sys.getprofile()

def deny_connection(*args, **kwargs):
    events.append("connection")
    raise AssertionError("early default database connection sentinel")

def deny_container(*args, **kwargs):
    events.append("container")
    raise AssertionError("isolation probe must not start Docker")

sa.Engine.connect = deny_connection
docker.APIClient = deny_container

def profile(frame, event, arg):
    if event != "call":
        return
    name = frame.f_code.co_name
    if name not in {
        "init_database", "_require_safe_database_reset",
        "_clear_mapped_database_rows", "clean_database"
    }:
        return
    path = frame.f_code.co_filename.replace("\\", "/")
    if (
        path.endswith("/tests/fixtures/database/database.py")
        and name == "clean_database"
    ):
        if name not in events:
            events.append(name)
        return
    if (
        (path.endswith("/app/core/database.py") and name == "init_database")
        or (
            path.endswith("/tests/fixtures/database/database.py")
            and name in {"_require_safe_database_reset", "_clear_mapped_database_rows"}
        )
    ):
        events.append(name)
        raise AssertionError("early default database sentinel: " + name)

sys.setprofile(profile)

def pytest_collectstart(collector):
    if (
        isinstance(collector, pytest.Module)
        and collector.path.name == "test_aud262_receipt_schema_postgres.py"
    ):
        missing = os.environ["OWNED_FIXTURE_REMOVE"]
        if missing:
            delattr(collector.obj, missing)

def pytest_collection_modifyitems(items):
    assert len(items) == 1
    assert items[0].nodeid.endswith(
        "tests/integration/test_aud262_receipt_schema_postgres.py"
        "::test_receipt_owned_fixture_never_uses_default_database"
    )

def pytest_runtest_call(item):
    from app.core.config import settings
    from app.core.config.base import _ENV_FILE

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.database_read_replica_url is None
    assert _ENV_FILE is None

def pytest_sessionfinish(session, exitstatus):
    sys.setprofile(original_profile)
    print("\nOWNED_ISOLATION_EVENTS=" + json.dumps(events))
"""


@pytest.mark.parametrize(
    "missing, expected, hostile_aliases",
    [
        ("", None, False),
        ("", None, True),
        ("initialize_database_for_tests", "init_database", False),
        ("prepare_database", "_require_safe_database_reset", False),
        ("clean_database", "blocked default database: lazy access", False),
    ],
)
def test_receipt_real_autouse_graph_isolated_before_conftest_import(
    pytester: pytest.Pytester,
    missing: str,
    expected: str | None,
    hostile_aliases: bool,
) -> None:
    pytester.makepyfile(owned_early_guard=_EARLY_GUARD_PLUGIN)
    # Pytester's supported launcher copies os.environ. Limit our overrides to
    # this synchronous child invocation and restore them before checking results.
    parent_fingerprint = hashlib.sha256(
        json.dumps(dict(os.environ), sort_keys=True).encode()
    ).digest()
    try:
        with pytest.MonkeyPatch.context() as child_environment:
            if hostile_aliases:
                for key, value in {
                    "PYTEST_ADDOPTS": "--collect-only",
                    "PYTEST_PLUGINS": "unowned_probe_plugin_must_not_load",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    "PYTEST_CURRENT_TEST": "unrelated-parent-case (call)",
                    "PYTEST_XDIST_WORKER": "gw_unowned",
                    "PYTEST_XDIST_WORKER_COUNT": "99",
                    "PYTEST_XDIST_TESTRUNUID": "unrelated-parent-run",
                    "PYTEST_XDIST_AUTO_NUM_WORKERS": "99",
                    "PYTEST_SHARD_MANIFEST": str(
                        pytester.path / "parent-manifest.json"
                    ),
                    "UNIVERSITY_ECOSYSTEM_DB_PERF_CAPTURE_REQUIRED": "1",
                }.items():
                    child_environment.setenv(key, value)
                for key in ("database_url", "DaTaBaSe_ReAd_RePlIcA_Url"):
                    child_environment.setenv(key, "not-a-database-url")
                for key in (
                    "DATABASE_URL_FILE",
                    "DaTaBaSe_Url_FiLe",
                    "DaTaBaSe_ReAd_RePlIcA_Url_FiLe",
                    "eNv_FiLe_PaTh",
                    "EnV_ExAmPlE_PaTh",
                ):
                    child_environment.setenv(
                        key, str(pytester.path / "absent-operator-input")
                    )

            # Plain DB inputs are case-insensitive. Isolate aliases only in
            # this child; production's exact-case FILE policy is unchanged.
            controlled = {
                "database_url",
                "database_url_file",
                "database_read_replica_url",
                "database_read_replica_url_file",
                "env_file_path",
                "env_example_path",
                "pytest_addopts",
                "pytest_plugins",
                "pytest_disable_plugin_autoload",
                "pytest_current_test",
                "pytest_xdist_worker",
                "pytest_xdist_worker_count",
                "pytest_xdist_testrunuid",
                "pytest_xdist_auto_num_workers",
                "pytest_shard_manifest",
                "university_ecosystem_db_perf_capture_required",
                "university_ecosystem_pytest_allow_testcontainers_fallback",
                "university_ecosystem_pytest_auto_database_url",
                "university_ecosystem_pytest_auto_database_dir",
                "university_ecosystem_pytest_database_mode",
                "university_ecosystem_pytest_external_database_url",
            }
            for key in tuple(os.environ):
                if key.casefold() in controlled:
                    child_environment.delenv(key)

            child_environment.setenv(
                "PYTHONPATH", os.pathsep.join((str(pytester.path), str(_ROOT)))
            )
            child_environment.setenv("RUN_INTEGRATION_TESTS", "1")
            child_environment.setenv("USE_TESTCONTAINERS_POSTGRES", "0")
            child_environment.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
            child_environment.setenv("ENV_FILE_PATH", "")
            child_environment.setenv("OWNED_FIXTURE_REMOVE", missing)
            child_environment.setenv("PYTEST_ADDOPTS", "")
            pytester.plugins.append("owned_early_guard")
            # Pytester's timeout bounds the wait, then kills the subprocess.
            # Its reap wait is unbounded; the host job remains outermost.
            result = pytester.runpytest_subprocess(
                f"{_RECEIPT}::test_receipt_owned_fixture_never_uses_default_database",
                "-c",
                str(_ROOT / "pyproject.toml"),
                "--rootdir",
                str(_ROOT),
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
                "-q",
                "-s",
                timeout=60,
            )
    finally:
        current_fingerprint = hashlib.sha256(
            json.dumps(dict(os.environ), sort_keys=True).encode()
        ).digest()
        restored = current_fingerprint == parent_fingerprint
        assert restored, "Child isolation changed the parent environment"
    output = result.stdout.str()
    lines = [
        line
        for line in output.splitlines()
        if line.startswith("OWNED_ISOLATION_EVENTS=")
    ]
    assert len(lines) == 1
    events = json.loads(lines[0].split("=", 1)[1])
    assert "connection" not in events
    assert "container" not in events
    assert result.parseoutcomes().get("skipped", 0) == 0
    if expected is None:
        assert result.ret == pytest.ExitCode.OK
        result.assert_outcomes(passed=1)
        assert events == []
    else:
        assert result.ret == pytest.ExitCode.TESTS_FAILED
        assert result.parseoutcomes().get("errors", 0) >= 1
        assert expected in output
        assert events == (
            ["clean_database"] if missing == "clean_database" else [expected]
        )
