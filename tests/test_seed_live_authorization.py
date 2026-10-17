"""Owned stand bootstrap contracts using SQL rows and the installed Authzed SDK.

The in-memory channel exercises protobuf requests, not a real SpiceDB server.
"""

from __future__ import annotations

import importlib
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from authzed.api.v1 import (
    CheckPermissionResponse,
    RelationshipUpdate,
    WriteRelationshipsResponse,
    WriteSchemaResponse,
    ZedToken,
)

from scripts import live_stand, seed_admin_data, seed_target

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "ue-live-0123456789abcdef"


class AuthorizationChannel:
    """Minimal transport fake retaining relationship state across reruns."""

    def __init__(self) -> None:
        self.schema = ""
        self.relationships = {("document", "existing", "viewer", "other-user")}
        self.requests = []
        self.failure = None
        self.deny = False
        self.closed = False

    def __enter__(self):
        self.closed = False
        return self

    def __exit__(self, *args):
        self.closed = True

    def unary_unary(self, path, *, request_serializer, response_deserializer, **kw):
        def call(request, *, metadata, timeout):
            # Use the actual generated SDK serializer/deserializer at each boundary.
            request = type(request).FromString(request_serializer(request))
            method = path.rsplit("/", 1)[1]
            self.requests.append((method, request, metadata, timeout))
            if self.failure == method:
                raise RuntimeError(f"injected {method} failure")
            if method == "WriteSchema":
                self.schema = request.schema
                response = WriteSchemaResponse()
            elif method == "WriteRelationships":
                assert self.schema
                for update in request.updates:
                    relationship = update.relationship
                    key = (
                        relationship.resource.object_type,
                        relationship.resource.object_id,
                        relationship.relation,
                        relationship.subject.object.object_id,
                    )
                    if update.operation == RelationshipUpdate.OPERATION_CREATE:
                        assert key not in self.relationships, "duplicate relationship"
                    assert update.operation in {
                        RelationshipUpdate.OPERATION_CREATE,
                        RelationshipUpdate.OPERATION_TOUCH,
                    }
                    assert relationship.subject.object.object_type == "user"
                    self.relationships.add(key)
                response = WriteRelationshipsResponse(
                    written_at=ZedToken(token="seed-revision")
                )
            elif method == "CheckPermission":
                assert request.consistency.at_least_as_fresh.token == "seed-revision"
                key = (
                    request.resource.object_type,
                    request.resource.object_id,
                    request.permission,
                    request.subject.object.object_id,
                )
                response = CheckPermissionResponse(
                    permissionship=(
                        CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
                        if key in self.relationships and not self.deny
                        else CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
                    )
                )
            else:
                pytest.fail(f"unexpected RPC: {method}")
            return response_deserializer(response.SerializeToString())

        return call

    def unary_stream(self, *args, **kwargs):
        return self._unexpected_stream

    def stream_unary(self, *args, **kwargs):
        return self._unexpected_stream

    def _unexpected_stream(self, *args, **kwargs):
        pytest.fail("authorization bootstrap must not enumerate or import grants")


@pytest.fixture
def seed_module(monkeypatch):
    script = ROOT / "scripts" / "seed_live_authorization.py"
    assert script.is_file(), "owned-live authorization bootstrap entry point is missing"
    module = importlib.import_module("scripts.seed_live_authorization")
    monkeypatch.delenv("UE_SEED_TARGET", raising=False)
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", PROJECT)
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", PROJECT)
    monkeypatch.setenv("SPICEDB_INSECURE", "true")
    monkeypatch.setattr(
        seed_target,
        "_configured_database_url",
        lambda: "postgresql+asyncpg://stand@postgres/stand",
    )
    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            spicedb_endpoint="spicedb:50051",
            spicedb_preshared_key="synthetic-test-token",
        ),
    )
    return module


@pytest.fixture
def authorization_channel(seed_module, monkeypatch):
    channel = AuthorizationChannel()

    def connect(target):
        assert target == "spicedb:50051"
        return channel

    monkeypatch.setattr(seed_module.grpc, "insecure_channel", connect)
    return channel


@pytest.fixture
def seeded_database(seed_module, db_session, monkeypatch):
    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(seed_module, "init_database", lambda: None)
    monkeypatch.setattr(seed_module, "async_session", session)
    return db_session


