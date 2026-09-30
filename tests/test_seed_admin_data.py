import pytest
from sqlalchemy import select

import app.models as models
from scripts.seed_admin_data import AUDIT_ACTIONS, seed_audit_logs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_seed_audit_logs_is_idempotent(db_session, user_factory, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_SECRET", "test-audit-signing-key")
    admin = await user_factory(role="admin")
    other = await user_factory(role="student")

    async def demo_seed_logs():
        result = await db_session.scalars(select(models.DataAccessLog))
        return [
            row
            for row in result.all()
            if row.context and row.context.get("demo_seed") is True
        ]

    await seed_audit_logs(db_session, admin, [other])
    first_run_logs = await demo_seed_logs()
    assert len(first_run_logs) == len(AUDIT_ACTIONS)
    await db_session.commit()

    await seed_audit_logs(db_session, admin, [other])
    second_run_logs = await demo_seed_logs()

    assert len(second_run_logs) == len(first_run_logs)


async def test_admin_seed_fails_closed_before_database_initialization_without_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import seed_admin_data

    def database_must_not_start() -> None:
        pytest.fail(
            "admin seeding must reject a missing password before database initialization"
        )

    monkeypatch.setattr(seed_admin_data, "init_database", database_must_not_start)
    monkeypatch.delenv("TEST_PASSWORD", raising=False)
    try:
        with pytest.raises(RuntimeError, match="TEST_PASSWORD"):
            await seed_admin_data.main()
    finally:
        capsys.readouterr()

    monkeypatch.setenv("TEST_PASSWORD", " \t ")
    try:
        with pytest.raises(RuntimeError, match="TEST_PASSWORD"):
            await seed_admin_data.main()
    finally:
        capsys.readouterr()


async def test_admin_seed_uses_transient_password_without_logging_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import secrets

    from scripts import seed_admin_data

    runtime_password = secrets.token_urlsafe(32)
    monkeypatch.setenv("TEST_PASSWORD", runtime_password)

    def no_op_init_database() -> None:
        return None

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    observed_passwords: list[str] = []

    async def capture_admin_password(db, *, admin_password: str):
        observed_passwords.append(admin_password)
        return object()

    async def no_op_seed(db, *args):
        return []

    monkeypatch.setattr(seed_admin_data, "init_database", no_op_init_database)
    monkeypatch.setattr(seed_admin_data, "async_session", FakeSession)
    monkeypatch.setattr(seed_admin_data, "find_or_create_admin", capture_admin_password)
    monkeypatch.setattr(seed_admin_data, "seed_extra_groups", no_op_seed)
    monkeypatch.setattr(seed_admin_data, "seed_extra_users", no_op_seed)
    monkeypatch.setattr(seed_admin_data, "seed_audit_logs", no_op_seed)
    monkeypatch.setattr(seed_admin_data, "seed_dead_letter_jobs", no_op_seed)

    try:
        await seed_admin_data.main()
    finally:
        output = capsys.readouterr()

    if len(observed_passwords) != 1 or not secrets.compare_digest(
        observed_passwords[0], runtime_password
    ):
        pytest.fail(
            "admin seeder did not pass the transient password to the admin creator"
        )

    if runtime_password in output.out or runtime_password in output.err:
        pytest.fail("admin seeder wrote the transient password to captured output")


async def test_reseeding_existing_admin_replaces_the_password_hash(
    db_session, user_factory, capsys: pytest.CaptureFixture[str]
) -> None:
    import secrets

    from app.auth.security import verify_password_sync
    from scripts import seed_admin_data

    previous_password = secrets.token_urlsafe(32) + "!Aa0"
    current_password = secrets.token_urlsafe(32) + "!Aa0"
    previous_hash = seed_admin_data.get_password_hash_sync(previous_password)
    existing = await user_factory(
        email=seed_admin_data.ADMIN_EMAIL,
        role="admin",
        hashed_password=previous_hash,
    )

    result = await seed_admin_data.find_or_create_admin(
        db_session, admin_password=current_password
    )
    await db_session.commit()
    await db_session.refresh(existing)

    if result.id != existing.id:
        pytest.fail("admin reseeding must update the existing seeded account")
    if not verify_password_sync(current_password, existing.hashed_password):
        pytest.fail("admin reseeding must apply the current per-run password")
    if verify_password_sync(previous_password, existing.hashed_password):
        pytest.fail("admin reseeding must invalidate the previous password")

    output = capsys.readouterr()
    if current_password in output.out or current_password in output.err:
        pytest.fail("admin reseeding must not log the current password")
