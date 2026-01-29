from unittest.mock import patch

from typer.testing import CliRunner

from app.cli.tests import app

runner = CliRunner()


def test_run_default():
    """Test running tests with default arguments."""
    with patch("app.cli.tests.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        result = runner.invoke(app, ["run"])

        assert result.exit_code == 0
        assert "Tests passed successfully!" in result.stdout

        # Verify default command construction
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "pytest" in cmd
        assert "tests" in cmd
        assert "--cov=app" in cmd  # coverage is True by default


def test_run_options():
    """Test running tests with custom options."""
    with patch("app.cli.tests.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        result = runner.invoke(
            app, ["run", "my_tests", "--no-coverage", "--parallel", "--ff"]
        )

        assert result.exit_code == 0

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "my_tests" in cmd
        assert "--cov=app" not in cmd
        assert "-n" in cmd
        assert "auto" in cmd
        assert "-x" in cmd


def test_run_failure():
    """Test running tests when pytest fails."""
    with patch("app.cli.tests.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1

        result = runner.invoke(app, ["run"])

        assert result.exit_code == 1
        assert "Tests failed with exit code 1" in result.stdout


def test_smoke_success():
    """Test smoke tests execution."""
    with patch("app.cli.tests.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        result = runner.invoke(app, ["smoke"])

        assert result.exit_code == 0
        assert "Smoke tests passed!" in result.stdout

        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        assert "pytest" in cmd
        assert "tests/smoke" in cmd


def test_smoke_failure():
    """Test execution when smoke tests fail."""
    with patch("app.cli.tests.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1

        result = runner.invoke(app, ["smoke"])

        assert result.exit_code == 1
        assert "Smoke tests failed!" in result.stdout
