"""Live PostgreSQL rendering of changed Alembic revisions for Squawk (AUD-208)."""

from __future__ import annotations

import os
import re
import runpy
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import psycopg
from sqlalchemy.engine import make_url

from scripts.quality import render_live_alembic_sql as renderer

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ROOT_MIGRATION = _PROJECT_ROOT / "alembic" / "versions" / "b05ae64aaeef_init.py"
_AUD180_MIGRATION = (
    _PROJECT_ROOT
    / "alembic"
    / "versions"
    / "202610120002_add_news_media_asset_ownership.py"
)
_GUARDED_MIGRATION = (
    _PROJECT_ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"
)
_LIVE_DATABASE = bool(os.getenv("RUN_INTEGRATION_TESTS"))
_UNREACHABLE_DATABASE_URL = (
    "postgresql+asyncpg://migration-gate@127.0.0.1:9/unreachable"
)


def test_ddl_recorder_preserves_leading_directives_and_lock_copy_order() -> None:
    recorder = renderer._DdlRecorder()
    recorder.active = True
    rename = (
        "-- The source heap remains locked while the replacement takes its name.\n"
        "-- squawk-ignore renaming-table\n"
        "ALTER TABLE public.events RENAME TO events_prepart_old"
    )

    recorder(
        None,
        None,
        "LOCK TABLE public.events IN ACCESS EXCLUSIVE MODE",
        None,
        None,
        False,
    )
    recorder(None, None, rename, None, None, False)
    recorder(
        None,
        None,
        "INSERT INTO public.events SELECT * FROM public.events_prepart_old",
        None,
        None,
        False,
    )

    assert recorder.statements == [
        "LOCK TABLE public.events IN ACCESS EXCLUSIVE MODE",
        rename,
        "INSERT INTO public.events SELECT * FROM public.events_prepart_old",
    ]


def test_ddl_recorder_keeps_parameterized_dml_as_a_non_ddl_comment() -> None:
    recorder = renderer._DdlRecorder()
    recorder.active = True
    statement = "DELETE FROM public.events_default WHERE occurred_at >= %(start)s"
    context = SimpleNamespace(compiled=SimpleNamespace(binds={"start": object()}))

    recorder(None, None, statement, {"start": "secret-value"}, context, False)

    assert len(recorder.statements) == 1
    assert "non-DDL observation only" in recorder.statements[0]
    assert (
        "-- DELETE FROM public.events_default WHERE occurred_at >= %(start)s"
        in (recorder.statements[0])
    )
    assert "secret-value" not in recorder.statements[0]


def test_ddl_recorder_does_not_duplicate_transaction_events_as_cursor_sql() -> None:
    recorder = renderer._DdlRecorder()
    recorder.active = True

    recorder._on_begin(None)
    recorder(None, None, "BEGIN", None, None, False)

    assert recorder.statements == [
        "-- observed SQLAlchemy begin event; transaction-event representation, "
        "not cursor text\nBEGIN"
    ]


class _FakeAdminConnection:
    def __init__(self, statements: list[str]) -> None:
        self.statements = statements

    def __enter__(self) -> _FakeAdminConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def exec_driver_sql(self, statement: str) -> _ScratchRows | None:
        self.statements.append(statement)


class _FakeAdminEngine:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.disposed = False

    def connect(self) -> _FakeAdminConnection:
        return _FakeAdminConnection(self.statements)

    def dispose(self) -> None:
        self.disposed = True


def _patch_renderer_runtime(
    monkeypatch: pytest.MonkeyPatch,
    fake_upgrade: Callable[[object, str], None],
) -> tuple[_FakeAdminEngine, list[renderer._DdlRecorder]]:
    admin = _ScratchTransport()
    _install_scratch_engines(monkeypatch, admin)
    recorders: list[renderer._DdlRecorder] = []
    recorder_type = renderer._DdlRecorder

    def new_recorder() -> renderer._DdlRecorder:
        recorder = recorder_type()
        recorders.append(recorder)
        return recorder

    monkeypatch.setattr(renderer, "_connect_admin", lambda _url: admin)
    monkeypatch.setattr(
        renderer,
        "read_revision_metadata",
        lambda _migration: ("target", "parent"),
    )
    monkeypatch.setattr(renderer, "_alembic_config", lambda: object())
    monkeypatch.setattr(renderer, "_DdlRecorder", new_recorder)
    monkeypatch.setattr(renderer.command, "upgrade", fake_upgrade)
    return admin, recorders


