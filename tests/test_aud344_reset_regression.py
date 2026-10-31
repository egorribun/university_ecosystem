import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from typer.testing import CliRunner

import app.cli.db as candidate_cli
from app.core.database import Base
from app.models import ActiveSession, Group, User, UserRole


def _session(existing):
    db = AsyncMock()
    db.__aenter__.return_value = db

    async def exit_context(exc_type, _exc, _tb):
        if exc_type is not None:
            await db.rollback()

    db.__aexit__.side_effect = exit_context
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute.return_value = result
    db.add = MagicMock()
    return db


def test_existing_admin_reset_rotates_epoch_and_revokes_before_commit():
    events = []
    existing_digest = uuid4().hex
    replacement_digest = uuid4().hex
    existing = SimpleNamespace(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        email="existing@example.test",
        hashed_password=existing_digest,
        mfa_epoch=11,
    )
    db = _session(existing)

    async def revoke(**kwargs):
        events.append("revoke")
        assert kwargs["db"] is db
        assert kwargs["lock_rows"] is True
        compiled = kwargs["whereclause"].compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert "active_sessions.user_id =" in sql
        assert "active_sessions.revoked_at IS NULL" in sql
        assert list(compiled.params.values()) == [existing.id]
        return 2

    async def commit():
        events.append("commit")

    db.commit.side_effect = commit
    with (
        patch.object(candidate_cli, "async_session", return_value=db),
        patch.object(
            candidate_cli,
            "get_password_hash",
            new_callable=AsyncMock,
            return_value=replacement_digest,
        ),
        patch.object(
            candidate_cli, "revoke_sessions_matching", side_effect=revoke
        ) as revoker,
    ):
        result = CliRunner().invoke(
            candidate_cli.app,
            [
                "create-admin",
                "--email",
                existing.email,
                "--password",
                "newpass",
            ],
        )

    assert result.exit_code == 0, result.output
    assert existing.hashed_password == replacement_digest
    assert existing.mfa_epoch == 12
    account_lock_sql = str(
        db.execute.await_args_list[0].args[0].compile(dialect=postgresql.dialect())
    )
    assert "FROM users" in account_lock_sql
    assert account_lock_sql.rstrip().endswith("FOR UPDATE")
    revoker.assert_awaited_once()
    assert events == ["revoke", "commit"]
    assert "Revoked 2 active session(s)" in result.output


def test_actual_session_helper_redis_failure_rolls_back_database_but_keeps_prior_tombstone(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "aud344-reset.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}", poolclass=NullPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    existing_digest = uuid4().hex
    replacement_digest = uuid4().hex
    first_jti = str(uuid4())
    second_jti = str(uuid4())

    async def setup_database() -> UUID:
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all,
                tables=[Group.__table__, User.__table__, ActiveSession.__table__],
            )
        async with session_factory() as db:
            user = User(
                email="fixture@example.test",
                hashed_password=existing_digest,
                role=UserRole.ADMIN,
                is_active=True,
                mfa_epoch=4,
            )
            db.add(user)
            await db.flush()
            db.add_all(
                [
                    ActiveSession(
                        user_id=user.id,
                        jti=first_jti,
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    ),
                    ActiveSession(
                        user_id=user.id,
                        jti=second_jti,
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    ),
                ]
            )
            await db.commit()
            return user.id

    user_id = asyncio.run(setup_database())
    tombstones = set()
    attempts: list[str] = []

    async def revoke_jti(jti, *, expires_at):
        del expires_at
        attempts.append(jti)
        if len(attempts) == 1:
            tombstones.add(jti)
            return
        raise RuntimeError("revocation backend unavailable")

    backend = AsyncMock()
    backend.revoke_session.side_effect = revoke_jti
    try:
        with (
            patch.object(candidate_cli, "async_session", new=session_factory),
            patch.object(
                candidate_cli,
                "get_password_hash",
                new_callable=AsyncMock,
                return_value=replacement_digest,
            ),
            patch(
                "app.services.session_cleanup.get_session_backend",
                new_callable=AsyncMock,
                return_value=backend,
            ),
        ):
            result = CliRunner().invoke(
                candidate_cli.app,
                [
                    "create-admin",
                    "--email",
                    "fixture@example.test",
                    "--password",
                    "newpass",
                ],
            )

        assert result.exit_code != 0
        assert "Password reset." not in result.output
        backend.revoke_session.assert_awaited()
        assert len(attempts) == 2
        assert set(attempts) == {
            first_jti,
            second_jti,
        }
        assert len(tombstones) == 1
        assert tombstones.issubset({first_jti, second_jti})
        assert tombstones.issubset(set(attempts))

        async def verify_rollback() -> None:
            async with session_factory() as db:
                user = await db.get(User, user_id)
                assert user is not None
                assert user.hashed_password == existing_digest
                assert user.mfa_epoch == 4
                result = await db.execute(
                    select(ActiveSession)
                    .where(ActiveSession.user_id == user_id)
                    .order_by(ActiveSession.jti)
                )
                sessions = list(result.scalars())
                assert len(sessions) == 2
                assert all(session.revoked_at is None for session in sessions)

        asyncio.run(verify_rollback())
    finally:
        asyncio.run(engine.dispose())


def test_new_admin_creation_does_not_call_existing_user_revocation():
    generated_digest = uuid4().hex
    db = _session(None)
    with (
        patch.object(candidate_cli, "async_session", return_value=db),
        patch.object(
            candidate_cli,
            "get_password_hash",
            new_callable=AsyncMock,
            return_value=generated_digest,
        ),
        patch.object(
            candidate_cli,
            "revoke_sessions_matching",
            new_callable=AsyncMock,
        ) as revoker,
    ):
        result = CliRunner().invoke(
            candidate_cli.app,
            [
                "create-admin",
                "--email",
                "new@example.test",
                "--password",
                "newpass",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Created admin user: new@example.test" in result.output
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    revoker.assert_not_awaited()
