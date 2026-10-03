"""Exercise the password preflight inside a locally built immutable backend image.

This gate is deliberately limited to the passwordless, disposable PostgreSQL
service in the DB Migration Gate. It refuses every other database endpoint.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import subprocess
import sys
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

# The script entrypoint starts under scripts/quality, so local imports follow
# explicit repository-root setup above.
from sqlalchemy import delete, select, text  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_READER_ROLE = "migration_password_preflight_reader"
_EMPTY_MESSAGE = "No active legacy bcrypt accounts found."
_REMAINING_MESSAGE = "Legacy bcrypt accounts remain: 1"


class GateFailure(RuntimeError):
    """A fail-closed preflight assertion failed without safe diagnostics."""


def _validated_database_url(value: str) -> URL:
    """Accept only the passwordless local DB Migration Gate service URL."""

    try:
        url = make_url(value)
    except Exception:
        raise GateFailure("the disposable PostgreSQL URL is malformed") from None

    if (
        url.drivername != "postgresql+asyncpg"
        or url.username != "test"
        or url.password is not None
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5433
        or url.database != "test_migration"
        or url.query
    ):
        raise GateFailure("refusing a database outside the disposable CI service")
    return url


def _validated_image_id(value: str) -> str:
    """Require Docker's full content-addressed local image config ID."""

    if not _IMAGE_ID.fullmatch(value):
        raise GateFailure("backend image is not identified by a full SHA-256 image ID")
    return value


def _docker_command(image_id: str) -> list[str]:
    """Run the exact CLI in the backend image by immutable image ID."""

    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "--env",
        "DATABASE_URL",
        "--env",
        "ENVIRONMENT",
        "--env",
        "SECRET_KEY",
        "--entrypoint",
        "/opt/venv/bin/python",
        image_id,
        "-m",
        "app.cli",
        "migrate-passwords",
        "assert-none",
    ]


def _assert_cli_result(
    result: subprocess.CompletedProcess[str], *, exit_code: int, stdout: str
) -> None:
    """Require the exact expected result, rejecting connection errors too."""

    stdout_matches = result.stdout.strip().endswith(stdout)
    if result.returncode != exit_code or not stdout_matches or result.stderr.strip():
        raise GateFailure(
            "backend preflight result did not match the expected state "
            f"(exit={result.returncode}, expected_exit={exit_code}, "
            f"stdout_matches={stdout_matches}, "
            f"stderr_present={bool(result.stderr.strip())})"
        )


async def _drop_reader_role_if_present(connection: AsyncConnection) -> None:
    """Drop only the reader role created by this run if it survived rollback."""

    result = await connection.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
        {"role": _READER_ROLE},
    )
    if result.scalar_one_or_none() is None:
        return
    await connection.execute(text("DROP OWNED BY migration_password_preflight_reader"))
    await connection.execute(text("DROP ROLE migration_password_preflight_reader"))


async def _finalize_gate(
    cleanup: Callable[[], Awaitable[None]],
    dispose: Callable[[], Awaitable[None]],
    primary_error: BaseException | None,
) -> None:
    """Attempt cleanup and disposal without masking the gate's primary error."""

    secondary_error: BaseException | None = None
    for operation_name, operation in (("cleanup", cleanup), ("disposal", dispose)):
        try:
            await operation()
        except BaseException as error:
            if secondary_error is None:
                secondary_error = error
            else:
                secondary_error.add_note(
                    f"engine {operation_name} also failed ({type(error).__name__})"
                )

    if secondary_error is None:
        return
    if primary_error is not None:
        primary_error.add_note(
            f"gate cleanup or disposal also failed ({type(secondary_error).__name__})"
        )
        for note in getattr(secondary_error, "__notes__", ()):
            primary_error.add_note(note)
        return
    raise secondary_error


def _run_cli(
    image_id: str, database_url: str, secret_key: str
) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env.update(
        {
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "test",
            "SECRET_KEY": secret_key,
        }
    )
    try:
        _validated_image_id(image_id)
        # Fixed argv, no shell, and a full SHA-256 image ID guard the executable.
        return subprocess.run(  # noqa: S603
            _docker_command(image_id),
            check=False,
            capture_output=True,
            env=child_env,
            text=True,
        )
    except OSError:
        raise GateFailure("could not run the backend image preflight") from None