def _assert_recorder_listeners_removed(recorder: renderer._DdlRecorder) -> None:
    for event_name, listener in recorder.event_listeners():
        assert not renderer.event.contains(renderer.Engine, event_name, listener)


def test_live_renderer_records_transaction_events_and_removes_listeners_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://renderer@localhost/university"
    monkeypatch.setenv("DATABASE_URL", database_url)

    def fake_upgrade(_config: object, destination: str) -> None:
        if destination == "parent":
            return
        engine = sa.create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE rendered (id INTEGER)")
        finally:
            engine.dispose()

    admin, recorders = _patch_renderer_runtime(monkeypatch, fake_upgrade)

    sql = renderer.render_revision_sql(Path("target.py"), database_url)

    assert sql.count("BEGIN;") == 1
    assert sql.count("COMMIT;") == 1
    assert "CREATE TABLE rendered (id INTEGER);" in sql
    assert admin.disposed
    assert admin.statements[0].startswith('CREATE DATABASE "alembic_squawk_')
    assert admin.statements[1].startswith('DROP DATABASE IF EXISTS "alembic_squawk_')
    assert os.environ["DATABASE_URL"] == database_url
    _assert_recorder_listeners_removed(recorders[0])


def test_live_renderer_records_rollback_and_removes_listeners_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://renderer@localhost/university"
    monkeypatch.setenv("DATABASE_URL", database_url)

    def fake_upgrade(_config: object, destination: str) -> None:
        if destination == "parent":
            return
        engine = sa.create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE rendered (id INTEGER)")
                raise RuntimeError("simulated migration failure")
        finally:
            engine.dispose()

    admin, recorders = _patch_renderer_runtime(monkeypatch, fake_upgrade)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        renderer.render_revision_sql(Path("target.py"), database_url)

    statements = recorders[0].statements
    assert sum(statement.endswith("\nBEGIN") for statement in statements) == 1
    assert sum(statement.endswith("\nROLLBACK") for statement in statements) == 1
    assert not any(statement.endswith("\nCOMMIT") for statement in statements)
    assert admin.disposed
    assert os.environ["DATABASE_URL"] == database_url
    _assert_recorder_listeners_removed(recorders[0])


def test_main_requires_a_migration_and_an_output_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert renderer.main(["only-one-argument"]) == 2
    assert "usage: render_live_alembic_sql.py" in capsys.readouterr().err


def test_main_requires_a_postgresql_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

    assert renderer.main([str(_AUD180_MIGRATION), str(tmp_path / "out.sql")]) == 2
    assert "DATABASE_URL must target PostgreSQL" in capsys.readouterr().err


def test_main_rejects_migrations_without_literal_revision_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)
    migration = tmp_path / "dynamic.py"
    migration.write_text("revision = make_revision()\ndown_revision = None\n")

    assert renderer.main([str(migration), str(tmp_path / "out.sql")]) == 2
    assert "revision must be a string literal" in capsys.readouterr().err


