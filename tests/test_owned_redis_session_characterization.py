"""Local harness controls; real Valkey/service evidence comes only from its job."""

import asyncio
import logging
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scripts.quality import owned_redis_session_characterization as proof


@pytest.mark.asyncio
async def test_client_seam_is_exact_and_restored_without_rendering_payloads():
    original_client = object()
    original_logger = object()
    module = SimpleNamespace(
        _get_shared_client=original_client,
        logger=original_logger,
    )
    client = object()

    class MustNotRender:
        def __str__(self):
            raise AssertionError("provider payload rendered")

        def __repr__(self):
            raise AssertionError("provider payload rendered")

    with pytest.raises(asyncio.CancelledError):
        with proof.service_client(module, client) as warnings:
            assert await module._get_shared_client(proof.URL) is client
            with pytest.raises(proof.fixture.Rejected):
                await module._get_shared_client("redis://unowned.invalid/0")
            module.logger.warning(MustNotRender(), MustNotRender(), exc_info=True)
            assert warnings.count == 1
            raise asyncio.CancelledError
    assert module._get_shared_client is original_client
    assert module.logger is original_logger


@pytest.mark.asyncio
async def test_nested_client_seams_restore_outer_and_original():
    original = object()
    module = SimpleNamespace(_get_shared_client=original, logger=original)
    outer = object()
    inner = object()
    with proof.service_client(module, outer) as outer_warnings:
        with proof.service_client(module, inner):
            assert await module._get_shared_client(proof.URL) is inner
        assert await module._get_shared_client(proof.URL) is outer
        assert module.logger is outer_warnings
    assert module._get_shared_client is original
    assert module.logger is original


@pytest.mark.asyncio
async def test_cancellation_barrier_requires_ack_then_prevents_expire():
    client = SimpleNamespace(hset=AsyncMock(return_value=1), expire=AsyncMock())
    barrier = proof.AfterHset(client)
    finished = asyncio.Event()

    async def operation():
        try:
            await barrier.hset("owned-key", mapping={"field": "value"})
            await barrier.expire("owned-key", 600)
        finally:
            finished.set()

    await proof.cancel_after_hset(operation(), barrier)
    client.hset.assert_awaited_once_with("owned-key", mapping={"field": "value"})
    client.expire.assert_not_awaited()
    assert barrier.acknowledged.is_set()
    assert finished.is_set()
    assert barrier.expire_calls == 0


@pytest.mark.asyncio
async def test_cancellation_swallow_is_rejected_and_task_joined():
    barrier = proof.AfterHset(SimpleNamespace(hset=AsyncMock(return_value=1)))

    async def operation():
        try:
            await barrier.hset("owned-key", mapping={"field": "value"})
        except asyncio.CancelledError:
            return

    with pytest.raises(proof.fixture.Rejected, match="CANCELLATION_NOT_PROPAGATED"):
        await proof.cancel_after_hset(operation(), barrier)


@pytest.mark.asyncio
async def test_hset_failure_does_not_claim_acknowledgement():
    failure = RuntimeError("unreported-provider-payload")
    barrier = proof.AfterHset(SimpleNamespace(hset=AsyncMock(side_effect=failure)))
    with pytest.raises(RuntimeError) as caught:
        await barrier.hset("owned-key", mapping={"field": "value"})
    assert caught.value is failure
    assert not barrier.acknowledged.is_set()
    assert barrier.expire_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [601000, 601001, 601002])
async def test_ttl_uses_server_clock_bounds(expiry):
    admin = SimpleNamespace(
        time=Mock(side_effect=[(1, 0), (1, 2000)]),
        execute_command=Mock(return_value=expiry),
    )
    operation = AsyncMock()
    await proof.refreshed(admin, "owned-key", 600, operation())
    operation.assert_awaited_once()
    admin.execute_command.assert_called_once_with("PEXPIRETIME", "owned-key")


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [-1, -2, 600999, 601003])
async def test_ttl_missing_or_outside_bounds_is_rejected(expiry):
    admin = SimpleNamespace(
        time=Mock(side_effect=[(1, 0), (1, 2000)]),
        execute_command=Mock(return_value=expiry),
    )
    with pytest.raises(proof.fixture.Rejected):
        await proof.refreshed(admin, "owned-key", 600, AsyncMock()())


def configure(monkeypatch):
    for name in tuple(os.environ):
        if name.endswith("_FILE") or name == "SECRET_KEY":
            monkeypatch.delenv(name)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ENV_FILE_PATH", "")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10")


def test_import_configuration_is_explicit_and_restored(monkeypatch):
    configure(monkeypatch)
    previous = logging.root.manager.disable
    module = SimpleNamespace(settings=SimpleNamespace(has_development_fallbacks=False))

    def importer(name):
        assert name == "app.services.auth.redis_session"
        assert len(os.environ["SECRET_KEY"]) >= 48
        assert logging.root.manager.disable == logging.CRITICAL
        return module

    monkeypatch.setattr(proof.importlib, "import_module", importer)
    assert proof.load_service() is module
    assert "SECRET_KEY" not in os.environ
    assert logging.root.manager.disable == previous


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ENVIRONMENT", "production"),
        ("DATABASE_URL", "postgresql://unowned.invalid/db"),
        ("ENV_FILE_PATH", ".env"),
        ("ACCESS_TOKEN_EXPIRE_MINUTES", "60"),
        ("SECRET_KEY_FILE", "/unowned/secret"),
        ("SECRET_KEY", "must-not-borrow-existing"),
    ],
)
def test_unsafe_import_configuration_never_imports(monkeypatch, name, value):
    configure(monkeypatch)
    monkeypatch.setenv(name, value)
    importer = Mock()
    monkeypatch.setattr(proof.importlib, "import_module", importer)
    with pytest.raises(proof.fixture.Rejected):
        proof.load_service()
    importer.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_import_error_or_development_fallback_fails_safely(monkeypatch, fails):
    configure(monkeypatch)
    previous = logging.root.manager.disable

    def importer(_name):
        if fails:
            raise RuntimeError("sensitive-provider-payload")
        return SimpleNamespace(settings=SimpleNamespace(has_development_fallbacks=True))

    monkeypatch.setattr(proof.importlib, "import_module", importer)
    with pytest.raises((RuntimeError, proof.fixture.Rejected)):
        proof.load_service()
    assert "SECRET_KEY" not in os.environ
    assert logging.root.manager.disable == previous


