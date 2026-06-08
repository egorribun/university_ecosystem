from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.migrate_passwords import _is_bcrypt, app
from app.models import User

runner = CliRunner()


def test_is_bcrypt():
    assert _is_bcrypt("$2b$12$somehash...") is True
    assert _is_bcrypt("$2a$10$somehash...") is True
    assert _is_bcrypt("argon2id...") is False


@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


def test_report_no_users(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["report"])
        assert result.exit_code == 0
        assert "Bcrypt accounts remaining: 0" in result.stdout
        assert "Migration complete" in result.stdout


def test_report_with_users(mock_db_session):
    user_mock = MagicMock(spec=User)
    user_mock.id = 1
    user_mock.email = "test@example.com"
    user_mock.hashed_password = "$2b$12$somehash..."
    user_mock.is_active = True

    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_mock]
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["report"])
        assert result.exit_code == 0
        assert "Bcrypt accounts remaining: 1" in result.stdout
        assert "test@example.com" in result.stdout


def test_force_reset_no_users(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["force-reset", "--yes"])
        assert result.exit_code == 0
        assert "No bcrypt accounts found" in result.stdout


def test_force_reset_with_users(mock_db_session):
    user_mock = MagicMock(spec=User)
    user_mock.id = 1
    user_mock.email = "test@example.com"
    user_mock.hashed_password = "$2b$12$somehash..."
    user_mock.is_active = True

    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        # 1. count active users -> returns user_mock (so count=1)
        # 2. force_reset_batch update query
        # 3. count_bcrypt_users -> returns empty list (so remaining=0)
        mock_result_count_1 = MagicMock()
        mock_result_count_1.scalars.return_value.all.return_value = [user_mock]

        mock_result_update = MagicMock()

        mock_result_count_2 = MagicMock()
        mock_result_count_2.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [
            mock_result_count_1,  # count in force_reset
            mock_result_count_1,  # select inside force_reset_batch
            mock_result_update,  # update inside force_reset_batch
            mock_result_count_2,  # count inside force_reset_batch (remaining)
        ]

        result = runner.invoke(app, ["force-reset", "--yes"])
        assert result.exit_code == 0
        assert "1 marked for reset" in result.stdout
        mock_db_session.commit.assert_called()