async def test_bootstrap_grants_only_the_seeded_admin_and_is_repeatable(
    seed_module, seeded_database, user_factory, authorization_channel, capsys
):
    admin = await seed_admin_data.find_or_create_admin(
        seeded_database, admin_password=secrets.token_urlsafe(32) + "!Aa0"
    )
    other_admin = await user_factory(role="admin")
    student = await user_factory(role="student")
    await seeded_database.commit()
    original_hash = admin.hashed_password

    await seed_module.main()
    await seed_module.main()

    assert authorization_channel.schema == (ROOT / "schema.zed").read_text()
    assert authorization_channel.relationships == {
        ("document", "existing", "viewer", "other-user"),
        ("semester", "current", "admin", str(admin.id)),
    }
    assert str(other_admin.id) not in repr(authorization_channel.relationships)
    assert str(student.id) not in repr(authorization_channel.relationships)
    assert admin.hashed_password == original_hash
    assert authorization_channel.closed
    assert [call[0] for call in authorization_channel.requests] == [
        "WriteSchema",
        "WriteRelationships",
        "CheckPermission",
        "WriteSchema",
        "WriteRelationships",
        "CheckPermission",
    ]
    for _, _, metadata, timeout in authorization_channel.requests:
        assert metadata == (("authorization", "Bearer synthetic-test-token"),)
        assert 0 < timeout <= 30
    output = capsys.readouterr()
    assert "synthetic-test-token" not in output.out + output.err


@pytest.mark.parametrize("identity", ["missing", "student", "inactive"])
async def test_invalid_seed_admin_fails_before_spicedb_writes(
    seed_module, seeded_database, user_factory, authorization_channel, identity
):
    await user_factory(role="admin")
    if identity != "missing":
        await user_factory(
            email=seed_admin_data.ADMIN_EMAIL,
            role="student" if identity == "student" else "admin",
            is_active=identity != "inactive",
        )

    with pytest.raises(RuntimeError, match=r"seeded.*admin"):
        await seed_module.main()

    assert authorization_channel.requests == []


@pytest.mark.parametrize(
    "failure", ["WriteSchema", "WriteRelationships", "CheckPermission", "denied"]
)
async def test_authorization_failure_aborts_seed(
    seed_module, seeded_database, user_factory, authorization_channel, failure
):
    await user_factory(email=seed_admin_data.ADMIN_EMAIL, role="admin")
    authorization_channel.failure = failure
    authorization_channel.deny = failure == "denied"

    with pytest.raises(RuntimeError):
        await seed_module.main()

    calls = [call[0] for call in authorization_channel.requests]
    expected = ["WriteSchema", "WriteRelationships", "CheckPermission"]
    assert calls == (
        expected if failure == "denied" else expected[: expected.index(failure) + 1]
    )
    assert authorization_channel.closed


@pytest.mark.parametrize(
    "invalid_target",
    [
        "unowned",
        "project-mismatch",
        "external-database",
        "admin-smoke",
        "external-spicedb",
        "wrong-port",
        "tls-required",
        "missing-key",
    ],
)
async def test_unverified_targets_fail_before_database_or_spicedb_access(
    seed_module, monkeypatch, invalid_target
):
    if invalid_target == "unowned":
        monkeypatch.delenv("LIVE_STAND_OWNER_VERIFIED")
    elif invalid_target == "project-mismatch":
        monkeypatch.setenv("COMPOSE_PROJECT_NAME", "other-project")
    elif invalid_target == "external-database":
        monkeypatch.setattr(
            seed_target,
            "_configured_database_url",
            lambda: "postgresql+asyncpg://stand@external.example/stand",
        )
    elif invalid_target == "admin-smoke":
        monkeypatch.setattr(
            seed_module,
            "require_owned_live_stand_target",
            lambda: seed_target.ADMIN_SMOKE_PROJECT,
        )
    elif invalid_target == "external-spicedb":
        seed_module.settings.spicedb_endpoint = "external.example:50051"
    elif invalid_target == "wrong-port":
        seed_module.settings.spicedb_endpoint = "spicedb:443"
    elif invalid_target == "tls-required":
        monkeypatch.setenv("SPICEDB_INSECURE", "false")
    elif invalid_target == "missing-key":
        seed_module.settings.spicedb_preshared_key = ""

    def forbidden(*args, **kwargs):
        pytest.fail("invalid target reached a database or authorization connection")

    monkeypatch.setattr(seed_module, "init_database", forbidden)
    monkeypatch.setattr(seed_module.grpc, "insecure_channel", forbidden)
    with pytest.raises(RuntimeError):
        await seed_module.main()


