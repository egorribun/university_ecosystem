import argparse
import os
import shlex
import subprocess
import sys


def get_alembic_cmd() -> list[str]:
    # Priority 1: Direct 'alembic' script in PATH
    try:
        # Check if alembic exists and is runnable
        subprocess.run(["alembic", "--version"], capture_output=True, check=True)  # noqa: S607
        return ["alembic"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Priority 2: 'uv run alembic' if uv is present
    try:
        subprocess.run(
            ["uv", "run", "alembic", "--version"],  # noqa: S607
            capture_output=True,
            check=True,
        )
        return ["uv", "run", "alembic"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Priority 3: python module (some environments might prefer this)
    # Note: 'python -m alembic' sometimes fails if __main__ is missing.
    return [sys.executable, "-m", "alembic"]


ALEMBIC_BASE_CMD = get_alembic_cmd()
print(f"INFO: Using Alembic command: {shlex.join(ALEMBIC_BASE_CMD)}")


def run_command(cmd: list[str], env=None) -> bool:
    print(f"Executing: {shlex.join(cmd)}")
    result = subprocess.run(cmd, shell=False, env=env, check=False)  # noqa: S603
    if result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Migration Stress Test")
    parser.add_argument(
        "--db-url",
        help=(
            "Database URL to test against. "
            "Default: uses DATABASE_URL env or temp SQLite."
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Perform a full downgrade to 'base' (GitHub CI style).",
    )
    args = parser.parse_args()

    # Use SQLite for a quick syntax check if no DATABASE_URL is provided
    # Using aiosqlite to match project's async nature
    db_url = (
        args.db_url
        or os.getenv("DATABASE_URL")
        or "sqlite+aiosqlite:///./temp_test_db.db"
    )

    # Ensure PostgreSQL URLs use the async driver (asyncpg) required by the project
    is_postgres = db_url.startswith("postgresql://") or db_url.startswith(
        "postgresql+asyncpg://"
    )
    if is_postgres:
        if "+asyncpg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # On Windows, asyncpg with SSL can sometimes cause ConnectionResetError
        # if the server doesn't support it or during handshake quirks.
        if "ssl=" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url += f"{separator}ssl=disable"

        print(f"INFO: Normalized PostgreSQL URL: {db_url}")

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    print(f"--- Starting Migration Stress Test on {db_url} ---")
    if args.full:
        print("NOTE: Running FULL downgrade-to-base cycle.")

    # 1. Clean start for SQLite
    if "sqlite" in db_url:
        db_file = db_url.split("///")[-1]
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
                print(f"Removed old test database: {db_file}")
            except Exception as e:
                print(f"Warning: Could not remove {db_file}: {e}")

    # 2. Upgrade to Head
    print("\n--- Phase 1: Upgrade to Head ---")
    if not run_command(
        [*ALEMBIC_BASE_CMD, "-c", "alembic.ini", "upgrade", "head"], env
    ):
        sys.exit(1)

    # 3. Test Downgrade
    print("\n--- Phase 2: Testing Downgrade ---")
    downgrade_target = "base" if args.full else "-1"
    print(f"Downgrading to: {downgrade_target}")

    if not run_command(
        [*ALEMBIC_BASE_CMD, "-c", "alembic.ini", "downgrade", downgrade_target], env
    ):
        print(
            "\n[!] Downgrade failed! This usually means a migration in the chain "
            "cannot be reversed cleanly (e.g. missing IF EXISTS, or doomed "
            "transaction)."
        )
        sys.exit(1)

    # 4. Final Upgrade back to Head
    print("\n--- Phase 3: Final Upgrade back to Head ---")
    if not run_command(
        [*ALEMBIC_BASE_CMD, "-c", "alembic.ini", "upgrade", "head"], env
    ):
        print(
            "\n[!] Final upgrade failed! The downgrade left the DB in a broken state."
        )
        sys.exit(1)

    print("\nSUCCESS: Migration cycle completed successfully!")
    if "sqlite" in db_url:
        print(
            "\nNote: SQLite check passed. To check for PostgreSQL-specific issues, "
            "run with local Postgres: \n"
            '$env:DATABASE_URL="postgresql://..." ; '
            "python scripts/test_migrations.py --full"
        )


if __name__ == "__main__":
    main()
