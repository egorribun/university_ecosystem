import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from typer.testing import CliRunner

from app.cli.__main__ import app as root_app
from app.management.normalize_static import _normalize_path, _rename_files
from app.management.normalize_static import main as normalize_static_main
from app.management.reset_mfa import (
    _async_main,
    _audit_cli,
    _build_arg_parser,
    _load_user,
    _reset_user_mfa,
)
from app.management.reset_mfa import main as reset_mfa_main
from app.management.squash_migrations import main as squash_migrations_main
from app.management.stories_cleanup import main as stories_cleanup_main
from app.management.weekly_cleanup import main as weekly_cleanup_main
from app.management.weekly_cleanup import run_weekly_cleanup
from app.scripts.backfill_uuids import main as backfill_uuids_main

# Declarative models for backfill testing to mimic transition phase
TestBase = declarative_base()


class MockUser(TestBase):
    __tablename__ = "mock_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid_id: Mapped[str] = mapped_column(String, nullable=True)
    created_at = None


class MockActiveSession(TestBase):
    __tablename__ = "mock_active_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid_id: Mapped[str] = mapped_column(String, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer)
    shadow_user_id: Mapped[str] = mapped_column(String, nullable=True)
    created_at = None


@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


# ===========================================================================
# root cli app (__main__.py) tests
# ===========================================================================


def test_root_app_help() -> None:
    runner = CliRunner()
    result = runner.invoke(root_app, ["--help"])
    assert result.exit_code == 0
    assert "University Ecosystem Unified CLI" in result.stdout


# ===========================================================================
# normalize_static.py tests
# ===========================================================================


def test_normalize_path_not_file() -> None:
    path = MagicMock(spec=Path)
    path.is_file.return_value = False
    assert _normalize_path(path) is None


def test_normalize_path_no_normalization_needed() -> None:
    path = MagicMock(spec=Path)
    path.is_file.return_value = True
    path.stem = "safe-prefix_remainder"
    path.suffix = ".png"
    path.name = "safe-prefix_remainder.png"
    assert _normalize_path(path) is None


def test_normalize_path_needs_normalization() -> None:
    path = MagicMock(spec=Path)
    path.is_file.return_value = True
    path.stem = "Unsafe Prefix_remainder"
    path.suffix = ".png"
    path.name = "Unsafe Prefix_remainder.png"
    path.parent.name = "avatars"

    target_mock = MagicMock(spec=Path)
    target_mock.name = "unsafe-prefix_remainder.png"
    path.with_name.return_value = target_mock
    target_mock.exists.return_value = False

    result = _normalize_path(path)
    assert result is not None
    assert result[0] == target_mock
    assert result[1] == "/static/avatars/unsafe-prefix_remainder.png"


def test_rename_files_real_fs(tmp_path) -> None:
    avatars_dir = tmp_path / "avatars"
    avatars_dir.mkdir(parents=True)

    # Create a file that needs normalization
    old_file = avatars_dir / "Unsafe Name_123.png"
    old_file.write_text("dummy")

    # Create a file that already exists to trigger collision counter path
    collision_target = avatars_dir / "unsafe-name_123.png"
    collision_target.write_text("exists")

    avatar_mapping, _ = _rename_files(tmp_path)

    # It should normalize to "unsafe-name_123-1.png" because of collision!
    expected_new_file = avatars_dir / "unsafe-name_123-1.png"
    assert expected_new_file.exists()
    assert "/static/avatars/Unsafe Name_123.png" in avatar_mapping
    assert (
        avatar_mapping["/static/avatars/Unsafe Name_123.png"]
        == "/static/avatars/unsafe-name_123-1.png"
    )


@pytest.mark.asyncio
async def test_normalize_static_main(mock_db_session) -> None:
    base_dir = Path("/tmp/static")  # noqa: S108

    # Override session.begin to be a MagicMock so it behaves as a synchronous context manager
    mock_db_session.begin = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock()
    mock_begin.__aexit__ = AsyncMock()
    mock_db_session.begin.return_value = mock_begin

    with (
        patch("app.management.normalize_static.settings") as mock_settings,
        patch(
            "app.management.normalize_static.async_session",
            return_value=mock_db_session,
        ),
        patch("app.management.normalize_static._rename_files") as mock_rename,
    ):
        mock_settings.static_dir_path = base_dir
        mock_rename.return_value = (
            {"/static/avatars/old.png": "/static/avatars/new.png"},
            {},
        )

        await normalize_static_main()
        mock_db_session.execute.assert_called_once()


# ===========================================================================
# reset_mfa.py tests
# ===========================================================================