async def test_missing_canonical_schema_fails_before_any_connection(
    seed_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(seed_module, "SCHEMA_PATH", tmp_path / "missing.zed")

    def forbidden(*args, **kwargs):
        pytest.fail("missing schema reached a database or authorization connection")

    monkeypatch.setattr(seed_module, "init_database", forbidden)
    monkeypatch.setattr(seed_module.grpc, "insecure_channel", forbidden)
    with pytest.raises(FileNotFoundError):
        await seed_module.main()


async def test_empty_canonical_schema_fails_before_any_connection(
    seed_module, monkeypatch, tmp_path
):
    schema_path = tmp_path / "schema.zed"
    schema_path.write_text(" \n ", encoding="utf-8")
    monkeypatch.setattr(seed_module, "SCHEMA_PATH", schema_path)

    def forbidden(*args, **kwargs):
        pytest.fail("empty schema reached a database or authorization connection")

    monkeypatch.setattr(seed_module, "init_database", forbidden)
    monkeypatch.setattr(seed_module.grpc, "insecure_channel", forbidden)
    with pytest.raises(RuntimeError, match="schema"):
        await seed_module.main()


@pytest.fixture
def stand_seed_runner(monkeypatch, tmp_path):
    worktree = tmp_path / "stand"
    source_root = tmp_path / "checkout"
    owner = live_stand.StandOwner(
        repository=str(source_root),
        worktree=str(worktree),
        project_name=PROJECT,
        published_ports=(),
        schema_version=live_stand.OWNER_SCHEMA_VERSION,
    )
    runs = []
    resource_checks = []
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "REPO_ROOT", source_root)
    monkeypatch.setattr(live_stand, "_require_worktree", lambda: None)
    monkeypatch.setattr(live_stand, "load_stand_owner", lambda path: owner)
    monkeypatch.setattr(live_stand, "_require_owned_docker_daemon", lambda owner: None)
    monkeypatch.setattr(live_stand, "load_vapid", lambda path: {})
    monkeypatch.setattr(live_stand, "stand_environment", lambda *args: {})
    monkeypatch.setattr(
        live_stand,
        "_verify_stand_owner_compose_resources",
        lambda path, checked_owner: resource_checks.append(checked_owner),
    )
    monkeypatch.setattr(
        live_stand, "compose_command", lambda *args, project_name: list(args)
    )
    monkeypatch.setattr(
        live_stand,
        "_run",
        lambda command, *, cwd, env: runs.append((command, dict(env))),
    )
    return SimpleNamespace(
        runs=runs,
        owner=owner,
        resource_checks=resource_checks,
        worktree=worktree,
        source_root=source_root,
    )


@pytest.mark.parametrize("in_place", [False, True])
def test_live_seed_runs_authorization_last_with_matching_readonly_schema(
    stand_seed_runner, monkeypatch, in_place
):
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", in_place)
    live_stand._seed_locked("synthetic-test-password", owner=stand_seed_runner.owner)

    runs = stand_seed_runner.runs
    assert [command[-1] for command, env in runs] == [
        "scripts/seed_demo_data.py",
        "scripts/seed_admin_data.py",
        "scripts/seed_live_authorization.py",
    ]
    source_root = (
        stand_seed_runner.source_root if in_place else stand_seed_runner.worktree
    )
    command, environment = runs[-1]
    assert f"{source_root / 'schema.zed'}:/app/schema.zed:ro" in command
    assert (
        command[command.index(f"{source_root / 'schema.zed'}:/app/schema.zed:ro") - 1]
        == "-v"
    )
    assert f"{source_root / 'scripts'}:/app/scripts:ro" in command
    assert "TEST_PASSWORD" not in environment
    assert "TEST_PASSWORD" not in command
    assert f"LIVE_STAND_SEED_PROJECT={PROJECT}" in command
    assert "LIVE_STAND_OWNER_VERIFIED=1" in command
    assert stand_seed_runner.resource_checks == [stand_seed_runner.owner] * 3


def test_authorization_subprocess_failure_aborts_live_seed(
    stand_seed_runner, monkeypatch
):
    def run(command, *, cwd, env):
        stand_seed_runner.runs.append(command)
        if command[-1] == "scripts/seed_live_authorization.py":
            raise live_stand.StandError("authorization seed failed")

    monkeypatch.setattr(live_stand, "_run", run)
    with pytest.raises(live_stand.StandError, match="authorization seed failed"):
        live_stand._seed_locked(
            "synthetic-test-password", owner=stand_seed_runner.owner
        )
