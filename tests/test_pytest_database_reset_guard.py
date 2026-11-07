from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

from tests.fixtures.database import database as fixture_database


class UnexpectedConnection(AssertionError):
    pass


class SyntheticEngine:
    def __init__(self, url: str) -> None:
        self.url = make_url(url)
        self.begin_calls = 0

    def begin(self) -> None:
        self.begin_calls += 1
        raise UnexpectedConnection("database connection attempted")


@pytest.fixture
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL_FILE",
        "UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL",
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET",
        "PYTEST_XDIST_WORKER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE", "explicit")


def _advance_prepare() -> None:
    async def advance() -> None:
        generator = fixture_database.prepare_database.__wrapped__()
        try:
            await generator.__anext__()
        finally:
            await generator.aclose()

    asyncio.run(advance())


def test_database_url_file_takes_precedence_and_cannot_redirect_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    from app.core.config import Settings

    selected_url = "sqlite+aiosqlite:///:memory:"
    actual_url = f"sqlite+aiosqlite:///{(tmp_path / 'private.db').as_posix()}"
    url_file = tmp_path / "database_url.txt"
    url_file.write_text(actual_url, encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", selected_url)
    monkeypatch.setenv("DATABASE_URL_FILE", str(url_file))
    settings = Settings(database_url=selected_url)
    assert settings.database_url == actual_url
    engine = SyntheticEngine(settings.database_url)
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)

    with pytest.raises(pytest.UsageError):
        _advance_prepare()
    assert engine.begin_calls == 0


def test_xdist_refuses_different_effective_engine_before_admin_connect(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    import asyncpg

    selected_url = "postgresql+asyncpg://test@db.invalid:5432/test_suite_gw0"
    engine = SyntheticEngine("postgresql+asyncpg://test@db.invalid:5432/production")
    monkeypatch.setenv("DATABASE_URL", selected_url)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)

    async def unexpected_connect(*args: object, **kwargs: object) -> None:
        raise UnexpectedConnection("admin connection attempted")

    monkeypatch.setattr(asyncpg, "connect", unexpected_connect)
    with pytest.raises(pytest.UsageError):
        _advance_prepare()
    assert engine.begin_calls == 0