def test_build_arg_parser() -> None:
    parser = _build_arg_parser()
    assert isinstance(parser, argparse.ArgumentParser)


@pytest.mark.asyncio
async def test_load_user_by_id(mock_db_session) -> None:
    user = MagicMock()
    mock_db_session.get.return_value = user
    res = await _load_user(mock_db_session, user_id=1, email=None)
    assert res == user


@pytest.mark.asyncio
async def test_load_user_by_email(mock_db_session) -> None:
    user = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db_session.execute.return_value = mock_result

    res = await _load_user(mock_db_session, user_id=None, email="TEST@example.com")
    assert res == user


@pytest.mark.asyncio
async def test_load_user_both_none(mock_db_session) -> None:
    res = await _load_user(mock_db_session, user_id=None, email=None)
    assert res is None


def test_audit_cli() -> None:
    with patch("app.management.reset_mfa.audit_logger") as mock_logger:
        _audit_cli("test_event", user_id=1, reason="test", extra={"foo": "bar"})
        mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_reset_user_mfa_not_found(mock_db_session) -> None:
    with patch("app.management.reset_mfa.async_session", return_value=mock_db_session):
        mock_db_session.get.return_value = None
        with pytest.raises(ValueError, match="User not found"):
            await _reset_user_mfa(user_id=999, email=None, notify=True)


@pytest.mark.asyncio
async def test_reset_user_mfa_success(mock_db_session) -> None:
    user = MagicMock()
    user.id = 1
    stats = MagicMock()
    stats.changed = True
    stats.totp_deleted = 1
    stats.challenges_revoked = 1

    with (
        patch("app.management.reset_mfa.async_session", return_value=mock_db_session),
        patch("app.management.reset_mfa.mfa.reset_user_mfa", return_value=stats),
        patch("app.management.reset_mfa.create_notifications_for_users") as mock_notify,
        patch("app.management.reset_mfa._audit_cli") as mock_audit,
    ):
        mock_db_session.get.return_value = user

        res_user, res_stats = await _reset_user_mfa(user_id=1, email=None, notify=True)
        assert res_user == user
        assert res_stats == stats
        mock_notify.assert_called_once()
        mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_reset_mfa() -> None:
    user = MagicMock()
    user.id = 1
    stats = MagicMock()
    stats.totp_deleted = 0
    stats.challenges_revoked = 0
    stats.fields_cleared = []

    args = argparse.Namespace(user_id=1, email=None, no_notify=True)

    with patch(
        "app.management.reset_mfa._reset_user_mfa", return_value=(user, stats)
    ) as mock_reset:
        await _async_main(args)
        mock_reset.assert_called_once_with(user_id=1, email=None, notify=False)


def test_reset_mfa_main() -> None:
    args = argparse.Namespace(user_id=1, email=None, no_notify=True)
    with (
        patch("app.management.reset_mfa._build_arg_parser") as mock_parser,
        patch("app.management.reset_mfa._async_main"),
        patch("app.management.reset_mfa.asyncio.run") as mock_run,
    ):
        mock_parser.return_value.parse_args.return_value = args
        reset_mfa_main()
        mock_run.assert_called_once()


# ===========================================================================
# squash_migrations.py tests
# ===========================================================================


def test_squash_migrations_no_migrations() -> None:
    mock_versions_dir = MagicMock(spec=Path)
    mock_versions_dir.glob.return_value = []
    with patch("app.management.squash_migrations.VERSIONS_DIR", mock_versions_dir):
        with pytest.raises(SystemExit) as exc:
            squash_migrations_main()
        assert exc.value.code == 1


def test_squash_migrations_too_few_migrations() -> None:
    migrations = [Path("0001_initial.py"), Path("0002_user.py")]
    mock_versions_dir = MagicMock(spec=Path)
    mock_versions_dir.glob.return_value = migrations
    with patch("app.management.squash_migrations.VERSIONS_DIR", mock_versions_dir):
        with pytest.raises(SystemExit) as exc:
            squash_migrations_main()
        assert exc.value.code == 0


def test_squash_migrations_proceed(tmp_path) -> None:
    versions_dir = tmp_path / "alembic" / "versions"
    versions_dir.mkdir(parents=True)

    # Create 25 migrations
    for i in range(25):
        (versions_dir / f"{i:04d}_migration.py").write_text("content")

    with (
        patch("app.management.squash_migrations.VERSIONS_DIR", versions_dir),
        patch(
            "app.management.squash_migrations.ARCHIVE_DIR", versions_dir / "_archived"
        ),
        patch("builtins.input", return_value="y"),
    ):
        squash_migrations_main()

        # 5 should be archived (since KEEP_RECENT = 20)
        archived_dir = versions_dir / "_archived"
        assert archived_dir.exists()
        assert len(list(archived_dir.glob("*.py"))) == 5
        # 20 kept + 1 new baseline
        assert len(list(versions_dir.glob("*.py"))) == 21


