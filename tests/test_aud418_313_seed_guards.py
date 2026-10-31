"""Isolated regression tests for audit-seed signing configuration."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.dtos.audit import DataAccessLogDTO
from app.services import audit_service
from scripts import seed_admin_data


class SyntheticAuditStore:
    """Keep seed log operations in memory; never open a database connection."""

    def __init__(self) -> None:
        self.queries = 0
        self.logs: dict[object, DataAccessLogDTO] = {}

    async def scalar(self, query) -> str | None:
        self.queries += 1
        if next(iter(query.selected_columns)).key == "signature":
            return next(reversed(self.logs.values())).signature
        return None

    async def connection(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="synthetic"))

    @asynccontextmanager
    async def begin_nested(self):
        original_logs = self.logs.copy()
        try:
            yield
        except BaseException:
            self.logs = original_logs
            raise


class SyntheticAuditRepository:
    def __init__(self, db: SyntheticAuditStore) -> None:
        self.db = db

    async def create(self, values: dict) -> DataAccessLogDTO:
        log = DataAccessLogDTO(id=uuid4(), created_at=datetime.now(UTC), **values)
        self.db.logs[log.id] = log
        return log

    async def update(self, log_id: object, values: dict) -> DataAccessLogDTO:
        log = self.db.logs[log_id].model_copy(update=values)
        self.db.logs[log_id] = log
        return log


async def _run_fresh_process(child: str, environment: dict[str, str]) -> dict:
    import asyncio
    import json
    import sys

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        child,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        pytest.fail("fresh audit-seed test process failed")
    return json.loads(stdout.decode("utf-8").splitlines()[-1])


@pytest.mark.parametrize("secret", [None, "", "   ", " ,  , "])
async def test_aud418_missing_signing_key_does_not_query_or_write_audit_rows(
    monkeypatch: pytest.MonkeyPatch, secret: str | None
) -> None:
    monkeypatch.delenv("AUDIT_LOG_SECRET_FILE", raising=False)
    if secret is None:
        monkeypatch.delenv("AUDIT_LOG_SECRET", raising=False)
        monkeypatch.setattr(
            seed_admin_data,
            "settings",
            SimpleNamespace(audit_log_secret="cached-value", model_fields_set=set()),
        )
    else:
        monkeypatch.setenv("AUDIT_LOG_SECRET", secret)
    monkeypatch.setattr(audit_service, "AuditRepository", SyntheticAuditRepository)
    db = SyntheticAuditStore()

    await seed_admin_data.seed_audit_logs(db, SimpleNamespace(id=uuid4()), [])

    assert db.queries == 0
    assert not db.logs


async def test_aud418_seeded_logs_verify_with_active_rotation_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import secrets

    active_key = secrets.token_hex(32)
    previous_key = secrets.token_hex(32)
    monkeypatch.delenv("AUDIT_LOG_SECRET_FILE", raising=False)
    monkeypatch.setenv("AUDIT_LOG_SECRET", f" {active_key} , {previous_key} ")
    monkeypatch.setattr(audit_service, "AuditRepository", SyntheticAuditRepository)
    db = SyntheticAuditStore()

    await seed_admin_data.seed_audit_logs(db, SimpleNamespace(id=uuid4()), [])

    assert len(db.logs) == len(seed_admin_data.AUDIT_ACTIONS)
    verifier = audit_service.SecureAuditService(signing_key=active_key.encode())
    assert all(verifier.verify_integrity(log) for log in db.logs.values())


async def test_aud418_seed_uses_the_resolved_file_key_before_plain_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import secrets

    mounted_key = secrets.token_hex(32)
    monkeypatch.setenv("AUDIT_LOG_SECRET_FILE", "synthetic-secret-file")
    monkeypatch.setenv("AUDIT_LOG_SECRET", secrets.token_hex(32))
    monkeypatch.setattr(
        seed_admin_data,
        "settings",
        SimpleNamespace(audit_log_secret=mounted_key),
        raising=False,
    )
    monkeypatch.setattr(audit_service, "AuditRepository", SyntheticAuditRepository)
    db = SyntheticAuditStore()

    await seed_admin_data.seed_audit_logs(db, SimpleNamespace(id=uuid4()), [])

    assert len(db.logs) == len(seed_admin_data.AUDIT_ACTIONS)
    verifier = audit_service.SecureAuditService(signing_key=mounted_key.encode())
    assert all(verifier.verify_integrity(log) for log in db.logs.values())


@pytest.mark.parametrize("source", ["environment_file", "mounted_secret"])
async def test_aud418_fresh_process_seeds_with_configured_key(
    tmp_path,
    source: str,
) -> None:
    """The seed and the application's verifier use the same loaded settings."""
    import os
    import secrets

    key_file = tmp_path / "synthetic-settings"
    key = secrets.token_hex(32)
    content = "AUDIT_LOG_SECRET=" + key if source == "environment_file" else key
    key_file.write_text(content + "\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.pop("AUDIT_LOG_SECRET", None)
    environment.pop("AUDIT_LOG_SECRET_FILE", None)
    environment.update(
        ENVIRONMENT="testing",
        ENV_FILE_PATH=str(key_file) if source == "environment_file" else "",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        SECRET_KEY=secrets.token_hex(32),
        PYTHONUTF8="1",
    )
    if source == "mounted_secret":
        environment["AUDIT_LOG_SECRET_FILE"] = str(key_file)
        environment["AUDIT_LOG_SECRET"] = secrets.token_hex(32)
    child = r"""
import asyncio, contextlib, io, json, sys
from types import SimpleNamespace
from uuid import uuid4

sys.modules["magic"] = None
with contextlib.redirect_stdout(io.StringIO()):
    from app.services import audit_service
    from scripts import seed_admin_data
    from tests.test_aud418_313_seed_guards import SyntheticAuditRepository, SyntheticAuditStore

    audit_service.AuditRepository = SyntheticAuditRepository
    store = SyntheticAuditStore()
    asyncio.run(seed_admin_data.seed_audit_logs(store, SimpleNamespace(id=uuid4()), []))
    verifier = audit_service.SecureAuditService()
    result = {
        "configured": "audit_log_secret" in seed_admin_data.settings.model_fields_set,
        "count": len(store.logs),
        "expected": len(seed_admin_data.AUDIT_ACTIONS),
        "valid": all(verifier.verify_integrity(log) for log in store.logs.values()),
    }
print(json.dumps(result))
"""
    report = await _run_fresh_process(child, environment)
    assert report["configured"]
    assert report["count"] == report["expected"]
    assert report["valid"]


@pytest.mark.parametrize("secret", [None, "", "   "])
async def test_aud418_fresh_process_missing_or_blank_key_fails_closed(
    secret: str | None,
) -> None:
    import os
    import secrets

    environment = os.environ.copy()
    environment.pop("AUDIT_LOG_SECRET", None)
    environment.pop("AUDIT_LOG_SECRET_FILE", None)
    environment.update(
        ENVIRONMENT="testing",
        ENV_FILE_PATH="",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        SECRET_KEY=secrets.token_hex(32),
        PYTHONUTF8="1",
    )
    if secret is not None:
        environment["AUDIT_LOG_SECRET"] = secret

    child = r"""
import asyncio, contextlib, io, json, sys
from types import SimpleNamespace
from uuid import uuid4

sys.modules["magic"] = None
with contextlib.redirect_stdout(io.StringIO()):
    try:
        from scripts import seed_admin_data
    except Exception as exc:
        result = {
            "error": type(exc).__name__,
            "audit_config": "AUDIT_LOG_SECRET" in str(exc),
        }
    else:
        class Store:
            def __init__(self): self.queries = 0
            async def scalar(self, _query):
                self.queries += 1
                return 1
        store = Store()
        asyncio.run(seed_admin_data.seed_audit_logs(store, SimpleNamespace(id=uuid4()), []))
        result = {"error": None, "queries": store.queries}
print(json.dumps(result))
"""
    report = await _run_fresh_process(child, environment)
    if secret is None:
        assert report == {"error": None, "queries": 0}
    else:
        assert report == {"error": "ValidationError", "audit_config": True}


@pytest.mark.parametrize("file_path", ["", "   "])
async def test_aud418_blank_secret_file_does_not_use_cached_settings(
    monkeypatch: pytest.MonkeyPatch, file_path: str
) -> None:
    monkeypatch.setenv("AUDIT_LOG_SECRET_FILE", file_path)
    monkeypatch.setattr(
        seed_admin_data,
        "settings",
        SimpleNamespace(audit_log_secret=uuid4().hex),
    )
    db = SyntheticAuditStore()

    await seed_admin_data.seed_audit_logs(db, SimpleNamespace(id=uuid4()), [])

    assert db.queries == 0
    assert not db.logs


@pytest.mark.parametrize(
    "failure_site", ["sign", "update", "update_missing", "mismatch", "deleted"]
)
@pytest.mark.parametrize("successful_writes", [0, 2])
async def test_aud418_audit_failure_rolls_back_savepoint_before_outer_commit(
    monkeypatch: pytest.MonkeyPatch, failure_site: str, successful_writes: int
) -> None:
    import secrets

    from sqlalchemy import delete, func, select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.logs import DataAccessLog

    monkeypatch.delenv("AUDIT_LOG_SECRET_FILE", raising=False)
    monkeypatch.setenv("AUDIT_LOG_SECRET", secrets.token_hex(32))
    actor_id = uuid4()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    original_sign = audit_service.SecureAuditService._compute_signature
    original_update = audit_service.AuditRepository.update
    successful_calls = 0

    def fail_sign(service, log):
        nonlocal successful_calls
        if successful_calls == successful_writes:
            raise RuntimeError("synthetic audit failure")
        successful_calls += 1
        return original_sign(service, log)

    async def fail_update(repository, *args):
        nonlocal successful_calls
        if successful_calls == successful_writes:
            if failure_site == "update_missing":
                return None
            if failure_site == "mismatch":
                updated = await original_update(repository, *args)
                row = await repository._get_orm(args[0])
                row.signature = "different-synthetic-signature"
                await repository.db.flush()
                return updated
            if failure_site == "deleted":
                await repository.db.execute(
                    delete(DataAccessLog).where(DataAccessLog.id == args[0])
                )
                return None
            raise RuntimeError("synthetic audit failure")
        successful_calls += 1
        return await original_update(repository, *args)

    if failure_site == "sign":
        monkeypatch.setattr(
            audit_service.SecureAuditService, "_compute_signature", fail_sign
        )
    else:
        monkeypatch.setattr(audit_service.AuditRepository, "update", fail_update)

    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE users (id CHAR(32) PRIMARY KEY)"
            )
            await connection.exec_driver_sql(
                "INSERT INTO users (id) VALUES (?)", (actor_id.hex,)
            )
            await connection.run_sync(DataAccessLog.__table__.create)
            await connection.exec_driver_sql(
                "CREATE TABLE seed_markers (id INTEGER PRIMARY KEY)"
            )
            await connection.exec_driver_sql("INSERT INTO seed_markers (id) VALUES (1)")

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            await db.execute(text("INSERT INTO seed_markers (id) VALUES (2)"))
            failure_seen = False
            try:
                await seed_admin_data.seed_audit_logs(
                    db, SimpleNamespace(id=actor_id), []
                )
            except RuntimeError:
                failure_seen = True
            await db.commit()

        async with sessions() as db:
            audit_count = await db.scalar(
                select(func.count()).select_from(DataAccessLog)
            )
            marker_rows = (
                (await db.execute(text("SELECT id FROM seed_markers ORDER BY id")))
                .scalars()
                .all()
            )

        assert failure_seen
        assert audit_count == 0
        assert marker_rows == [1, 2]
    finally:
        await engine.dispose()