async def _run_gate(admin_url: URL, image_id: str) -> None:
    from app.models.users import User

    engine: AsyncEngine = create_async_engine(admin_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    reader_url = admin_url.set(
        username=_READER_ROLE,
        password=None,
        host="127.0.0.1",
        port=5433,
    ).render_as_string(hide_password=True)
    reader_creation_attempted = False
    seeded_user_id: Any | None = None
    secret_key = secrets.token_hex(32)
    primary_error: BaseException | None = None

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE ROLE migration_password_preflight_reader "
                    "LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT"
                )
            )
            # If a later statement aborts this transaction, cleanup checks
            # pg_roles before trying to drop a role that no longer exists.
            reader_creation_attempted = True
            await connection.execute(
                text(
                    "GRANT CONNECT ON DATABASE test_migration TO migration_password_preflight_reader"
                )
            )
            await connection.execute(
                text(
                    "GRANT USAGE ON SCHEMA public TO migration_password_preflight_reader"
                )
            )
            await connection.execute(
                text(
                    "GRANT SELECT ON TABLE public.users TO migration_password_preflight_reader"
                )
            )
            role = (
                await connection.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = :role"
                    ),
                    {"role": _READER_ROLE},
                )
            ).one()
            if role.rolsuper or role.rolbypassrls:
                raise GateFailure(
                    "preflight reader role has elevated PostgreSQL privileges"
                )

        _assert_cli_result(
            _run_cli(image_id, reader_url, secret_key),
            exit_code=0,
            stdout=_EMPTY_MESSAGE,
        )

        # The CLI checks this historical prefix only; no authentication path
        # consumes this deliberately non-verifiable synthetic sentinel.
        synthetic_hash = f"$2b$ci-{uuid.uuid4().hex}"
        async with sessions() as session:
            user = User.create(
                email=f"migration-preflight-{uuid.uuid4().hex}@example.invalid",
                hashed_password=synthetic_hash,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            seeded_user_id = user.id
            if seeded_user_id is None:
                raise GateFailure("synthetic preflight row was not assigned an ID")
            await session.commit()

        _assert_cli_result(
            _run_cli(image_id, reader_url, secret_key),
            exit_code=1,
            stdout=_REMAINING_MESSAGE,
        )

        async with sessions() as session:
            unchanged = await session.execute(
                select(User.id).where(
                    User.id == seeded_user_id,
                    User.hashed_password == synthetic_hash,
                    User.is_active.is_(True),
                )
            )
            if unchanged.scalar_one_or_none() is None:
                raise GateFailure("preflight changed or removed the synthetic user row")
            await session.execute(delete(User).where(User.id == seeded_user_id))
            await session.commit()
        seeded_user_id = None

        _assert_cli_result(
            _run_cli(image_id, reader_url, secret_key),
            exit_code=0,
            stdout=_EMPTY_MESSAGE,
        )
    except BaseException as error:
        primary_error = error
        raise
    finally:

        async def cleanup() -> None:
            if seeded_user_id is not None or reader_creation_attempted:
                async with engine.begin() as connection:
                    if seeded_user_id is not None:
                        await connection.execute(
                            delete(User).where(User.id == seeded_user_id)
                        )
                    if reader_creation_attempted:
                        await _drop_reader_role_if_present(connection)

        await _finalize_gate(cleanup, engine.dispose, primary_error)


def main() -> int:
    os.environ["ENVIRONMENT"] = "test"
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    try:
        raw_url = os.environ["DATABASE_URL"]
        image_id = _validated_image_id(os.environ["MIGPASS_BACKEND_IMAGE_ID"])
        admin_url = _validated_database_url(raw_url)
        asyncio.run(_run_gate(admin_url, image_id))
    except Exception as exc:
        # Database driver errors may contain connection details; keep diagnostics
        # limited to the exception type and never print the URL or row values.
        if isinstance(exc, GateFailure):
            detail = f": {exc}"
        elif isinstance(exc, ModuleNotFoundError):
            detail = f", missing_module={exc.name}"
        else:
            detail = ""
        print(
            f"migrate-passwords image gate failed ({type(exc).__name__}{detail})",
            file=sys.stderr,
        )
        return 1

    print("migrate-passwords passed in the immutable backend image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
