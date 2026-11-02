"""Committed baselines on acknowledged, disposable local PostgreSQL servers.

Only explicitly importing test modules override the three default-DB fixtures.
The fixed Unix daemon is trusted and quiescent; names and operator URLs are not
ownership evidence. The image must already be present: this helper never pulls.

Docker's 15-second socket/request timeout is not an aggregate wall deadline.
Readiness retry scheduling stops after 90 seconds; an in-flight call can extend
that interval. Connect timeout is 5 seconds; SQL lock/statement/idle-transaction
limits are 10/60/60 seconds on the server, not a client network wall deadline.
The importing live module also has a pytest signal watchdog; the hosted job
remains the outer limit. Process death or an unacknowledged CREATE cannot prove
resource cleanup.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import docker
import psycopg
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from docker.constants import DEFAULT_DOCKER_API_VERSION
from docker.errors import NotFound
from sqlalchemy.engine import make_url

from scripts.quality.render_live_alembic_sql import _owned_scratch_database

_POSTGRES_IMAGE = (
    "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
)
_IMAGE_DIGEST = _POSTGRES_IMAGE.split("@", 1)[1]
_OWNER_LABEL = "university-ecosystem.owned-baseline-test"
_DOCKER_SOCKET = "unix:///var/run/docker.sock"
_REQUEST_TIMEOUT = 15
_READINESS_SECONDS = 90
_SQL_OPTIONS = (
    "-c lock_timeout=10s -c statement_timeout=60s "
    "-c idle_in_transaction_session_timeout=60s"
)
_BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "202611020000_mvp_baseline.py"
)


class OwnedPostgresError(RuntimeError):
    """Opaque lifecycle diagnostic; never include API bodies or credentials."""


def _docker_call[T](operation: Callable[[], T], stage: str) -> T:
    try:
        return operation()
    except Exception:
        raise OwnedPostgresError(f"Owned PostgreSQL {stage} failed") from None


def _new_docker_client() -> docker.APIClient:
    if docker.__version__ != "7.2.0" or DEFAULT_DOCKER_API_VERSION != "1.45":
        raise OwnedPostgresError("Owned PostgreSQL Docker SDK version unsupported")
    # The constructor may read Docker config/auth data. This fixed API version
    # avoids discovery requests; no registry or credential-helper call is used.
    client = _docker_call(
        lambda: docker.APIClient(
            base_url=_DOCKER_SOCKET,
            version=DEFAULT_DOCKER_API_VERSION,
            timeout=_REQUEST_TIMEOUT,
        ),
        "local Docker client creation",
    )
    # Requests otherwise trusts ambient proxy/netrc settings. Constructor-time
    # discovery is disabled above, so isolation precedes the first request.
    client.trust_env = False
    client.max_redirects = 0
    configuration = getattr(client, "_general_configs", None)
    if type(configuration) is not dict:
        try:
            client.close()
        except Exception:
            raise OwnedPostgresError(
                "Owned PostgreSQL Docker configuration unsupported; client close failed"
            ) from None
        raise OwnedPostgresError("Owned PostgreSQL Docker configuration unsupported")
    # Pinned docker 7.2.0's update_headers decorator reads this private mapping
    # independently of Requests.trust_env. This filter copies its input instead
    # of mutating it. SDK construction may already normalize the freshly loaded
    # per-client mapping; no config file or process environment is modified.
    client._general_configs = {
        key: value
        for key, value in configuration.items()
        if key != "HttpHeaders"
    }
    return client


@dataclass(frozen=True)
class OwnedPostgres:
    url: sa.URL = field(repr=False)
    container_id: str
    owner_nonce: str
    _lease: _ContainerLease = field(repr=False)


class _ContainerLease:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.nonce = uuid4().hex
        self.container_id: str | None = None
        self.image_id: str | None = None
        self.url: sa.URL | None = None
        self.closed = False

    def _identity(self) -> dict[str, Any]:
        data = self.client.inspect_container(self.container_id)
        config = data.get("Config", {})
        host = data.get("HostConfig", {})
        bindings = host.get("PortBindings", {})
        if (
            data.get("Id") != self.container_id
            or data.get("Image") != self.image_id
            or config.get("Image") != self.image_id
            or config.get("Labels", {}).get(_OWNER_LABEL) != self.nonce
            or host.get("Privileged") is not False
            or host.get("Binds") not in (None, [])
            or host.get("NetworkMode") not in ("default", "bridge")
            or set(bindings) != {"5432/tcp"}
            or len(bindings["5432/tcp"]) != 1
            or bindings["5432/tcp"][0].get("HostIp") != "127.0.0.1"
        ):
            raise OwnedPostgresError("Owned PostgreSQL container identity changed")
        return data

    def start(self) -> OwnedPostgres:
        image = _docker_call(
            lambda: self.client.inspect_image(_POSTGRES_IMAGE),
            "pre-pulled image inspection",
        )
        image_id = image.get("Id")
        if (
            not isinstance(image_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
            or not any(
                value == f"pgvector/pgvector@{_IMAGE_DIGEST}"
                for value in image.get("RepoDigests", [])
            )
        ):
            raise OwnedPostgresError("Owned PostgreSQL pinned image is unverified")
        self.image_id = image_id
        credential = uuid4().hex + uuid4().hex
        host = self.client.create_host_config(
            port_bindings={5432: ("127.0.0.1",)},
            restart_policy={"Name": "no"},
            auto_remove=False,
        )
        response = _docker_call(
            lambda: self.client.create_container(
                image=image_id,
                command=[
                    "postgres",
                    "-c",
                    "lock_timeout=10s",
                    "-c",
                    "statement_timeout=60s",
                    "-c",
                    "idle_in_transaction_session_timeout=60s",
                ],
                detach=True,
                ports=[5432],
                environment={
                    "POSTGRES_USER": "baseline_admin",
                    "POSTGRES_PASSWORD": credential,
                    "POSTGRES_DB": "postgres",
                },
                labels={_OWNER_LABEL: self.nonce},
                host_config=host,
                use_config_proxy=False,
            ),
            "container creation (outcome may be unknown)",
        )
        container_id = response.get("Id") if isinstance(response, dict) else None
        if (
            not isinstance(container_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", container_id) is None
        ):
            # No guessed name, list/filter search or unverified-ID cleanup.
            raise OwnedPostgresError("Owned PostgreSQL CREATE identity unacknowledged")
        self.container_id = container_id
        _docker_call(self._identity, "pre-start identity inspection")
        _docker_call(
            lambda: self.client.start(container_id),
            "container start",
        )
        data = _docker_call(self._identity, "running identity inspection")
        ports = data.get("NetworkSettings", {}).get("Ports", {})
        bindings = ports.get("5432/tcp")
        if (
            data.get("State", {}).get("Running") is not True
            or set(ports) != {"5432/tcp"}
            or not isinstance(bindings, list)
            or len(bindings) != 1
            or bindings[0].get("HostIp") != "127.0.0.1"
            or re.fullmatch(r"[0-9]{1,5}", bindings[0].get("HostPort", "")) is None
            or not 1 <= int(bindings[0]["HostPort"]) <= 65535
        ):
            raise OwnedPostgresError("Owned PostgreSQL loopback binding unverified")
        url = sa.URL.create(
            "postgresql+psycopg",
            username="baseline_admin",
            password=credential,
            host="127.0.0.1",
            port=int(bindings[0]["HostPort"]),
            database="postgres",
            query={"options": _SQL_OPTIONS},
        )
        _wait_ready(url)
        self.url = url
        return OwnedPostgres(url, container_id, self.nonce, self)

    def verify(self, server: OwnedPostgres) -> None:
        if (
            self.closed
            or server._lease is not self
            or server.url is not self.url
            or server.container_id != self.container_id
            or server.owner_nonce != self.nonce
        ):
            raise OwnedPostgresError("Owned PostgreSQL lease is not active")
        data = _docker_call(self._identity, "database-admission identity inspection")
        if (
            data.get("State", {}).get("Running") is not True
            or data.get("NetworkSettings", {}).get("Ports") != {
                "5432/tcp": [
                    {"HostIp": "127.0.0.1", "HostPort": str(server.url.port)}
                ]
            }
        ):
            raise OwnedPostgresError("Owned PostgreSQL active binding changed")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.container_id is not None:
                try:
                    self._identity()
                except NotFound:
                    return
                except Exception:
                    raise OwnedPostgresError(
                        "Owned PostgreSQL cleanup identity unverified; not removed"
                    ) from None
                try:
                    self.client.remove_container(self.container_id, force=True, v=True)
                except Exception:
                    # Never retry an uncertain destructive request. An exact-ID
                    # read may establish absence, but does not erase the error.
                    try:
                        self.client.inspect_container(self.container_id)
                    except NotFound:
                        outcome = "absence confirmed"
                    except Exception:
                        outcome = "outcome unknown"
                    else:
                        outcome = "container still present"
                    raise OwnedPostgresError(
                        f"Owned PostgreSQL removal response uncertain; {outcome}"
                    ) from None
                try:
                    self.client.inspect_container(self.container_id)
                except NotFound:
                    pass
                except Exception:
                    raise OwnedPostgresError(
                        "Owned PostgreSQL removal verification failed"
                    ) from None
                else:
                    raise OwnedPostgresError(
                        "Owned PostgreSQL container remains after removal"
                    )
        finally:
            pending = sys.exception()
            try:
                self.client.close()
            except Exception:
                if pending is None:
                    raise OwnedPostgresError(
                        "Owned PostgreSQL Docker client close failed"
                    ) from None
                pending.add_note("Owned PostgreSQL Docker client close failed")


def _wait_ready(url: sa.URL) -> None:
    deadline = time.monotonic() + _READINESS_SECONDS
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(
                host=url.host,
                port=url.port,
                user=url.username,
                password=url.password,
                dbname=url.database,
                connect_timeout=5,
                options="-c statement_timeout=5s",
                autocommit=True,
            ) as connection:
                row = connection.execute(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num')::integer"
                ).fetchone()
                if row is None or row[:2] != ("postgres", "baseline_admin"):
                    raise OwnedPostgresError(
                        "Owned PostgreSQL ready-server identity mismatch"
                    )
                if not 170000 <= row[2] < 180000:
                    raise OwnedPostgresError("Owned PostgreSQL requires version 17")
                return
        except psycopg.OperationalError:
            time.sleep(0.25)
        except psycopg.Error:
            raise OwnedPostgresError(
                "Owned PostgreSQL readiness query failed"
            ) from None
    raise OwnedPostgresError("Owned PostgreSQL readiness deadline exceeded")


@contextmanager
def owned_postgres_server() -> Iterator[OwnedPostgres]:
    lease = _ContainerLease(_new_docker_client())
    try:
        yield lease.start()
    finally:
        pending = sys.exception()
        try:
            lease.close()
        except OwnedPostgresError as error:
            if pending is None:
                raise
            # close() emits only our bounded diagnostics, never a driver body.
            pending.add_note(f"Owned PostgreSQL server cleanup failed: {error}")
            for note in getattr(error, "__notes__", ()):
                pending.add_note(note)


def load_baseline() -> ModuleType:
    spec = importlib.util.spec_from_file_location("owned_mvp_baseline", _BASELINE_PATH)
    if spec is None or spec.loader is None:
        raise OwnedPostgresError("Owned PostgreSQL baseline loader unavailable")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@dataclass(frozen=True)
class BaselineDatabase:
    url: sa.URL = field(repr=False)
    migration: ModuleType = field(repr=False)
    transaction_timeouts: tuple[str, str]


@contextmanager
def committed_baseline(server: OwnedPostgres) -> Iterator[BaselineDatabase]:
    """CREATE receipt/OID checks and DROP are retained in the existing helper."""
    server._lease.verify(server)
    with _owned_scratch_database(
        server.url.render_as_string(hide_password=False)
    ) as scratch_url:
        url = make_url(scratch_url)
        engine = sa.create_engine(
            url,
            poolclass=sa.pool.NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            migration = load_baseline()
            with engine.begin() as connection:
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                timeouts = (
                    connection.scalar(sa.text("SHOW lock_timeout")),
                    connection.scalar(sa.text("SHOW statement_timeout")),
                )
            # Only this newly created server permits committing cluster-global
            # baseline roles/jobs. No caller-supplied/operator URL is accepted.
            yield BaselineDatabase(url, migration, timeouts)
        finally:
            engine.dispose()


@contextmanager
def forbid_default_database() -> Iterator[list[str]]:
    """Fail on actual default init, reset, cleanup, lazy access or connection."""
    from app.core import database
    from tests.fixtures.database import database as fixtures

    calls: list[str] = []
    default_engines = tuple(
        engine.sync_engine
        for engine in (database._engine, database._read_replica_engine)
        if engine is not None
    )
    original_connect = sa.Engine.connect

    def reject(label: str) -> None:
        calls.append(label)
        raise AssertionError(f"Owned baseline blocked default database: {label}")

    def no_init(*_args: object, **_kwargs: object) -> None:
        reject("initialization")

    def no_reset(*_args: object, **_kwargs: object) -> None:
        reject("reset")

    async def no_clear(*_args: object, **_kwargs: object) -> None:
        reject("cleanup")

    def no_proxy(*_args: object, **_kwargs: object) -> None:
        reject("lazy access")

    def checked_connect(engine: sa.Engine) -> sa.Connection:
        if any(engine is candidate for candidate in default_engines):
            reject("connection")
        return original_connect(engine)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(database, "init_database", no_init)
        patch.setattr(fixtures, "init_database", no_init)
        patch.setattr(fixtures, "_require_safe_database_reset", no_reset)
        patch.setattr(fixtures, "_clear_mapped_database_rows", no_clear)
        patch.setattr(database._LazyProxy, "_get_current_object", no_proxy)
        patch.setattr(sa.Engine, "connect", checked_connect)
        yield calls
    assert calls == [], "Owned baseline attempted default database access"


@pytest.fixture(scope="module")
def default_database_guard() -> Iterator[list[str]]:
    with forbid_default_database() as calls:
        yield calls


@pytest.fixture(scope="module", autouse=True)
def initialize_database_for_tests(request: pytest.FixtureRequest) -> None:
    request.getfixturevalue("default_database_guard")


@pytest.fixture(scope="module", autouse=True)
def prepare_database(request: pytest.FixtureRequest) -> None:
    request.getfixturevalue("default_database_guard")


@pytest.fixture(autouse=True)
def clean_database(request: pytest.FixtureRequest) -> Iterator[None]:
    request.getfixturevalue("default_database_guard")
    yield


@pytest.fixture(scope="module")
def owned_baseline_server(request: pytest.FixtureRequest) -> Iterator[OwnedPostgres]:
    request.getfixturevalue("default_database_guard")
    with owned_postgres_server() as server:
        yield server
