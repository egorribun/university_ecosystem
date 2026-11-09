"""Failure-path ownership checks for the borrowed-session PostgreSQL fixture."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.integration import test_aud363_454_borrowed_session_postgres as proof

_URL = "postgresql+asyncpg://audit_ws_reader@127.0.0.1:15432/audit_ws_borrowed"
_ROLE = ("audit_ws_borrowed", "audit_ws_reader", False, False)


class _Connection:
    def __init__(self, *, role=_ROLE, fail_at: str | None = None) -> None:
        self.role = role
        self.fail_at = fail_at
        self.statements: list[str] = []

    async def execute(self, statement, *_args):
        sql = str(statement)
        self.statements.append(sql)
        if self.fail_at is not None and sql.startswith(self.fail_at):
            raise RuntimeError("injected database failure")
        if sql.startswith("SELECT current_database()"):
            return SimpleNamespace(one=lambda: self.role)
        return None


class _Engine:
    def __init__(self, connection: _Connection, *, fail_commit: bool = False) -> None:
        self.connection = connection
        self.fail_commit = fail_commit
        self.disposed = False

    @asynccontextmanager
    async def begin(self):
        yield self.connection
        if self.fail_commit:
            raise RuntimeError("injected commit failure")

    async def dispose(self) -> None:
        self.disposed = True


def _configure(monkeypatch, bootstrap: _Engine, engine: _Engine | None = None) -> Mock:
    monkeypatch.setenv("AUD363_WS_DISPOSABLE_PG_URL", _URL)
    create = Mock(
        side_effect=[bootstrap, engine] if engine is not None else [bootstrap]
    )
    monkeypatch.setattr(proof, "create_async_engine", create)
    return create


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["identity", "create", "commit"])
async def test_unowned_schema_is_never_dropped_after_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    connection = _Connection(
        role=("other", *_ROLE[1:]) if failure == "identity" else _ROLE,
        fail_at="CREATE SCHEMA" if failure == "create" else None,
    )
    bootstrap = _Engine(connection, fail_commit=failure == "commit")
    create = _configure(monkeypatch, bootstrap)
    fixture = proof.owned_postgres.__wrapped__()

    expected_failure = pytest.fail.Exception if failure == "identity" else RuntimeError
    with pytest.raises(expected_failure):
        await anext(fixture)

    assert not any(sql.startswith("DROP SCHEMA") for sql in connection.statements)
    assert bootstrap.disposed
    create.assert_called_once()


@pytest.mark.asyncio
async def test_created_schema_is_dropped_after_later_setup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _Engine(_Connection())
    engine = _Engine(_Connection(fail_at="CREATE TABLE"))
    _configure(monkeypatch, bootstrap, engine)
    fixture = proof.owned_postgres.__wrapped__()

    with pytest.raises(RuntimeError, match="injected database failure"):
        await anext(fixture)

    created = next(
        sql
        for sql in bootstrap.connection.statements
        if sql.startswith("CREATE SCHEMA")
    )
    drops = [
        sql for sql in bootstrap.connection.statements if sql.startswith("DROP SCHEMA")
    ]
    assert drops == [f"DROP SCHEMA {created.removeprefix('CREATE SCHEMA ')} CASCADE"]
    assert engine.disposed
    assert bootstrap.disposed


@pytest.mark.asyncio
async def test_created_schema_is_dropped_after_successful_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _Engine(_Connection())
    engine = _Engine(_Connection())
    _configure(monkeypatch, bootstrap, engine)
    monkeypatch.setattr(proof, "async_sessionmaker", Mock())
    fixture = proof.owned_postgres.__wrapped__()

    owned = await anext(fixture)
    assert owned.engine is engine
    assert not any(
        sql.startswith("DROP SCHEMA") for sql in bootstrap.connection.statements
    )
    await fixture.aclose()

    created = next(
        sql
        for sql in bootstrap.connection.statements
        if sql.startswith("CREATE SCHEMA")
    )
    drops = [
        sql for sql in bootstrap.connection.statements if sql.startswith("DROP SCHEMA")
    ]
    assert drops == [f"DROP SCHEMA {created.removeprefix('CREATE SCHEMA ')} CASCADE"]
    assert engine.disposed
    assert bootstrap.disposed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        ("other_db", "audit_ws_reader", False, False),
        ("audit_ws_borrowed", "other_user", False, False),
        ("audit_ws_borrowed", "audit_ws_reader", True, False),
        ("audit_ws_borrowed", "audit_ws_reader", False, True),
    ],
)
async def test_server_identity_or_privilege_mismatch_never_creates_or_drops_schema(
    monkeypatch: pytest.MonkeyPatch, role: tuple[str, str, bool, bool]
) -> None:
    bootstrap = _Engine(_Connection(role=role))
    _configure(monkeypatch, bootstrap)
    fixture = proof.owned_postgres.__wrapped__()

    with pytest.raises(pytest.fail.Exception, match="server identity"):
        await anext(fixture)

    assert len(bootstrap.connection.statements) == 1
    assert bootstrap.connection.statements[0].startswith("SELECT current_database()")
    assert bootstrap.disposed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://audit_ws_reader@localhost:15432/audit_ws_borrowed",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:5432/audit_ws_borrowed",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1/audit_ws_borrowed",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:0/audit_ws_borrowed",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:65536/audit_ws_borrowed",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:15432/audit_ws_borrowed?host=example.org",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:15432/audit_ws_borrowed?port=5432",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:15432/audit_ws_borrowed?user=postgres",
        "postgresql+asyncpg://audit_ws_reader@127.0.0.1:15432/postgres",
        "postgresql+asyncpg://postgres@127.0.0.1:15432/audit_ws_borrowed",
        "postgresql://audit_ws_reader@127.0.0.1:15432/audit_ws_borrowed",
    ],
)
async def test_identity_guards_reject_unowned_target_before_connecting(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    create = Mock(side_effect=AssertionError("unowned target reached engine creation"))
    monkeypatch.setattr(proof, "create_async_engine", create)
    monkeypatch.setenv("AUD363_WS_DISPOSABLE_PG_URL", url)
    fixture = proof.owned_postgres.__wrapped__()

    with pytest.raises(pytest.fail.Exception, match="identity does not match"):
        await anext(fixture)

    create.assert_not_called()
