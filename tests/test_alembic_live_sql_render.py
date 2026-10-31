"""Live PostgreSQL rendering of changed Alembic revisions for Squawk (AUD-208)."""

from __future__ import annotations

import os
import re
import runpy
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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


@pytest.mark.parametrize(
    "error_kind",
    [
        "migration",
        "driver",
        "live-render",
        "revision-metadata",
        "metadata-multiple-args",
        "metadata-nonstring-arg",
        "metadata-subclass",
    ],
)
def test_main_keeps_unexpected_migration_failure_context_private(
    error_kind: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI must fail without exposing migration or driver exception data."""
    marker = uuid.uuid4().hex
    output = tmp_path / "rendered.sql"
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)

    def fail_render(_migration: Path, _url: str) -> str:
        if error_kind == "driver":
            raise sa.exc.StatementError(
                "migration failed",
                "SELECT :private",
                {"private": marker},
                RuntimeError(marker),
            )
        if error_kind == "live-render":
            raise renderer.LiveRenderError(marker)
        if error_kind == "revision-metadata":
            raise renderer.RevisionMetadataError(marker)
        if error_kind == "metadata-multiple-args":
            raise renderer.RevisionMetadataError(marker, marker)
        if error_kind == "metadata-nonstring-arg":
            raise renderer.RevisionMetadataError({"private": marker})
        if error_kind == "metadata-subclass":

            class PrivateMetadataError(renderer.RevisionMetadataError):
                pass

            raise PrivateMetadataError(marker)
        raise RuntimeError(marker)

    monkeypatch.setattr(renderer, "render_revision_sql", fail_render)

    assert renderer.main([str(_AUD180_MIGRATION), str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: live migration rendering failed\n"
    assert marker not in captured.err
    assert not output.exists()


def test_main_keeps_output_write_failure_context_private(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = uuid.uuid4().hex
    output = tmp_path / "rendered.sql"
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)
    monkeypatch.setattr(
        renderer, "render_revision_sql", lambda _migration, _url: "SELECT 1"
    )

    def fail_write(_path: Path, *_args: object, **_kwargs: object) -> int:
        raise OSError(marker)

    monkeypatch.setattr(Path, "write_text", fail_write)

    assert renderer.main([str(_AUD180_MIGRATION), str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: live migration rendering failed\n"
    assert marker not in captured.err
    assert not output.exists()


def test_main_writes_successful_render_without_changing_sql(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "rendered.sql"
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)
    monkeypatch.setattr(
        renderer, "render_revision_sql", lambda _migration, _url: "SELECT 1;\n"
    )

    assert renderer.main([str(_AUD180_MIGRATION), str(output)]) == 0
    assert output.read_text(encoding="utf-8") == "SELECT 1;\n"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_main_does_not_swallow_process_interruptions(
    interruption: type[BaseException], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)

    def interrupt(_migration: Path, _url: str) -> str:
        raise interruption

    monkeypatch.setattr(renderer, "render_revision_sql", interrupt)
    with pytest.raises(interruption):
        renderer.main([str(_AUD180_MIGRATION), str(tmp_path / "out.sql")])


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


@pytest.fixture
def owned_renderer_admin() -> Iterator[sa.Engine]:
    """Use only the disposable PG17 service in the existing migration CI job."""
    database_url = os.environ.get("ALEMBIC_RENDERER_POSTGRES_DATABASE_URL", "")
    admitted = (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_JOB") == "db-migration-gate"
        and database_url == "postgresql+psycopg://test@127.0.0.1:5433/test_migration"
    )
    if not admitted:
        pytest.fail("renderer integration requires its owned CI service", pytrace=False)
    # Endpoint checks prevent accidental reuse; ownership comes from the job service.
    engine = sa.create_engine(
        database_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            version = int(
                connection.exec_driver_sql("SHOW server_version_num").scalar_one()
            )
            assert 170000 <= version < 180000
        yield engine
    finally:
        engine.dispose()


def _owned_renderer_database_identity(
    admin: sa.Engine, name: str
) -> tuple[int, str, int, int] | None:
    with admin.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT d.oid, d.datname, d.datdba, r.oid "
                "FROM pg_catalog.pg_database AS d "
                "JOIN pg_catalog.pg_roles AS r ON r.rolname = current_user "
                "WHERE d.datname = :name"
            ),
            {"name": name},
        ).one_or_none()
    if row is None:
        return None
    oid, datname, owner, current_role = row
    identity_valid = (
        all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in (oid, owner, current_role)
        )
        and datname == name
        and owner == current_role
    )
    if not identity_valid:
        raise AssertionError("owned renderer database identity is invalid")
    return oid, datname, owner, current_role


@contextmanager
def _owned_renderer_database(admin: sa.Engine, name: str) -> Iterator[sa.URL]:
    """Clean up only the exact database this fixture successfully created."""
    if re.fullmatch(r"alembic_squawk_[0-9a-f]{16}", name) is None:
        raise AssertionError("owned renderer database name is invalid")
    identity: tuple[int, str, int, int] | None = None
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE template0')
        identity = _owned_renderer_database_identity(admin, name)
        if identity is None:
            raise AssertionError("owned renderer database creation was not confirmed")
        yield admin.url.set(database=name)
    finally:
        if identity is not None:
            same_identity = _owned_renderer_database_identity(admin, name) == identity
            if not same_identity:
                raise AssertionError("owned renderer cleanup refused changed identity")
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["relation", "routine", "type", "schema", "extension"])
# AUD-208 @egorribun
@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS") != "1"
    or not os.environ.get("ALEMBIC_RENDERER_POSTGRES_DATABASE_URL"),
    reason="Requires the owned renderer PostgreSQL CI service",
)
def test_owned_renderer_catalog_rejects_user_objects(
    owned_renderer_admin: sa.Engine, kind: str
) -> None:
    name = f"alembic_squawk_{uuid.uuid4().hex[:16]}"
    with _owned_renderer_database(owned_renderer_admin, name) as scratch_url:
        # This is the production SQL probe, not a copied query or safety verdict.
        renderer._assert_empty_scratch_catalog(scratch_url)
        engine = sa.create_engine(scratch_url, connect_args={"connect_timeout": 5})
        try:
            with engine.begin() as connection:
                if kind == "relation":
                    connection.exec_driver_sql(
                        "CREATE TABLE public.renderer_admission_probe (id integer)"
                    )
                    connection.exec_driver_sql(
                        "INSERT INTO public.renderer_admission_probe VALUES (73)"
                    )
                    present = connection.exec_driver_sql(
                        "SELECT count(*) FROM public.renderer_admission_probe"
                    ).scalar_one()
                elif kind == "routine":
                    connection.exec_driver_sql(
                        "CREATE FUNCTION public.renderer_admission_probe() "
                        "RETURNS integer LANGUAGE sql AS 'SELECT 73'"
                    )
                    present = connection.exec_driver_sql(
                        "SELECT count(*) FROM pg_catalog.pg_proc AS p "
                        "JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace "
                        "WHERE p.proname = 'renderer_admission_probe' "
                        "AND n.nspname = 'public'"
                    ).scalar_one()
                elif kind == "type":
                    connection.exec_driver_sql(
                        "CREATE TYPE public.renderer_admission_probe AS ENUM ('owned')"
                    )
                    present = connection.exec_driver_sql(
                        "SELECT count(*) FROM pg_catalog.pg_type AS t "
                        "JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace "
                        "WHERE t.typname = 'renderer_admission_probe' "
                        "AND n.nspname = 'public' AND t.typtype = 'e'"
                    ).scalar_one()
                elif kind == "schema":
                    connection.exec_driver_sql("CREATE SCHEMA renderer_admission_probe")
                    present = connection.exec_driver_sql(
                        "SELECT count(*) FROM pg_catalog.pg_namespace "
                        "WHERE nspname = 'renderer_admission_probe'"
                    ).scalar_one()
                else:
                    available = connection.exec_driver_sql(
                        "SELECT count(*) "
                        "FROM pg_catalog.pg_available_extension_versions "
                        "WHERE name = 'vector' AND relocatable AND version = "
                        "(SELECT default_version "
                        "FROM pg_catalog.pg_available_extensions "
                        "WHERE name = 'vector')"
                    ).scalar_one()
                    assert available == 1, "the pinned PG17 image must provide vector"
                    # System-schema members must not hide an extra extension.
                    connection.exec_driver_sql(
                        "CREATE EXTENSION vector WITH SCHEMA pg_catalog"
                    )
                    present = connection.exec_driver_sql(
                        "SELECT count(*) FROM pg_catalog.pg_extension AS e "
                        "JOIN pg_catalog.pg_namespace AS n ON n.oid = e.extnamespace "
                        "WHERE e.extname = 'vector' AND n.nspname = 'pg_catalog'"
                    ).scalar_one()
                assert present == 1
            with pytest.raises(
                renderer.LiveRenderError,
                match=r"^PostgreSQL scratch catalog check failed$",
            ):
                renderer._assert_empty_scratch_catalog(scratch_url)
        finally:
            engine.dispose()


@pytest.mark.integration
# AUD-208 @egorribun
@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS") != "1"
    or not os.environ.get("ALEMBIC_RENDERER_POSTGRES_DATABASE_URL"),
    reason="Requires the owned renderer PostgreSQL CI service",
)
def test_owned_live_renderer_root_lifecycle_cleans_up(
    owned_renderer_admin: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed = uuid.uuid4()
    name = f"alembic_squawk_{fixed.hex[:16]}"
    assert _owned_renderer_database_identity(owned_renderer_admin, name) is None
    monkeypatch.setattr(renderer, "uuid", SimpleNamespace(uuid4=lambda: fixed))
    previous_url = os.environ.get("DATABASE_URL")
    try:
        sql = renderer.render_revision_sql(
            _ROOT_MIGRATION,
            owned_renderer_admin.url.render_as_string(hide_password=False),
        )
        assert "CREATE TABLE" in sql
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql
    finally:
        # No fallback DROP: unconfirmed leftovers belong to job-service teardown.
        assert _owned_renderer_database_identity(owned_renderer_admin, name) is None
        environment_restored = os.environ.get("DATABASE_URL") == previous_url
        assert environment_restored, "renderer must restore the prior environment"


@pytest.mark.integration
# AUD-208 @egorribun
@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS") != "1"
    or not os.environ.get("ALEMBIC_RENDERER_POSTGRES_DATABASE_URL"),
    reason="Requires the owned renderer PostgreSQL CI service",
)
def test_owned_live_renderer_create_collision_preserves_existing_database(
    owned_renderer_admin: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed = uuid.uuid4()
    name = f"alembic_squawk_{fixed.hex[:16]}"
    with _owned_renderer_database(owned_renderer_admin, name) as scratch_url:
        identity = _owned_renderer_database_identity(owned_renderer_admin, name)
        engine = sa.create_engine(scratch_url, connect_args={"connect_timeout": 5})
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE public.renderer_collision_canary (id integer)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO public.renderer_collision_canary VALUES (73)"
                )
            monkeypatch.setattr(renderer, "uuid", SimpleNamespace(uuid4=lambda: fixed))
            previous_url = os.environ.get("DATABASE_URL")
            with pytest.raises(
                renderer.LiveRenderError,
                match=r"^PostgreSQL scratch creation failed$",
            ):
                renderer.render_revision_sql(
                    _ROOT_MIGRATION,
                    owned_renderer_admin.url.render_as_string(hide_password=False),
                )
            current_identity = _owned_renderer_database_identity(
                owned_renderer_admin, name
            )
            assert current_identity == identity
            with engine.connect() as connection:
                rows = connection.exec_driver_sql(
                    "SELECT id FROM public.renderer_collision_canary"
                ).all()
                assert rows == [(73,)]
            environment_restored = os.environ.get("DATABASE_URL") == previous_url
            assert environment_restored, "renderer must restore the prior environment"
        finally:
            engine.dispose()


def _assert_fixed_scratch_error(
    migration: Path, database_url: str, canary: str, expected: str
) -> None:
    error_type: type[Exception] | None = None
    message = ""
    try:
        renderer.render_revision_sql(migration, database_url)
    except Exception as error:
        error_type = type(error)
        message = str(error)
    opaque = canary not in message
    assert opaque, "renderer errors must not expose transport context"
    assert error_type is renderer.LiveRenderError
    assert message == expected


@pytest.mark.parametrize(
    "mode", ["invalid-port", "non-postgresql", "admin-engine-error"]
)
def test_renderer_rejects_invalid_url_and_engine_setup_opaquely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)
    database_url = environment["DATABASE_URL"]
    engine_calls: list[bool] = []

    def failed_engine(*_args: object, **_kwargs: object) -> object:
        engine_calls.append(True)
        raise sa.exc.ArgumentError(admin.canary)

    monkeypatch.setattr(renderer.sa, "create_engine", failed_engine)
    expected = "PostgreSQL database URL is invalid"
    if mode == "invalid-port":
        database_url = f"postgresql+psycopg://renderer@localhost:{admin.canary}/db"
    elif mode == "non-postgresql":
        database_url = "sqlite:///:memory:"
    else:
        expected = "PostgreSQL admin connection failed"

    _assert_fixed_scratch_error(migration, database_url, admin.canary, expected)

    assert engine_calls == ([True] if mode == "admin-engine-error" else [])
    assert admin.statements == []
    assert admin.probes == []
    assert admin.upgrades == []
    assert admin.listeners == []
    assert environment == previous
    assert environment.writes == []


@pytest.mark.parametrize("mode", ["nonoperational-connect", "failed-connect-disposal"])
def test_renderer_connection_failure_disposes_opaquely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)
    attempts: list[bool] = []

    def failed_connect() -> _ScratchConnection:
        attempts.append(True)
        if mode == "nonoperational-connect":
            raise sa.exc.InterfaceError(
                "CONNECT", {"private": admin.canary}, RuntimeError(admin.canary)
            )
        raise admin.failure("CONNECT")

    def failed_dispose() -> None:
        admin.disposed = True
        raise admin.failure("DISPOSE")

    monkeypatch.setattr(admin, "connect", failed_connect)
    if mode == "failed-connect-disposal":
        monkeypatch.setattr(admin, "dispose", failed_dispose)

    _assert_fixed_scratch_error(
        migration,
        environment["DATABASE_URL"],
        admin.canary,
        "PostgreSQL admin connection failed",
    )

    assert len(attempts) == (1 if mode == "nonoperational-connect" else 2)
    assert admin.disposed
    assert admin.statements == []
    assert admin.probes == []
    assert admin.upgrades == []
    assert admin.listeners == []
    assert environment == previous
    assert environment.writes == []


@pytest.mark.parametrize("mode", ["missing-key", "boolean-oid"])
def test_renderer_rejects_malformed_server_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)
    execute = admin.execute

    def malformed_identity(
        scope: str, statement: str, parameters: dict[str, object] | None
    ) -> _ScratchRows | None:
        result = execute(scope, statement, parameters)
        if "PG_DATABASE" in statement.upper():
            assert isinstance(result, _ScratchRows)
            if mode == "missing-key":
                result.rows[0].pop("datdba")
            else:
                result.rows[0]["oid"] = True
        return result

    monkeypatch.setattr(admin, "execute", malformed_identity)

    _assert_fixed_scratch_error(
        migration,
        environment["DATABASE_URL"],
        admin.canary,
        "PostgreSQL scratch identity check failed",
    )

    assert admin.identity_reads == 1
    assert not any(sql.startswith("DROP DATABASE") for sql in admin.statements)
    assert admin.upgrades == []
    assert admin.listeners == []
    assert admin.disposed
    assert environment == previous
    assert environment.writes == []


@pytest.mark.parametrize("field", ["kind", "namespace", "name"])
def test_renderer_rejects_malformed_catalog_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)
    execute = admin.execute

    def malformed_catalog(
        scope: str, statement: str, parameters: dict[str, object] | None
    ) -> _ScratchRows | None:
        result = execute(scope, statement, parameters)
        if "PG_NAMESPACE" in statement.upper():
            assert isinstance(result, _ScratchRows)
            key = {"kind": "kind", "namespace": "nspname", "name": "objname"}[field]
            result.rows[0][key] = 1
        return result

    monkeypatch.setattr(admin, "execute", malformed_catalog)

    _assert_fixed_scratch_error(
        migration,
        environment["DATABASE_URL"],
        admin.canary,
        "PostgreSQL scratch catalog check failed",
    )

    assert admin.timeline == ["create", "identity", "catalog", "identity", "drop"]
    assert admin.upgrades == []
    assert admin.listeners == []
    assert admin.disposed and admin.scratch_disposed
    assert environment == previous
    assert environment.writes == []


@pytest.mark.parametrize(
    "mode",
    [
        "catalog-engine-error",
        "catalog-disposal-error",
        "admin-disposal-error",
        "migration-and-cleanup-error",
    ],
)
def test_renderer_cleanup_preserves_failure_and_disposes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    previous = dict(environment)
    create_engine = renderer.sa.create_engine
    original_error = RuntimeError("migration failure must survive cleanup")

    def failed_scratch_dispose() -> None:
        admin.scratch_disposed = True
        raise admin.failure("SCRATCH DISPOSE")

    def selected_engine(url: str | sa.URL, **kwargs: object) -> object:
        parsed = make_url(url)
        if admin.scratch and parsed.database == admin.scratch:
            if mode == "catalog-engine-error":
                raise sa.exc.ArgumentError(admin.canary)
            engine = create_engine(url, **kwargs)
            if mode == "catalog-disposal-error":
                monkeypatch.setattr(engine, "dispose", failed_scratch_dispose)
            return engine
        return create_engine(url, **kwargs)

    def failed_admin_dispose() -> None:
        admin.disposed = True
        raise admin.failure("ADMIN DISPOSE")

    def failed_upgrade(_config: object, revision: str) -> None:
        admin.upgrades.append(revision)
        admin.timeline.append(f"upgrade:{revision}")
        raise original_error

    monkeypatch.setattr(renderer.sa, "create_engine", selected_engine)
    if mode == "admin-disposal-error":
        monkeypatch.setattr(admin, "dispose", failed_admin_dispose)
    if mode == "migration-and-cleanup-error":
        admin.mode = "cleanup-error"
        monkeypatch.setattr(renderer.command, "upgrade", failed_upgrade)
        preserved = False
        opaque = False
        notes: list[str] = []
        try:
            renderer.render_revision_sql(migration, environment["DATABASE_URL"])
        except Exception as error:
            preserved = error is original_error
            notes = getattr(error, "__notes__", [])
            opaque = admin.canary not in str(error) + repr(notes)
        assert opaque, "cleanup must not disclose transport context"
        assert preserved, "cleanup must preserve the original migration exception"
        assert notes == ["PostgreSQL scratch cleanup failed"]
        assert admin.upgrades == ["parent"]
    else:
        expected = (
            "PostgreSQL scratch cleanup failed"
            if mode == "admin-disposal-error"
            else "PostgreSQL scratch catalog check failed"
        )
        _assert_fixed_scratch_error(
            migration, environment["DATABASE_URL"], admin.canary, expected
        )
        assert admin.upgrades == (
            ["parent", "target"] if mode == "admin-disposal-error" else []
        )

    assert admin.identity_reads == 2
    assert any(sql.startswith("DROP DATABASE") for sql in admin.statements)
    assert admin.disposed
    assert admin.scratch_disposed is (mode != "catalog-engine-error")
    assert environment == previous
    _assert_scratch_listeners_removed(admin)


def test_renderer_restores_unset_environment_after_owned_scratch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    admin, environment, migration = _scratch_case(monkeypatch, tmp_path)
    database_url = environment.pop("DATABASE_URL")
    assert database_url is not None
    environment.writes.clear()

    assert renderer.render_revision_sql(migration, database_url) == ""

    assert "DATABASE_URL" not in environment
    assert environment.writes == ["DATABASE_URL", "DATABASE_URL"]
    assert admin.upgrades == ["parent", "target"]
    assert admin.disposed and admin.scratch_disposed
    _assert_scratch_listeners_removed(admin)


def _install_renderer_pool_transport(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> list[sa.Engine]:
    from sqlalchemy.pool import QueuePool

    create_engine = sa.create_engine
    engines: list[sa.Engine] = []
    options: dict[str, object] = {}

    def owned_sqlite_transport(url: str | sa.URL, **kwargs: object) -> sa.Engine:
        # Keep the requested pool/configuration; replace only the PG transport.
        assert make_url(url) == make_url(database_url)
        assert kwargs.pop("connect_args") == {"connect_timeout": 5}
        kwargs.setdefault("poolclass", QueuePool)
        assert set(kwargs) == {"isolation_level", "poolclass"}
        assert kwargs["isolation_level"] == "AUTOCOMMIT"
        if engines:
            assert kwargs == options
            return engines[0]
        options.update(kwargs)
        engine = create_engine(
            "sqlite://",
            pool_logging_name="renderer-pool-" + uuid.uuid4().hex,
            **kwargs,
        )
        engines.append(engine)
        return engine

    monkeypatch.setattr(renderer.sa, "create_engine", owned_sqlite_transport)
    return engines


def test_renderer_admin_pool_reset_diagnostics_are_opaque(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import logging
    import sqlite3

    marker = "synthetic-" + uuid.uuid4().hex
    database_url = "postgresql+psycopg://renderer@localhost/owned_fixture"
    reset_calls: list[bool] = []
    returned: sa.Engine | None = None
    bounded_error = False
    private_error = False
    private_sinks = False
    pool_failure_logged = False
    engines: list[sa.Engine] = []

    try:
        with monkeypatch.context() as patch:
            engines = _install_renderer_pool_transport(patch, database_url)
            engine = renderer._admin_engine(database_url)
            pool_logger = logging.getLogger(engine.pool.logger.name)
            assert pool_logger.name.startswith("sqlalchemy.pool.impl.QueuePool.")
            original_reset = engine.dialect.do_rollback

            def failed_reset(connection: object) -> None:
                original_reset(connection)
                reset_calls.append(True)
                raise sqlite3.OperationalError(marker)

            # Capture only this uniquely named pool. No global logger is disabled,
            # and raw synthetic records must not reach pytest's failure report.
            patch.setattr(pool_logger, "propagate", False)
            pool_logger.addHandler(caplog.handler)
            try:
                with caplog.at_level(logging.ERROR, logger=pool_logger.name):
                    # Positive control primes initialization before reset failure.
                    assert renderer._connect_admin(database_url) is engine
                    with engine.connect() as connection:
                        value = connection.exec_driver_sql("SELECT 73").scalar_one()
                        assert value == 73
                    assert not caplog.records
                    control = capsys.readouterr()
                    assert control.out == "" and control.err == ""

                    patch.setattr(engine.dialect, "do_rollback", failed_reset)
                    try:
                        returned = renderer._connect_admin(database_url)
                    except Exception as error:
                        private_error = marker in str(error)
                        bounded_error = (
                            type(error) is renderer.LiveRenderError
                            and str(error) == "PostgreSQL admin connection failed"
                        )

                    pool_failure_logged = any(
                        record.name == pool_logger.name
                        and record.levelno >= logging.ERROR
                        for record in caplog.records
                    )
                    captured = capsys.readouterr()
                    private_sinks = marker in caplog.text + captured.out + captured.err
                    del captured
            finally:
                caplog.clear()
                pool_logger.removeHandler(caplog.handler)
    finally:
        # Restore the real rollback before disposing every owned engine.
        for engine in engines:
            engine.dispose()

    assert reset_calls, "the real pool must reach the injected reset failure"
    assert returned is engine or bounded_error, "unexpected renderer failure shape"
    assert pool_failure_logged, "the real pool failure must remain observable"
    assert not private_error
    assert not private_sinks, (
        "renderer pool diagnostics exposed synthetic private context"
    )


@pytest.mark.parametrize("entry_point", ["admin", "catalog"])
def test_renderer_pool_privacy_survives_recreation_without_changing_other_pools(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    entry_point: str,
) -> None:
    import logging
    import sqlite3

    from sqlalchemy.pool import QueuePool

    marker = "synthetic-" + uuid.uuid4().hex
    database_url = "postgresql+psycopg://renderer@localhost/owned_fixture"
    create_engine = sa.create_engine
    unrelated = create_engine(
        "sqlite://",
        poolclass=QueuePool,
        pool_logging_name="unrelated-pool-" + uuid.uuid4().hex,
    )
    engines: list[sa.Engine] = []
    invalidations: list[bool] = []
    info_observed = False
    private_sinks = False
    bounded_records = False
    unrelated_unchanged = False
    operation_failed = False

    def observed_invalidation(
        _connection: object, _record: object, error: BaseException | None
    ) -> None:
        invalidations.append(isinstance(error, sqlite3.OperationalError))

    try:
        with monkeypatch.context() as patch:
            engines = _install_renderer_pool_transport(patch, database_url)
            if entry_point == "admin":
                engine = renderer._admin_engine(database_url)
            else:
                # Real SQLite cannot execute PG catalogs: only the owned engine
                # creation/disposal path is tested here, not catalog admission.
                with pytest.raises(
                    renderer.LiveRenderError,
                    match=r"^PostgreSQL scratch catalog check failed$",
                ):
                    renderer._assert_empty_scratch_catalog(database_url)
                engine = engines[0]

            pool_logger = logging.getLogger(engine.pool.logger.name)
            assert pool_logger.name.startswith("sqlalchemy.pool.impl.QueuePool.")
            other_logger = logging.getLogger(unrelated.pool.logger.name)
            assert isinstance(unrelated.pool.logger, logging.Logger)
            assert not pool_logger.filters
            assert not other_logger.filters
            for logger in (pool_logger, other_logger):
                patch.setattr(logger, "propagate", False)
                logger.addHandler(caplog.handler)
            sa.event.listen(engine, "invalidate", observed_invalidation)
            try:
                with (
                    caplog.at_level(logging.INFO, logger=pool_logger.name),
                    caplog.at_level(logging.INFO, logger=other_logger.name),
                ):
                    with engine.connect() as connection:
                        value = connection.exec_driver_sql("SELECT 73").scalar_one()
                        assert value == 73
                    caplog.clear()
                    capsys.readouterr()
                    try:
                        for recreated in (False, True):
                            if recreated:
                                previous_pool = engine.pool
                                engine.dispose()
                                assert engine.pool is not previous_pool
                            with engine.connect() as connection:
                                connection.invalidate(sqlite3.OperationalError(marker))
                        engine.pool.logger.error(
                            "private-%s",
                            marker,
                            exc_info=(RuntimeError, RuntimeError(marker), None),
                            extra={"private_context": marker},
                            stack_info=True,
                        )
                    except Exception:
                        operation_failed = True

                    records = [
                        record
                        for record in caplog.records
                        if record.name == pool_logger.name
                    ]
                    info_observed = any(
                        record.levelno == logging.INFO for record in records
                    )
                    bounded_records = bool(records) and all(
                        record.msg == "PostgreSQL renderer pool diagnostic"
                        and record.args == ()
                        and record.exc_info is None
                        and record.stack_info is None
                        and not hasattr(record, "private_context")
                        for record in records
                    )
                    captured = capsys.readouterr()
                    private_sinks = marker in caplog.text + captured.out + captured.err
                    del records, captured
                    caplog.clear()
                    with unrelated.connect() as connection:
                        connection.invalidate(sqlite3.OperationalError(marker))
                    unrelated_unchanged = any(
                        record.name == other_logger.name
                        and record.levelno == logging.INFO
                        and marker in record.getMessage()
                        for record in caplog.records
                    )
                    capsys.readouterr()
            finally:
                sa.event.remove(engine, "invalidate", observed_invalidation)
                caplog.clear()
                for logger in (pool_logger, other_logger):
                    logger.removeHandler(caplog.handler)
    finally:
        for engine in engines:
            engine.dispose()
        unrelated.dispose()

    assert not operation_failed, "owned pool diagnostics must not break operations"
    assert invalidations == [True, True]
    assert info_observed, "real invalidation diagnostics must remain observable"
    assert bounded_records, "owned pool records must contain only fixed diagnostics"
    assert not private_sinks, "owned pool diagnostics exposed synthetic private context"
    assert unrelated_unchanged, "other pool diagnostics must remain unchanged"
