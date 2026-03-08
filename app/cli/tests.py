import subprocess  # nosec B404
from typing import Annotated

import typer

app = typer.Typer(help="Test management commands.")


@app.command()
def run(
    path: Annotated[str, typer.Argument(help="Path to tests to run.")] = "tests",
    coverage: Annotated[bool, typer.Option(help="Run with coverage report.")] = True,
    parallel: Annotated[
        bool, typer.Option(help="Run tests in parallel (xdist).")
    ] = False,
    fail_fast: Annotated[
        bool, typer.Option("--ff", help="Stop on first failure.")
    ] = False,
) -> None:
    """Run the test suite."""
    cmd = ["pytest", path]

    if coverage:
        cmd.extend(["--cov=app", "--cov-report=term-missing", "--cov-report=xml"])

    if parallel:
        cmd.extend(["-n", "auto"])

    if fail_fast:
        cmd.append("-x")

    typer.echo(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd)  # nosec B603

    if result.returncode != 0:
        typer.secho(
            f"Tests failed with exit code {result.returncode}", fg=typer.colors.RED
        )
        raise typer.Exit(result.returncode)
    else:
        typer.secho("Tests passed successfully!", fg=typer.colors.GREEN)


@app.command()
def smoke() -> None:
    """Run smoke tests against the live environment."""
    # This could run a specific set of tests or a separate script
    typer.echo("Running smoke tests...")
    cmd = ["pytest", "tests/smoke"]
    result = subprocess.run(cmd)  # nosec B603

    if result.returncode != 0:
        typer.secho("Smoke tests failed!", fg=typer.colors.RED)
        raise typer.Exit(result.returncode)
    else:
        typer.secho("Smoke tests passed!", fg=typer.colors.GREEN)
