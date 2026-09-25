from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.migrate_passwords import _is_bcrypt, app

runner = CliRunner()


def test_is_bcrypt():
    assert _is_bcrypt("$2b$12$somehash...") is True
    assert _is_bcrypt("$2a$10$somehash...") is True
    assert _is_bcrypt("$2y$10$somehash...") is True
    assert _is_bcrypt("argon2id...") is False


@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


def test_report_no_users(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert "Legacy bcrypt accounts remaining: 0" in result.stdout
    assert "No active legacy bcrypt accounts are currently reported" in result.stdout
    assert "Migration complete" not in result.stdout


def test_report_with_users_is_count_only_by_default(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert "Legacy bcrypt accounts remaining: 1" in result.stdout
    assert "test@example.com" not in result.stdout
    assert "No records were changed" in result.stdout


def test_report_can_show_only_opaque_ids(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        sample_result = MagicMock()
        sample_result.scalars.return_value.all.return_value = [
            "00000000-0000-0000-0000-000000000001"
        ]
        mock_db_session.execute.side_effect = [count_result, sample_result]

        result = runner.invoke(app, ["report", "--show-ids", "--limit", "1"])

    assert result.exit_code == 0
    assert "00000000-0000-0000-0000-000000000001" in result.stdout
    assert "@" not in result.stdout


def test_report_rejects_negative_limit():
    result = runner.invoke(app, ["report", "--limit", "-1"])
    assert result.exit_code != 0
    assert "zero or positive" in result.output


def test_assert_none_returns_success_when_empty(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["assert-none"])

    assert result.exit_code == 0
    assert "No active legacy bcrypt accounts" in result.stdout


def test_assert_none_fails_closed_when_rows_remain(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["assert-none"])

    assert result.exit_code == 1
    assert "Legacy bcrypt accounts remain: 1" in result.stdout
    mock_db_session.commit.assert_not_called()