# ===========================================================================
# stories_cleanup.py tests
# ===========================================================================


def test_stories_cleanup_main() -> None:
    with patch(
        "app.management.stories_cleanup.cleanup_expired_stories", new_callable=AsyncMock
    ) as mock_cleanup:
        mock_cleanup.return_value = 5
        stories_cleanup_main()
        mock_cleanup.assert_called_once()


# ===========================================================================
# weekly_cleanup.py tests
# ===========================================================================


@pytest.mark.asyncio
async def test_run_weekly_cleanup(mock_db_session) -> None:
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock()
    mock_engine.connect.return_value = mock_conn

    with (
        patch(
            "app.management.weekly_cleanup.async_session", return_value=mock_db_session
        ),
        patch("app.management.weekly_cleanup.engine", mock_engine),
        patch("app.management.weekly_cleanup.settings") as mock_settings,
    ):
        mock_settings.database_url = (
            "postgresql://user:pass@localhost/mydb"  # pragma: allowlist secret
        )

        orphaned_calls = 0
        stale_calls = 0

        async def mock_execute(stmt):
            nonlocal orphaned_calls, stale_calls
            stmt_str = str(stmt)
            if "NOT" in stmt_str or "user_id" in stmt_str:
                orphaned_calls += 1
                mock_res = MagicMock()
                if orphaned_calls == 1:
                    mock_res.scalars.return_value.fetchmany.return_value = [1]
                else:
                    mock_res.scalars.return_value.fetchmany.return_value = []
                return mock_res
            else:
                stale_calls += 1
                mock_res = MagicMock()
                if stale_calls == 1:
                    mock_res.scalars.return_value.fetchmany.return_value = [2]
                else:
                    mock_res.scalars.return_value.fetchmany.return_value = []
                return mock_res

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        stats = await run_weekly_cleanup()
        assert stats["subscriptions_removed"] == 2
        assert stats["subscriptions_orphaned"] == 1
        assert stats["subscriptions_stale"] == 1

        mock_conn.execution_options.assert_called_once()


def test_weekly_cleanup_main() -> None:
    with patch(
        "app.management.weekly_cleanup.run_weekly_cleanup", new_callable=AsyncMock
    ) as mock_run:
        mock_run.return_value = {"subscriptions_removed": 0}
        weekly_cleanup_main()
        mock_run.assert_called_once()


# ===========================================================================
# backfill_uuids.py tests
# ===========================================================================


@pytest.mark.asyncio
async def test_backfill_uuids_main(mock_db_session) -> None:
    with (
        patch("app.scripts.backfill_uuids.async_session", return_value=mock_db_session),
        patch("app.scripts.backfill_uuids.User", MockUser),
        patch("app.scripts.backfill_uuids.ActiveSession", MockActiveSession),
        patch("app.scripts.backfill_uuids.TABLES_OWN_ID", [(MockUser, "created_at")]),
        patch(
            "app.scripts.backfill_uuids.TABLES_USER_FK",
            [(MockActiveSession, "user_id", "shadow_user_id")],
        ),
    ):
        rec_own = MagicMock()
        rec_own.uuid_id = None
        rec_own.created_at = None

        mock_res_own_1 = MagicMock()
        mock_res_own_1.scalars.return_value.all.return_value = [rec_own]
        mock_res_own_2 = MagicMock()
        mock_res_own_2.scalars.return_value.all.return_value = []

        # Stream mapping
        row = MagicMock()
        row.id = 1
        row.uuid_id = "some-uuid"

        async def mock_stream_result():
            yield row

        mock_db_session.stream.return_value = mock_stream_result()

        # FK loop
        rec_fk = MagicMock()
        rec_fk.user_id = 1
        rec_fk.shadow_user_id = None

        mock_res_fk_1 = MagicMock()
        mock_res_fk_1.scalars.return_value.all.return_value = [rec_fk]
        mock_res_fk_2 = MagicMock()
        mock_res_fk_2.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [
            mock_res_own_1,
            mock_res_own_2,
            mock_res_fk_1,
            mock_res_fk_2,
        ]

        await backfill_uuids_main()

        assert rec_own.uuid_id is not None
        assert rec_fk.shadow_user_id == "some-uuid"
        mock_db_session.commit.assert_called()