async def test_aud418_outer_rollback_discards_successful_audit_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import secrets

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.logs import DataAccessLog

    monkeypatch.delenv("AUDIT_LOG_SECRET_FILE", raising=False)
    monkeypatch.setenv("AUDIT_LOG_SECRET", secrets.token_hex(32))
    actor_id = uuid4()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE users (id CHAR(32) PRIMARY KEY)"
            )
            await connection.exec_driver_sql(
                "INSERT INTO users (id) VALUES (?)", (actor_id.hex,)
            )
            await connection.run_sync(DataAccessLog.__table__.create)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            await seed_admin_data.seed_audit_logs(db, SimpleNamespace(id=actor_id), [])
            await db.rollback()
        async with sessions() as db:
            audit_count = await db.scalar(
                select(func.count()).select_from(DataAccessLog)
            )

        assert audit_count == 0
    finally:
        await engine.dispose()


async def test_aud418_main_rolls_back_its_seed_transaction_after_signing_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import secrets

    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.logs import DataAccessLog

    monkeypatch.delenv("AUDIT_LOG_SECRET_FILE", raising=False)
    monkeypatch.setenv("AUDIT_LOG_SECRET", secrets.token_hex(32))
    actor_id = uuid4()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    def fail_sign(*_args):
        raise RuntimeError("synthetic audit failure")

    async def admin(db, **_kwargs):
        await db.execute(text("INSERT INTO seed_markers (id) VALUES (2)"))
        return SimpleNamespace(id=actor_id)

    async def groups(_db):
        return {}

    async def users(_db, _groups):
        return []

    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE users (id CHAR(32) PRIMARY KEY)"
            )
            await connection.exec_driver_sql(
                "INSERT INTO users (id) VALUES (?)", (actor_id.hex,)
            )
            await connection.run_sync(DataAccessLog.__table__.create)
            await connection.exec_driver_sql(
                "CREATE TABLE seed_markers (id INTEGER PRIMARY KEY)"
            )
            await connection.exec_driver_sql("INSERT INTO seed_markers (id) VALUES (1)")

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(seed_admin_data, "async_session", sessions)
        monkeypatch.setattr(seed_admin_data, "init_database", lambda: None)
        monkeypatch.setattr(
            seed_admin_data, "_required_test_password", lambda: "in-memory"
        )
        monkeypatch.setattr(
            seed_admin_data,
            "require_owned_live_stand_target",
            lambda: seed_admin_data.ADMIN_SMOKE_PROJECT,
        )
        monkeypatch.setattr(seed_admin_data, "find_or_create_admin", admin)
        monkeypatch.setattr(seed_admin_data, "seed_extra_groups", groups)
        monkeypatch.setattr(seed_admin_data, "seed_extra_users", users)
        monkeypatch.setattr(
            audit_service.SecureAuditService, "_compute_signature", fail_sign
        )

        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            await seed_admin_data.main()

        async with sessions() as db:
            audit_count = await db.scalar(
                select(func.count()).select_from(DataAccessLog)
            )
            markers = (
                (await db.execute(text("SELECT id FROM seed_markers ORDER BY id")))
                .scalars()
                .all()
            )

        assert audit_count == 0
        assert markers == [1]
    finally:
        await engine.dispose()