def test_cleanup_refuses_replaced_engine_before_connection(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = SyntheticEngine("sqlite+aiosqlite:///private.db")
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)

    with pytest.raises(pytest.UsageError):
        asyncio.run(fixture_database._clear_mapped_database_rows(is_postgresql=False))
    assert engine.begin_calls == 0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("database", "production"),
        ("dbname", "production"),
        ("host", "other.invalid"),
        ("port", "5433"),
        ("user", "another"),
        ("password", "other"),
        ("dsn", "postgresql://other.invalid/production"),
        ("service", "other"),
        ("servicefile", "other"),
        ("unrecognized", "value"),
    ],
)
def test_postgres_query_aliases_are_refused_before_connection(
    key: str, value: str, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    url = (
        make_url("postgresql+asyncpg://test@db.invalid:5432/test_suite")
        .set(query={key: value})
        .render_as_string(hide_password=False)
    )
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(url)


def test_sqlite_memory_uri_alias_is_not_automatically_authorized(
    isolated_environment: None,
) -> None:
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(
            "sqlite+aiosqlite:///:memory:?mode=rwc&uri=true"
        )


def test_known_explicit_targets_are_still_authorized(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    assert (
        fixture_database._require_safe_database_reset(
            "postgresql+asyncpg://test@localhost:5432/test"
        )
    ) is None
    assert (
        fixture_database._require_safe_database_reset(
            "sqlite+aiosqlite:///custom-test.db?timeout=15&uri=false"
        )
    ) is None
    assert (
        fixture_database._require_safe_database_reset("sqlite+aiosqlite:///:memory:")
    ) is None


@pytest.mark.parametrize("key", ["database", "host", "port", "user"])
def test_xdist_rejects_postgres_query_alias_before_admin_connect(
    key: str, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    import asyncpg

    url = (
        make_url("postgresql+asyncpg://test@db.invalid:5432/test_suite_gw0")
        .set(query={key: "other"})
        .render_as_string(hide_password=False)
    )
    engine = SyntheticEngine(url)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)

    async def unexpected_connect(*args: object, **kwargs: object) -> None:
        raise UnexpectedConnection("admin connection attempted")

    monkeypatch.setattr(asyncpg, "connect", unexpected_connect)
    with pytest.raises(pytest.UsageError):
        _advance_prepare()
    assert engine.begin_calls == 0


def test_original_external_url_must_also_be_unambiguous(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    url = "postgresql+asyncpg://test@db.invalid:5432/test_suite_gw0"
    monkeypatch.setenv(
        "UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL",
        "postgresql+asyncpg://test@db.invalid:5432/test_suite?database=production",
    )
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE", "harness-postgres")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(url)


@pytest.mark.parametrize(
    "component", ["host", "port", "username", "password", "database", "query"]
)
def test_engine_identity_compares_each_component(
    component: str, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    selected = make_url("postgresql+asyncpg://test@db.invalid:5432/test_suite")
    replacements = {
        "host": "other.invalid",
        "port": 5433,
        "username": "other",
        "password": uuid4().hex,
        "database": "other",
        "query": {"application_name": "other"},
    }
    engine = SyntheticEngine(
        selected.set(**{component: replacements[component]}).render_as_string(
            hide_password=False
        )
    )
    monkeypatch.setenv("DATABASE_URL", selected.render_as_string(hide_password=False))
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    with pytest.raises(pytest.UsageError):
        fixture_database._authorized_reset_engine()
    assert engine.begin_calls == 0


def test_owned_sqlite_and_hosted_postgres_targets_are_accepted_without_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    sqlite_url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    sqlite_engine = SyntheticEngine(sqlite_url)
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE", "harness-sqlite")
    monkeypatch.setattr(fixture_database.database, "_engine", sqlite_engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    assert fixture_database._authorized_reset_engine() is sqlite_engine
    assert sqlite_engine.begin_calls == 0

    external = "postgresql+asyncpg://test@localhost:5432/test"
    worker = "postgresql+asyncpg://test@localhost:5432/test_gw0_abcdef1234"
    postgres_engine = SyntheticEngine(worker)
    monkeypatch.setenv("DATABASE_URL", worker)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL", external)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE", "harness-postgres")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database.database, "_engine", postgres_engine)
    assert fixture_database._authorized_reset_engine() is postgres_engine
    assert postgres_engine.begin_calls == 0


def test_equivalent_parsed_urls_do_not_require_exact_spelling(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    selected = "postgresql+asyncpg://t%65st@localhost:5432/test"
    engine = SyntheticEngine("postgresql+asyncpg://test@localhost:5432/test")
    monkeypatch.setenv("DATABASE_URL", selected)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    assert fixture_database._authorized_reset_engine() is engine


def test_cleanup_rejects_dialect_mismatch_without_opening_engine(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    url = "sqlite+aiosqlite:///:memory:"
    engine = SyntheticEngine(url)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    with pytest.raises(pytest.UsageError):
        asyncio.run(fixture_database._clear_mapped_database_rows(is_postgresql=True))
    assert engine.begin_calls == 0


def test_file_override_cannot_connect_with_a_real_sqlalchemy_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    from sqlalchemy import event

    from app.core import database
    from app.core.config import Settings

    selected = "sqlite+aiosqlite:///:memory:"
    actual = f"sqlite+aiosqlite:///{(tmp_path / 'private.db').as_posix()}"
    url_file = tmp_path / "database_url.txt"
    url_file.write_text(actual, encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", selected)
    monkeypatch.setenv("DATABASE_URL_FILE", str(url_file))
    settings = Settings(database_url=selected, database_read_replica_url=None)
    engine, _factory, replica = database.create_session_factory(settings)
    assert replica is None
    attempts = []

    def reject_connect(*args: object, **kwargs: object) -> None:
        attempts.append(1)
        raise UnexpectedConnection("real driver connection blocked")

    event.listen(engine.sync_engine, "do_connect", reject_connect)
    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    try:
        with pytest.raises(pytest.UsageError):
            _advance_prepare()
    finally:
        asyncio.run(engine.dispose())
    assert attempts == []


@pytest.mark.parametrize("replace", [False, True])
def test_postgres_worker_teardown_rechecks_engine_before_admin_connect(
    replace: bool, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    import asyncpg
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

    external = "postgresql+asyncpg://test@localhost:5432/test"
    worker = "postgresql+asyncpg://test@localhost:5432/test_gw0_abcdef1234"
    monkeypatch.setenv("DATABASE_URL", worker)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL", external)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE", "harness-postgres")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    monkeypatch.setattr(fixture_database.database, "_read_replica_engine", None)
    admin_connects = []

    class FakeResult:
        def scalar(self) -> None:
            return None

    class FakeConnection:
        async def __aenter__(self) -> FakeConnection:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def exec_driver_sql(self, statement: str) -> None:
            return None

        async def run_sync(self, function: object) -> None:
            return None

        async def execute(self, *args: object, **kwargs: object) -> FakeResult:
            return FakeResult()

        async def fetchval(self, *args: object) -> bool:
            return False

        async def close(self) -> None:
            return None

    class FakeEngine:
        def __init__(self, url: str) -> None:
            self.url = make_url(url)
            self.dialect = PGDialect_asyncpg()

        def begin(self) -> FakeConnection:
            return FakeConnection()

        def execution_options(self, **kwargs: object) -> FakeEngine:
            return self

        def connect(self) -> FakeConnection:
            return FakeConnection()

        async def dispose(self) -> None:
            return None

    async def connect(*args: object, **kwargs: object) -> FakeConnection:
        admin_connects.append(args)
        return FakeConnection()

    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(fixture_database.database, "_engine", FakeEngine(worker))

    async def exercise() -> None:
        generator = fixture_database.prepare_database.__wrapped__()
        await generator.__anext__()
        assert len(admin_connects) == 1
        if replace:
            monkeypatch.setattr(
                fixture_database.database,
                "_engine",
                FakeEngine("postgresql+asyncpg://test@localhost:5432/production"),
            )
            with pytest.raises(pytest.UsageError):
                await generator.aclose()
            assert len(admin_connects) == 1
        else:
            await generator.aclose()
            assert len(admin_connects) == 2

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "url",
    [
        "not a database URL",
        "mysql+aiomysql://test@db.invalid:3306/test_suite",
        "sqlite+aiosqlite://user@db.invalid/test.db",
        "sqlite+aiosqlite:///test.db?mode=ro",
        "postgresql+asyncpg://test@db.invalid/test_suite",
        "postgresql+asyncpg://db.invalid:5432/test_suite",
    ],
)
def test_malformed_or_ambiguous_targets_are_refused(
    url: str, isolated_environment: None
) -> None:
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(url)


def test_invalid_selected_url_is_refused_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "private-invalid-value")
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    with pytest.raises(pytest.UsageError) as error:
        fixture_database._authorized_reset_engine()
    assert "private-invalid-value" not in str(error.value)


def test_explicit_reset_still_requires_opt_in_and_valid_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    test_url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL", test_url)
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(test_url)
    monkeypatch.delenv("UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL")
    private_path = tmp_path / "private.db"
    private_url = f"sqlite+aiosqlite:///{private_path.as_posix()}"
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(private_url)
    sentinel = Path(f"{private_path}.pytest-owned")
    sentinel.write_text("university-ecosystem-pytest\n", encoding="utf-8")
    fixture_database._require_safe_database_reset(private_url)


@pytest.mark.parametrize("replace", [False, True])
def test_owned_sqlite_teardown_rechecks_engine_before_drop(
    replace: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_environment: None,
) -> None:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE", "harness-sqlite")
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    monkeypatch.setattr(fixture_database.database, "_read_replica_engine", None)
    operations = []

    class FakeConnection:
        async def __aenter__(self) -> FakeConnection:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def exec_driver_sql(self, statement: str) -> None:
            return None

        async def run_sync(self, function: object) -> None:
            operations.append(function)

    class FakeEngine:
        def __init__(self, target: str) -> None:
            self.url = make_url(target)

        def begin(self) -> FakeConnection:
            return FakeConnection()

        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(fixture_database.database, "_engine", FakeEngine(url))

    async def exercise() -> None:
        generator = fixture_database.prepare_database.__wrapped__()
        await generator.__anext__()
        before = len(operations)
        if replace:
            other = f"sqlite+aiosqlite:///{(tmp_path / 'private.db').as_posix()}"
            monkeypatch.setattr(fixture_database.database, "_engine", FakeEngine(other))
            with pytest.raises(pytest.UsageError):
                await generator.__anext__()
            assert len(operations) == before
        else:
            with pytest.raises(StopAsyncIteration):
                await generator.__anext__()
            assert len(operations) == before + 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("backend", "has_tables"),
    [("sqlite", True), ("postgresql", False), ("postgresql", True)],
)
def test_authorized_cleanup_uses_the_checked_engine(
    backend: str,
    has_tables: bool,
    monkeypatch: pytest.MonkeyPatch,
    isolated_environment: None,
) -> None:
    from tests.fixtures.database.database import Base

    url = (
        "sqlite+aiosqlite:///:memory:"
        if backend == "sqlite"
        else "postgresql+asyncpg://test@localhost:5432/test"
    )
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    calls = []

    class FakeResult:
        def all(self) -> list[tuple[str]]:
            return [(Base.metadata.sorted_tables[0].name,)] if has_tables else []

    class FakeConnection:
        async def __aenter__(self) -> FakeConnection:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def exec_driver_sql(self, sql: str) -> FakeResult:
            calls.append(sql)
            return FakeResult()

        async def execute(self, statement: object) -> None:
            calls.append("delete")

    class FakeEngine:
        def __init__(self) -> None:
            self.url = make_url(url)

        def begin(self) -> FakeConnection:
            return FakeConnection()

    monkeypatch.setattr(fixture_database.database, "_engine", FakeEngine())
    asyncio.run(
        fixture_database._clear_mapped_database_rows(
            is_postgresql=backend == "postgresql"
        )
    )
    if backend == "sqlite":
        assert calls[0] == "PRAGMA foreign_keys=OFF"
        assert calls[-1] == "PRAGMA foreign_keys=ON"
        assert "delete" in calls
    else:
        assert calls[0].startswith("SELECT tablename")
        assert any(sql.startswith("TRUNCATE TABLE ") for sql in calls) == has_tables


def test_matching_file_url_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    from app.core.config import Settings

    url = "sqlite+aiosqlite:///:memory:"
    url_file = tmp_path / "database_url.txt"
    url_file.write_text(url, encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL_FILE", str(url_file))
    engine = SyntheticEngine(Settings(database_url=url).database_url)
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    assert fixture_database._authorized_reset_engine() is engine
    assert engine.begin_calls == 0


def test_missing_or_changed_expected_engine_is_refused(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    url = "sqlite+aiosqlite:///:memory:"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    monkeypatch.setattr(fixture_database.database, "_engine", None)
    with pytest.raises(pytest.UsageError):
        fixture_database._authorized_reset_engine()
    engine = SyntheticEngine(url)
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    with pytest.raises(pytest.UsageError):
        fixture_database._authorized_reset_engine("sqlite+aiosqlite:///private.db")
    assert engine.begin_calls == 0


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"ssl": "verify-full"},
        {"prepared_statement_cache_size": "0"},
        {"ssl": "require", "prepared_statement_cache_size": "0"},
    ],
)
def test_worker_maintenance_uses_checked_dialect_connection_identity(
    query: dict[str, str], monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    import asyncpg
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

    parsed = make_url(
        "postgresql+asyncpg://test@127.0.0.%31:5432/test_suite%2Fgw0"
    ).set(username="test@user", password=uuid4().hex, query=query)
    url = parsed.render_as_string(hide_password=False)
    dialect = PGDialect_asyncpg()
    positional, options = dialect.create_connect_args(parsed)
    assert positional == []
    expected = dict(options)
    expected.pop("prepared_statement_cache_size", None)
    expected["database"] = "postgres"
    engine = SyntheticEngine(url)
    engine.dialect = dialect
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database.database, "_engine", engine)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    received = []
    requested_database = []

    class FakeAdminConnection:
        async def fetchval(self, statement: str, database_name: str) -> None:
            requested_database.append(database_name)
            raise UnexpectedConnection("stop before DDL")

        async def close(self) -> None:
            return None

    async def connect(*args: object, **kwargs: object) -> FakeAdminConnection:
        received.append((args, kwargs))
        return FakeAdminConnection()

    monkeypatch.setattr(asyncpg, "connect", connect)
    with pytest.raises(UnexpectedConnection, match="stop before DDL"):
        _advance_prepare()
    assert received == [((), expected)]
    assert requested_database == [options["database"]]
    assert received[0][1]["host"] == "127.0.0.%31"
    assert engine.begin_calls == 0


def test_cleanup_refuses_changed_session_engine_and_environment(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    from types import SimpleNamespace

    original_url = "sqlite+aiosqlite:///:memory:"
    new_url = "sqlite+aiosqlite:///test_other.db"
    monkeypatch.setenv("DATABASE_URL", original_url)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    original_engine = SyntheticEngine(original_url)
    original_engine.dialect = SimpleNamespace(name="sqlite")
    monkeypatch.setattr(fixture_database.database, "_engine", original_engine)
    request = SimpleNamespace(node=SimpleNamespace())

    async def exercise() -> None:
        generator = fixture_database.clean_database.__wrapped__(
            prepare_database=(make_url(original_url), original_engine), request=request
        )
        await generator.__anext__()
        changed_engine = SyntheticEngine(new_url)
        changed_engine.dialect = SimpleNamespace(name="sqlite")
        monkeypatch.setenv("DATABASE_URL", new_url)
        monkeypatch.setattr(fixture_database.database, "_engine", changed_engine)
        with pytest.raises(pytest.UsageError):
            await generator.__anext__()
        assert changed_engine.begin_calls == 0

    asyncio.run(exercise())


def test_cleanup_refuses_replacement_engine_even_with_same_url(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    from types import SimpleNamespace

    url = "sqlite+aiosqlite:///:memory:"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    original = SyntheticEngine(url)
    original.dialect = SimpleNamespace(name="sqlite")
    monkeypatch.setattr(fixture_database.database, "_engine", original)
    request = SimpleNamespace(node=SimpleNamespace())

    async def exercise() -> None:
        generator = fixture_database.clean_database.__wrapped__(
            prepare_database=(make_url(url), original), request=request
        )
        await generator.__anext__()
        replacement = SyntheticEngine(url)
        replacement.dialect = SimpleNamespace(name="sqlite")
        monkeypatch.setattr(fixture_database.database, "_engine", replacement)
        with pytest.raises(pytest.UsageError):
            await generator.__anext__()
        assert replacement.begin_calls == 0

    asyncio.run(exercise())


def test_reset_authorization_precedes_engine_initialization(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    import sys

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    events = []
    original_profile = sys.getprofile()
    watched = {
        fixture_database._require_safe_database_reset.__code__: "reset",
        fixture_database.init_database.__code__: "init",
    }

    def profile(frame: object, event: str, arg: object) -> None:
        if event == "call" and frame.f_code in watched:
            events.append(watched[frame.f_code])
            raise AssertionError("blocked early database access")

    try:
        sys.setprofile(profile)
        with pytest.raises(AssertionError, match="blocked early database access"):
            _advance_prepare()
    finally:
        sys.setprofile(original_profile)
    assert events == ["reset"]


def test_unexpected_dialect_positional_arguments_are_rejected(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    class AmbiguousDialect:
        def create_connect_args(self, url: object) -> tuple[list[str], dict[str, str]]:
            return ["ambiguous"], {}

    engine = SyntheticEngine("postgresql+asyncpg://test@localhost:5432/test")
    engine.dialect = AmbiguousDialect()
    with pytest.raises(pytest.UsageError):
        fixture_database._maintenance_connect_kwargs(engine)


def test_repeated_postgres_query_keys_are_refused(isolated_environment: None) -> None:
    with pytest.raises(pytest.UsageError):
        fixture_database._require_safe_database_reset(
            "postgresql+asyncpg://test@localhost:5432/test?ssl=require&ssl=disable"
        )


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_explicit_session_preclean_uses_original_engine_and_url(
    backend: str, monkeypatch: pytest.MonkeyPatch, isolated_environment: None
) -> None:
    credential = uuid4().hex
    url = (
        "sqlite+aiosqlite:///test_named.db"
        if backend == "sqlite"
        else make_url("postgresql+asyncpg://test@localhost:5432/test_named")
        .set(password=credential)
        .render_as_string(hide_password=False)
    )
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setattr(fixture_database, "init_database", lambda: None)
    monkeypatch.setattr(fixture_database.database, "_read_replica_engine", None)
    statements = []

    class FakeResult:
        def scalar(self) -> None:
            return None

        def all(self) -> list[tuple[str]]:
            return []

    class FakeConnection:
        async def __aenter__(self) -> FakeConnection:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def exec_driver_sql(self, sql: str) -> FakeResult:
            statements.append(sql)
            return FakeResult()

        async def run_sync(self, function: object) -> None:
            return None

        async def execute(self, *args: object, **kwargs: object) -> FakeResult:
            return FakeResult()

    class FakeEngine:
        def __init__(self) -> None:
            self.url = make_url(url)

        def begin(self) -> FakeConnection:
            return FakeConnection()

        def execution_options(self, **kwargs: object) -> FakeEngine:
            return self

        def connect(self) -> FakeConnection:
            return FakeConnection()

        async def dispose(self) -> None:
            return None

    engine = FakeEngine()
    monkeypatch.setattr(fixture_database.database, "_engine", engine)

    async def exercise() -> None:
        generator = fixture_database.prepare_database.__wrapped__()
        bound_url, bound_engine = await generator.__anext__()
        assert bound_url == make_url(url)
        assert bound_engine is engine
        assert credential not in repr(bound_url)
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()

    asyncio.run(exercise())
    if backend == "sqlite":
        assert "PRAGMA foreign_keys=OFF" in statements
    else:
        assert any(sql.startswith("SELECT tablename") for sql in statements)