def test_admin_connection_is_retried_then_reported_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)
    monkeypatch.setattr(renderer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(renderer, "_ADMIN_CONNECT_ATTEMPTS", 2)

    assert renderer.main([str(_AUD180_MIGRATION), str(tmp_path / "out.sql")]) == 2
    assert "PostgreSQL admin connection failed" in capsys.readouterr().err
    assert not (tmp_path / "out.sql").exists()


def _admin_engine_for(database_url: str) -> sa.Engine:
    return sa.create_engine(
        make_url(database_url).set(drivername="postgresql+psycopg"),
        isolation_level="AUTOCOMMIT",
    )


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_captures_the_aud180_ddl_with_its_timeouts(
    tmp_path: Path,
) -> None:
    sql = renderer.render_revision_sql(_AUD180_MIGRATION, os.environ["DATABASE_URL"])

    assert sql.startswith(
        "-- observed SQLAlchemy begin event; transaction-event representation, "
        "not cursor text\nBEGIN;\n"
    )
    lock_timeout_position = sql.index("SET LOCAL lock_timeout = '10s'")
    statement_timeout_position = sql.index("SET LOCAL statement_timeout = '60s'")
    first_ddl_position = sql.index("CREATE TABLE news_media_assets (")
    assert lock_timeout_position < statement_timeout_position < first_ddl_position
    assert "CREATE TABLE news_media_assets (" in sql
    assert (
        "CREATE INDEX ix_news_media_assets_owner_user_id "
        "ON news_media_assets (owner_user_id);"
    ) in sql


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_captures_inspector_guarded_branches_hidden_offline(
    tmp_path: Path,
) -> None:
    # The offline inspector reports no constraints, so the restore branch that
    # adds the shadow CHECK constraint is absent from offline --sql output.
    sql = renderer.render_revision_sql(_GUARDED_MIGRATION, os.environ["DATABASE_URL"])

    assert "ADD CONSTRAINT ck_groups_id_shadow_not_null" in sql
    assert "CREATE TEMP TABLE _groups_fk_restore" in sql


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_of_the_root_revision_needs_no_parent_upgrade() -> None:
    sql = renderer.render_revision_sql(_ROOT_MIGRATION, os.environ["DATABASE_URL"])

    assert "CREATE TABLE" in sql


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_drops_its_scratch_database_and_restores_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["DATABASE_URL"]
    fixed = uuid.UUID(hex="0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(renderer, "uuid", SimpleNamespace(uuid4=lambda: fixed))
    scratch = f"alembic_squawk_{fixed.hex[:16]}"

    renderer.render_revision_sql(_AUD180_MIGRATION, database_url)

    admin = _admin_engine_for(database_url)
    try:
        with admin.connect() as connection:
            remaining = connection.scalar(
                sa.text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                {"name": scratch},
            )
    finally:
        admin.dispose()
    assert remaining == 0
    assert os.environ["DATABASE_URL"] == database_url


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_restores_an_unset_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.delenv("DATABASE_URL")

    sql = renderer.render_revision_sql(_AUD180_MIGRATION, database_url)

    assert "CREATE TABLE news_media_assets (" in sql
    assert "DATABASE_URL" not in os.environ


def test_script_entry_point_exits_with_the_usage_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["render_live_alembic_sql.py"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(
            str(_PROJECT_ROOT / "scripts" / "quality" / "render_live_alembic_sql.py"),
            run_name="__main__",
        )

    assert exit_info.value.code == 2


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_main_writes_the_rendered_sql_to_the_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    output = tmp_path / "aud180.sql"

    assert renderer.main([str(_AUD180_MIGRATION), str(output)]) == 0
    assert "CREATE TABLE news_media_assets (" in output.read_text(encoding="utf-8")


class _ScratchRows:
    """Only the SQLAlchemy mapping-result methods used at this boundary."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> _ScratchRows:
        return self

    def all(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.rows]

    def one_or_none(self) -> dict[str, object] | None:
        if len(self.rows) > 1:
            raise sa.exc.MultipleResultsFound()
        return dict(self.rows[0]) if self.rows else None


class _ScratchConnection(_FakeAdminConnection):
    def __init__(self, admin: _ScratchTransport, scope: str) -> None:
        super().__init__(admin.statements)
        self.admin = admin
        self.scope = scope

    def exec_driver_sql(
        self, statement: str, parameters: dict[str, object] | None = None
    ) -> _ScratchRows | None:
        return self.admin.execute(self.scope, statement, parameters)

    def execute(
        self, statement: object, parameters: dict[str, object] | None = None
    ) -> _ScratchRows | None:
        return self.exec_driver_sql(str(statement), parameters)


class _ScratchDatabaseEngine:
    def __init__(self, admin: _ScratchTransport) -> None:
        self.admin = admin

    def connect(self) -> _ScratchConnection:
        return _ScratchConnection(self.admin, "scratch")

    def dispose(self) -> None:
        self.admin.scratch_disposed = True


class _ScratchTransport(_FakeAdminEngine):
    """Owned, quiescent CI-server transport; no ownership decision is mocked.

    Catalog rows describe the allowed template0 public/plpgsql baseline and
    non-system relation, routine, type, schema or extension contamination.
    They do not establish that a real PostgreSQL query covers those surfaces.
    """

    def __init__(self) -> None:
        super().__init__()
        self.mode = "success"
        self.canary = uuid.uuid4().hex
        self.scratch = ""
        self.created = False
        self.identity_reads = 0
        self.scratch_disposed = False
        self.probes: list[tuple[str, str, dict[str, object] | None]] = []
        self.engine_urls: list[sa.URL] = []
        self.timeline: list[str] = []
        self.upgrades: list[str] = []
        self.listeners: list[tuple[object, str, Callable[..., object]]] = []

    def failure(self, operation: str) -> sa.exc.OperationalError:
        return sa.exc.OperationalError(
            operation, {"private": self.canary}, RuntimeError(self.canary)
        )

    def connect(self) -> _ScratchConnection:
        if self.mode == "connect-error":
            raise self.failure("CONNECT")
        return _ScratchConnection(self, "admin")

    def execute(
        self, scope: str, statement: str, parameters: dict[str, object] | None
    ) -> _ScratchRows | None:
        normalized = statement.strip().upper()
        if normalized.startswith("CREATE DATABASE"):
            self.statements.append(statement)
            self.timeline.append("create")
            match = re.search(r'CREATE DATABASE "([^"]+)"', statement)
            assert match is not None, "the generated database name must be quoted"
            self.scratch = match.group(1)
            if self.mode in {"collision", "denied", "uncertain"}:
                self.created = self.mode == "uncertain"
                raise self.failure("CREATE DATABASE")
            self.created = True
            return None
        if normalized.startswith("DROP DATABASE"):
            self.statements.append(statement)
            self.timeline.append("drop")
            if self.mode == "cleanup-error":
                raise self.failure("DROP DATABASE")
            self.created = False
            return None

        self.probes.append((scope, statement, parameters))
        if "PG_DATABASE" in normalized:
            self.identity_reads += 1
            self.timeline.append("identity")
            if self.mode == "unconfirmed" or (
                self.identity_reads > 1 and self.mode == "missing"
            ):
                return _ScratchRows([])
            if self.identity_reads > 1 and self.mode == "identity-error":
                raise self.failure("SELECT pg_database")
            identity: dict[str, object] = {
                "oid": 79531,
                "datname": self.scratch,
                "datdba": 700,
                "current_role_oid": 700,
            }
            if self.mode == "foreign-owner":
                identity["datdba"] = 701
            if self.identity_reads > 1:
                if self.mode == "changed-oid":
                    identity["oid"] = 79532
                elif self.mode == "changed-name":
                    identity["datname"] = "not_the_owned_scratch"
                elif self.mode == "changed-owner":
                    identity["datdba"] = 701
            return _ScratchRows([identity])

        if "PG_NAMESPACE" in normalized:
            self.timeline.append("catalog")
            if self.mode == "catalog-error":
                raise self.failure("SELECT user catalogs")
            rows: list[dict[str, object]] = [
                {"kind": "schema", "nspname": None, "objname": "public"},
                {"kind": "extension", "nspname": "pg_catalog", "objname": "plpgsql"},
            ]
            if self.mode == "catalog-malformed":
                return _ScratchRows([{"kind": "relation"}])
            if self.mode.startswith("nonempty-"):
                rows.append(
                    {
                        "kind": self.mode.removeprefix("nonempty-"),
                        "nspname": (
                            None if self.mode == "nonempty-schema" else "public"
                        ),
                        "objname": "preexisting_object",
                    }
                )
            return _ScratchRows(rows)
        raise AssertionError("unexpected scratch transport query")


class _TrackedScratchEnvironment(dict[str, str]):
    def __init__(self, initial: dict[str, str]) -> None:
        super().__init__(initial)
        self.writes: list[str] = []

    def __setitem__(self, key: str, value: str) -> None:
        self.writes.append(key)
        super().__setitem__(key, value)

    def pop(self, key: str, default: str | None = None) -> str | None:
        self.writes.append(key)
        return super().pop(key, default)


def _install_scratch_engines(
    monkeypatch: pytest.MonkeyPatch, admin: _ScratchTransport
) -> None:
    create_engine = sa.create_engine

    def fake_create_engine(url: str | sa.URL, **kwargs: object) -> object:
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql":
            return create_engine(url, **kwargs)
        admin.engine_urls.append(parsed)
        if admin.scratch and parsed.database == admin.scratch:
            return _ScratchDatabaseEngine(admin)
        return admin

    monkeypatch.setattr(renderer.sa, "create_engine", fake_create_engine)


def _scratch_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str = "success"
) -> tuple[_ScratchTransport, _TrackedScratchEnvironment, Path]:
    admin = _ScratchTransport()
    admin.mode = mode
    environment = _TrackedScratchEnvironment(
        {"DATABASE_URL": "postgresql+psycopg://renderer@localhost/university"}
    )
    migration = tmp_path / "scratch_target.py"
    migration.write_text(
        "revision = 'target'\ndown_revision = 'parent'\n", encoding="utf-8"
    )
    _install_scratch_engines(monkeypatch, admin)
    monkeypatch.setattr(renderer, "os", SimpleNamespace(environ=environment))
    monkeypatch.setattr(renderer, "_ADMIN_CONNECT_ATTEMPTS", 2)
    monkeypatch.setattr(renderer.time, "sleep", lambda _seconds: None)
    listen = renderer.event.listen

    def record_listener(
        target: object, name: str, listener: Callable[..., object]
    ) -> None:
        admin.listeners.append((target, name, listener))
        listen(target, name, listener)

    def upgrade(_config: object, revision: str) -> None:
        admin.upgrades.append(revision)
        admin.timeline.append(f"upgrade:{revision}")

    monkeypatch.setattr(renderer.event, "listen", record_listener)
    monkeypatch.setattr(renderer.command, "upgrade", upgrade)
    return admin, environment, migration


def _scratch_failure(migration: Path, database_url: str) -> type[Exception] | None:
    try:
        renderer.render_revision_sql(migration, database_url)
    except Exception as error:
        return type(error)
    return None


def _assert_scratch_listeners_removed(admin: _ScratchTransport) -> None:
    for target, name, listener in admin.listeners:
        assert not renderer.event.contains(target, name, listener)


def test_scratch_requires_template0_and_empty_catalog_before_upgrade(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)

    assert renderer.render_revision_sql(migration, environment["DATABASE_URL"]) == ""

    assert re.search(
        r"\bTEMPLATE\s*(?:=\s*)?[\"']?template0\b", admin.statements[0], re.I
    )
    assert admin.timeline == [
        "create",
        "identity",
        "catalog",
        "upgrade:parent",
        "upgrade:target",
        "identity",
        "drop",
    ]
    assert admin.upgrades == ["parent", "target"]
    for url in admin.engine_urls:
        assert (url.host, url.port, url.username) == ("localhost", None, "renderer")
        assert url.database in {"university", admin.scratch}
    identity_probes = [
        probe for probe in admin.probes if "pg_database" in probe[1].lower()
    ]
    assert len(identity_probes) == 2
    for scope, statement, parameters in identity_probes:
        assert scope == "admin"
        assert "current_user" in statement.lower()
        assert parameters is not None and admin.scratch in parameters.values()
    catalog_probes = [
        probe for probe in admin.probes if "pg_database" not in probe[1].lower()
    ]
    assert len(catalog_probes) == 1
    scope, catalog_sql, _parameters = catalog_probes[0]
    assert scope == "scratch"
    for catalog in ("pg_class", "pg_proc", "pg_type", "pg_namespace", "pg_extension"):
        assert catalog in catalog_sql.lower()
    assert admin.statements[-1] == (
        f'DROP DATABASE IF EXISTS "{admin.scratch}" WITH (FORCE)'
    )
    assert environment == previous
    assert admin.disposed and admin.scratch_disposed
    _assert_scratch_listeners_removed(admin)


@pytest.mark.parametrize("mode", ["collision", "denied", "uncertain"])
def test_scratch_create_failure_never_drops_or_changes_execution_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path, mode)
    previous = dict(environment)

    failure = _scratch_failure(migration, environment["DATABASE_URL"])

    assert not any(sql.startswith("DROP DATABASE") for sql in admin.statements)
    assert admin.upgrades == []
    assert admin.listeners == []
    assert environment == previous
    assert environment.writes == []
    assert admin.identity_reads == 0
    assert admin.disposed
    assert failure is renderer.LiveRenderError


@pytest.mark.parametrize(
    "mode",
    [
        "nonempty-relation",
        "nonempty-routine",
        "nonempty-type",
        "nonempty-schema",
        "nonempty-extension",
        "catalog-error",
        "catalog-malformed",
    ],
)
def test_scratch_nonempty_or_unverifiable_catalog_blocks_upgrade(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path, mode)
    previous = dict(environment)

    failure = _scratch_failure(migration, environment["DATABASE_URL"])

    assert admin.upgrades == []
    assert admin.identity_reads == 2
    assert admin.timeline == ["create", "identity", "catalog", "identity", "drop"]
    assert environment == previous
    assert admin.disposed and admin.scratch_disposed
    assert failure is renderer.LiveRenderError
    _assert_scratch_listeners_removed(admin)


@pytest.mark.parametrize(
    "mode",
    [
        "changed-oid",
        "changed-name",
        "changed-owner",
        "missing",
        "identity-error",
        "unconfirmed",
        "foreign-owner",
    ],
)
def test_scratch_cleanup_requires_confirmed_created_database_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path, mode)
    previous = dict(environment)

    failure = _scratch_failure(migration, environment["DATABASE_URL"])

    assert not any(sql.startswith("DROP DATABASE") for sql in admin.statements)
    if mode in {"unconfirmed", "foreign-owner"}:
        assert admin.upgrades == []
        assert environment.writes == []
        assert admin.listeners == []
    else:
        assert admin.upgrades == ["parent", "target"]
        assert admin.scratch_disposed
    assert environment == previous
    assert admin.disposed
    assert failure is renderer.LiveRenderError
    _assert_scratch_listeners_removed(admin)


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("connect-error", "PostgreSQL admin connection failed"),
        ("denied", "PostgreSQL scratch creation failed"),
        ("catalog-error", "PostgreSQL scratch catalog check failed"),
        ("cleanup-error", "PostgreSQL scratch cleanup failed"),
    ],
)
def test_renderer_failure_diagnostics_are_opaque(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    reason: str,
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path, mode)
    database_url = make_url(environment["DATABASE_URL"]).set(password=admin.canary)
    environment["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    environment.writes.clear()
    previous = dict(environment)
    output = tmp_path / "rendered.sql"
    status: int | None = None
    escaped: str | None = None

    try:
        status = renderer.main([str(migration), str(output)])
    except Exception as error:
        escaped = type(error).__name__

    captured = capsys.readouterr()
    opaque = admin.canary not in captured.out + captured.err
    assert opaque, "transport diagnostics must not contain private context"
    assert escaped is None, "CLI must convert transport failures to bounded errors"
    assert status == 2
    assert captured.out == ""
    assert captured.err == f"error: {reason}\n"
    assert not output.exists()
    environment_restored = environment == previous
    assert environment_restored, "renderer must restore the prior environment"
    assert admin.disposed
    _assert_scratch_listeners_removed(admin)


def test_renderer_api_rejects_dbname_query_override_before_scratch_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)
    database_url = environment["DATABASE_URL"] + "?dbname=original"

    # The real dialect lets the query override a path-only scratch replacement.
    scratch_url = make_url(database_url).set(database="intended_scratch")
    _args, parameters = psycopg.dialect().create_connect_args(scratch_url)
    assert parameters["dbname"] == "original"

    failure = _scratch_failure(migration, database_url)

    assert admin.engine_urls == []
    assert admin.statements == []
    assert admin.probes == []
    assert admin.timeline == []
    assert admin.upgrades == []
    assert admin.listeners == []
    assert environment == previous
    assert environment.writes == []
    assert failure is renderer.LiveRenderError


def test_renderer_cli_rejects_dbname_query_override_before_scratch_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    environment["DATABASE_URL"] += "?dbname=original"
    environment.writes.clear()
    previous = dict(environment)
    output = tmp_path / "rendered.sql"

    status = renderer.main([str(migration), str(output)])

    captured = capsys.readouterr()
    assert admin.engine_urls == []
    assert admin.statements == []
    assert admin.probes == []
    assert admin.timeline == []
    assert admin.upgrades == []
    assert admin.listeners == []
    assert environment == previous
    assert environment.writes == []
    assert status == 2
    assert captured.out == ""
    assert captured.err == "error: PostgreSQL database URL cannot override dbname\n"
    assert not output.exists()