def test_main_ownership_failure_never_opens_redis(monkeypatch, capsys):
    monkeypatch.setattr(proof.importlib.metadata, "version", lambda _name: "8.1.0")
    monkeypatch.setattr(
        proof.fixture,
        "inspect_owned",
        Mock(side_effect=RuntimeError("sensitive-daemon-payload")),
    )
    connect = Mock()
    monkeypatch.setattr(proof.redis, "Redis", connect)
    assert proof.main() == 1
    connect.assert_not_called()
    assert capsys.readouterr().out == "VALKEY_SESSION_CHARACTERIZATION_REJECTED\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "exercise", "close", "ownership"])
async def test_owned_cleanup_and_failure_boundaries(monkeypatch, failure):
    class Service:
        KEY_PREFIX = "session:v2:"

    module = SimpleNamespace(RedisSessionService=Service)
    commands = []

    def execute(*args):
        commands.append(args)
        if args[:2] == ("ACL", "GETUSER"):
            return None
        return 1

    admin = SimpleNamespace(
        execute_command=Mock(side_effect=execute),
        exists=Mock(return_value=0),
        delete=Mock(),
    )
    client = SimpleNamespace(
        aclose=AsyncMock(
            side_effect=RuntimeError("private-close") if failure == "close" else None
        )
    )
    calls = 0

    def check_owner():
        nonlocal calls
        calls += 1
        if failure == "ownership" and calls == 3:
            raise proof.fixture.Rejected("OWNERSHIP_REJECTED")

    exercise = AsyncMock(
        side_effect=RuntimeError("private-exercise") if failure == "exercise" else None
    )
    monkeypatch.setattr(proof, "exercise", exercise)
    connect = Mock(return_value=client)
    monkeypatch.setattr(proof.async_redis, "Redis", connect)
    if failure == "none":
        await proof.characterize_service(admin, check_owner, module)
    else:
        with pytest.raises((RuntimeError, proof.fixture.Rejected)):
            await proof.characterize_service(admin, check_owner, module)
    client.aclose.assert_awaited_once()
    exercise.assert_awaited_once()
    assert calls == 3
    grant = next(command for command in commands if command[:2] == ("ACL", "SETUSER"))
    patterns = [
        item[1:] for item in grant if isinstance(item, str) and item.startswith("~")
    ]
    assert len(patterns) == 7
    assert all(key.startswith("session:v2:ttl-service-") for key in patterns)
    assert all("*" not in key and "?" not in key and "[" not in key for key in patterns)
    assert {key.rsplit(":", 1)[1] for key in patterns} == {str(i) for i in range(7)}
    if failure == "ownership":
        admin.delete.assert_not_called()
        assert not any(command[:2] == ("ACL", "DELUSER") for command in commands)
    else:
        admin.delete.assert_called_once_with(*patterns)
        assert ("ACL", "DELUSER", grant[2]) in commands
    kwargs = connect.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == proof.fixture.PORT
    assert kwargs["protocol"] == 2
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("collision", ["user", "key"])
async def test_collision_does_not_claim_or_delete_existing_state(
    monkeypatch, collision
):
    module = SimpleNamespace(
        RedisSessionService=SimpleNamespace(KEY_PREFIX="session:v2:")
    )
    admin = SimpleNamespace(
        execute_command=Mock(return_value={} if collision == "user" else None),
        exists=Mock(return_value=1 if collision == "key" else 0),
        delete=Mock(),
    )
    connect = Mock()
    monkeypatch.setattr(proof.async_redis, "Redis", connect)
    with pytest.raises(proof.fixture.Rejected):
        await proof.characterize_service(admin, Mock(), module)
    connect.assert_not_called()
    admin.delete.assert_not_called()
    assert all(
        call.args[:2] == ("ACL", "GETUSER")
        for call in admin.execute_command.call_args_list
    )


def test_warning_classifier_requires_exact_permission_family_without_formatting():
    warnings = proof.SafeWarnings()
    warnings.warning("fixed", "private-key", proof.NoPermissionError("private-error"))
    assert warnings.count == warnings.permission_denials == 1
    warnings.warning("fixed", "private-key", RuntimeError("private-error"))
    assert warnings.count == 2
    assert warnings.permission_denials == 1


@pytest.mark.asyncio
async def test_pre_ack_provider_failure_is_joined_and_rethrown():
    failure = RuntimeError("private-before-ack")
    client = SimpleNamespace(hset=AsyncMock(side_effect=failure), expire=AsyncMock())
    barrier = proof.AfterHset(client)
    loop = asyncio.get_running_loop()
    reports = []
    original = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: reports.append(context))
    try:
        with pytest.raises(RuntimeError) as caught:
            await proof.cancel_after_hset(barrier.hset("owned-key"), barrier)
        assert caught.value is failure
        await asyncio.sleep(0)
        assert reports == []
        assert not barrier.acknowledged.is_set()
        client.expire.assert_not_awaited()
    finally:
        loop.set_exception_handler(original)