async def test_aud418_main_does_not_claim_skipped_audit_logs_were_signed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AUDIT_LOG_SECRET", raising=False)
    monkeypatch.delenv("AUDIT_LOG_SECRET_FILE", raising=False)
    monkeypatch.setattr(
        seed_admin_data,
        "settings",
        SimpleNamespace(audit_log_secret="cached-value", model_fields_set=set()),
    )
    monkeypatch.setattr(
        seed_admin_data,
        "require_owned_live_stand_target",
        lambda: seed_admin_data.ADMIN_SMOKE_PROJECT,
    )
    monkeypatch.setattr(seed_admin_data, "_required_test_password", lambda: "in-memory")
    monkeypatch.setattr(seed_admin_data, "init_database", lambda: None)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            pass

    async def admin(_db, **_kwargs):
        return SimpleNamespace(id=uuid4())

    async def groups(_db):
        return {}

    async def users(_db, _groups):
        return []

    async def jobs(_db):
        pass

    monkeypatch.setattr(seed_admin_data, "async_session", Session)
    monkeypatch.setattr(seed_admin_data, "find_or_create_admin", admin)
    monkeypatch.setattr(seed_admin_data, "seed_extra_groups", groups)
    monkeypatch.setattr(seed_admin_data, "seed_extra_users", users)
    monkeypatch.setattr(seed_admin_data, "seed_dead_letter_jobs", jobs)

    await seed_admin_data.main()

    output = capsys.readouterr().out
    assert "skipping audit log seed" in output
    assert "signed logs" not in output
