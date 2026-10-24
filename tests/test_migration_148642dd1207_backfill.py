from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
import sqlalchemy.inspection as sa_inspection
from sqlalchemy.dialects import postgresql, sqlite

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = PROJECT_ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"
LEGACY_TYPES = {
    "spotify_user_id": sa.String(),
    "spotify_access_token": sa.Text(),
    "spotify_refresh_token": sa.Text(),
    "spotify_token_expires_at": sa.DateTime(timezone=True),
    "spotify_scope": sa.Text(),
    "spotify_display_name": sa.String(),
    "spotify_is_connected": sa.Boolean(),
    "spotify_is_playing": sa.Boolean(),
    "spotify_last_checked_at": sa.DateTime(timezone=True),
    "spotify_last_track_id": sa.String(),
    "spotify_last_track_name": sa.String(),
    "spotify_last_artist_name": sa.String(),
    "spotify_last_album_name": sa.String(),
    "spotify_last_track_url": sa.String(),
    "spotify_last_album_image_url": sa.String(),
}
TARGET_TYPES = {
    "spotify_user_id": sa.String(),
    "access_token": sa.Text(),
    "refresh_token": sa.Text(),
    "token_expires_at": sa.DateTime(timezone=True),
    "scope": sa.Text(),
    "display_name": sa.String(),
    "is_connected": sa.Boolean(),
    "is_playing": sa.Boolean(),
    "last_checked_at": sa.DateTime(timezone=True),
    "last_track_id": sa.String(),
    "last_track_name": sa.String(),
    "last_artist_name": sa.String(),
    "last_album_name": sa.String(),
    "last_track_url": sa.String(),
    "last_album_image_url": sa.String(),
}


def _load_migration() -> Any:
    name = "private_migration_148642dd1207_backfill_coverage"
    spec = importlib.util.spec_from_file_location(name, CANDIDATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _tables(
    engine: Any,
    *,
    user_fields: tuple[str, ...] = tuple(LEGACY_TYPES),
    target_fields: tuple[str, ...] = ("user_id", *TARGET_TYPES),
    user_id_column: bool = True,
) -> tuple[sa.Table | None, sa.Table | None]:
    metadata = sa.MetaData()
    users_columns = []
    if user_id_column:
        users_columns.append(sa.Column("id", sa.Integer(), primary_key=True))
    else:
        users_columns.append(sa.Column("source_key", sa.Integer(), primary_key=True))
    for name in user_fields:
        users_columns.append(sa.Column(name, LEGACY_TYPES[name], nullable=True))
    users = sa.Table("users", metadata, *users_columns)
    target_columns = []
    for name in target_fields:
        if name == "user_id":
            target_columns.append(sa.Column(name, sa.Integer(), primary_key=True))
        else:
            target_columns.append(
                sa.Column(
                    name,
                    TARGET_TYPES[name],
                    nullable=name not in {"is_connected", "is_playing"},
                )
            )
    integrations = sa.Table("spotify_integrations", metadata, *target_columns)
    metadata.create_all(engine)
    return users, integrations


class _Ops:
    def __init__(self, bind: Any, *, execute: Any | None = None) -> None:
        self._bind = bind
        self._execute = execute or bind.execute
        self.statements: list[Any] = []

    def get_bind(self) -> Any:
        return self._bind

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.statements.append(statement)
        return self._execute(statement, *args, **kwargs)


class _DialectProxy:
    def __init__(self, connection: Any, dialect_name: str) -> None:
        self.connection = connection
        self.dialect = SimpleNamespace(name=dialect_name)
        self.statements: list[Any] = []

    def execute(self, statement: Any, *_args: Any, **_kwargs: Any) -> Any:
        self.statements.append(statement)
        return statement


def _install(
    monkeypatch: pytest.MonkeyPatch, migration: Any, context: Any, ops: Any
) -> None:
    monkeypatch.setattr(migration, "context", context)
    monkeypatch.setattr(migration, "op", ops)


def test_sqlite_backfill_preserves_ciphertext_and_existing_destination_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, integrations = _tables(engine)
    assert users is not None and integrations is not None
    ciphertext = "v1:nonce:opaque-ciphertext:tag"
    old_ciphertext = "v1:original-existing-ciphertext"
    expiry = datetime(2026, 10, 23, 9, 15, tzinfo=UTC)
    with engine.begin() as conn:
        user_rows = []
        for row in (
            {
                "id": 41,
                "spotify_user_id": "sp-41",
                "spotify_access_token": ciphertext,
                "spotify_refresh_token": "refresh-41",
                "spotify_token_expires_at": expiry,
                "spotify_scope": "user-read-playback-state",
                "spotify_display_name": "Legacy display",
                "spotify_is_connected": False,
                "spotify_is_playing": True,
                "spotify_last_checked_at": expiry,
                "spotify_last_track_id": "track-41",
                "spotify_last_track_name": "Legacy track",
                "spotify_last_artist_name": "Legacy artist",
                "spotify_last_album_name": "Legacy album",
                "spotify_last_track_url": "https://example.test/41",
                "spotify_last_album_image_url": "https://example.test/41.png",
            },
            {"id": 42, "spotify_access_token": "partial-token"},
            {"id": 43},
            {"id": 44, "spotify_access_token": "new-value-must-not-win"},
        ):
            user_row = {name: None for name in users.c.keys()}
            user_row.update(row)
            user_rows.append(user_row)
        conn.execute(users.insert(), user_rows)
        conn.execute(
            integrations.insert(),
            {
                "user_id": 44,
                "access_token": old_ciphertext,
                "is_connected": True,
                "is_playing": True,
            },
        )
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )

        migration._backfill_spotify_integrations()

        rows = {
            row["user_id"]: row
            for row in conn.execute(sa.select(integrations)).mappings()
        }
        assert set(rows) == {41, 42, 44}
        assert rows[41]["access_token"] == ciphertext
        assert rows[41]["refresh_token"] == "refresh-41"
        assert rows[41]["spotify_user_id"] == "sp-41"
        assert rows[41]["display_name"] == "Legacy display"
        assert rows[41]["is_connected"] is False
        assert rows[41]["is_playing"] is True
        assert rows[41]["last_track_name"] == "Legacy track"
        assert rows[41]["last_artist_name"] == "Legacy artist"
        assert rows[41]["last_album_name"] == "Legacy album"
        assert rows[42]["access_token"] == "partial-token"
        assert rows[42]["spotify_user_id"] is None
        assert rows[42]["is_connected"] is True
        assert rows[42]["is_playing"] is False
        assert rows[44]["access_token"] == old_ciphertext
        assert rows[44]["is_connected"] is True
        assert rows[44]["is_playing"] is True
        access_token_column = next(
            column
            for column in sa.inspect(conn).get_columns("spotify_integrations")
            if column["name"] == "access_token"
        )
        assert isinstance(access_token_column["type"], sa.Text)
    engine.dispose()


def test_backfill_missing_legacy_columns_maps_null_for_absent_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, integrations = _tables(engine, user_fields=("spotify_access_token",))
    assert users is not None and integrations is not None
    with engine.begin() as conn:
        conn.execute(users.insert(), {"id": 51, "spotify_access_token": "only-token"})
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )
        migration._backfill_spotify_integrations()
        row = (
            conn.execute(sa.select(integrations).where(integrations.c.user_id == 51))
            .mappings()
            .one()
        )
        assert row["access_token"] == "only-token"
        assert row["refresh_token"] is None
        assert row["token_expires_at"] is None
        assert row["is_connected"] is True
    engine.dispose()


def test_backfill_without_credential_columns_keeps_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, integrations = _tables(engine, user_fields=("spotify_user_id",))
    assert users is not None and integrations is not None

    with engine.begin() as conn:
        conn.execute(
            users.insert(), {"id": 52, "spotify_user_id": "profile-without-token"}
        )
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )
        migration._backfill_spotify_integrations()
        row = (
            conn.execute(sa.select(integrations).where(integrations.c.user_id == 52))
            .mappings()
            .one()
        )

    assert row["spotify_user_id"] == "profile-without-token"
    assert row["is_connected"] is False
    assert row["is_playing"] is False
    engine.dispose()


@pytest.mark.parametrize(
    ("legacy_name", "target_name", "value"),
    [
        ("spotify_user_id", "spotify_user_id", "spotify-user-71"),
        ("spotify_access_token", "access_token", "v1:opaque-access-token"),
        ("spotify_refresh_token", "refresh_token", "v1:opaque-refresh-token"),
        (
            "spotify_token_expires_at",
            "token_expires_at",
            datetime(2026, 10, 23, 9, 15, tzinfo=UTC),
        ),
        ("spotify_scope", "scope", "user-read-playback-state"),
        ("spotify_display_name", "display_name", "Legacy name"),
        ("spotify_is_connected", "is_connected", True),
        ("spotify_is_connected", "is_connected", False),
        (
            "spotify_last_checked_at",
            "last_checked_at",
            datetime(2026, 10, 23, 9, 16, tzinfo=UTC),
        ),
        ("spotify_last_track_id", "last_track_id", "track-71"),
        ("spotify_last_track_name", "last_track_name", "Track name"),
        ("spotify_last_artist_name", "last_artist_name", "Artist name"),
        ("spotify_last_album_name", "last_album_name", "Album name"),
        ("spotify_is_playing", "is_playing", True),
        ("spotify_is_playing", "is_playing", False),
        ("spotify_last_track_url", "last_track_url", "https://example.test/71"),
        (
            "spotify_last_album_image_url",
            "last_album_image_url",
            "https://example.test/71.png",
        ),
        ("spotify_access_token", "access_token", ""),
    ],
)
def test_each_nonnull_legacy_field_alone_preserves_its_destination_value(
    monkeypatch: pytest.MonkeyPatch,
    legacy_name: str,
    target_name: str,
    value: Any,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, integrations = _tables(engine)
    assert users is not None and integrations is not None
    user_row = {name: None for name in users.c.keys()}
    user_row.update({"id": 71, legacy_name: value})

    with engine.begin() as conn:
        conn.execute(users.insert(), user_row)
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )
        migration._backfill_spotify_integrations()
        row = (
            conn.execute(sa.select(integrations).where(integrations.c.user_id == 71))
            .mappings()
            .one()
        )

    expected = value.replace(tzinfo=None) if isinstance(value, datetime) else value
    assert row[target_name] == expected
    if legacy_name == "spotify_is_connected":
        expected_connected = value
    else:
        expected_connected = legacy_name in {
            "spotify_access_token",
            "spotify_refresh_token",
        } and bool(value)
    assert row["is_connected"] is expected_connected
    assert row["is_playing"] is (
        value if legacy_name == "spotify_is_playing" else False
    )
    engine.dispose()


def test_backfill_noops_offline_without_requesting_a_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()

    class _UnexpectedOps:
        def get_bind(self) -> Any:
            raise AssertionError("offline backfill must not request a connection")

    _install(
        monkeypatch,
        migration,
        SimpleNamespace(is_offline_mode=lambda: True),
        _UnexpectedOps(),
    )
    migration._backfill_spotify_integrations()


def test_backfill_noops_when_bind_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    _install(
        monkeypatch,
        migration,
        SimpleNamespace(is_offline_mode=lambda: False),
        SimpleNamespace(get_bind=lambda: None),
    )
    migration._backfill_spotify_integrations()


def test_backfill_returns_when_source_or_destination_table_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    for absent_table in ("users", "spotify_integrations"):
        engine = sa.create_engine("sqlite+pysqlite:///:memory:")
        metadata = sa.MetaData()
        if absent_table != "users":
            sa.Table("users", metadata, sa.Column("id", sa.Integer(), primary_key=True))
        if absent_table != "spotify_integrations":
            sa.Table(
                "spotify_integrations",
                metadata,
                sa.Column("user_id", sa.Integer(), primary_key=True),
                *[
                    sa.Column(
                        name, dtype, nullable=name not in {"is_connected", "is_playing"}
                    )
                    for name, dtype in TARGET_TYPES.items()
                ],
            )
        metadata.create_all(engine)
        with engine.begin() as conn:
            _install(
                monkeypatch,
                migration,
                SimpleNamespace(is_offline_mode=lambda: False),
                _Ops(conn),
            )
            migration._backfill_spotify_integrations()
        engine.dispose()


def test_backfill_returns_when_no_legacy_spotify_field_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, _ = _tables(engine, user_fields=())
    assert users is not None
    with engine.begin() as conn:
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )
        migration._backfill_spotify_integrations()
    engine.dispose()


def test_backfill_rejects_missing_user_id_or_missing_target_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, _ = _tables(
        engine, user_fields=("spotify_access_token",), user_id_column=False
    )
    assert users is not None
    with engine.begin() as conn:
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )
        with pytest.raises(RuntimeError, match=r"without users.id"):
            migration._backfill_spotify_integrations()
    engine.dispose()

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spotify_access_token", sa.Text()),
    )
    sa.Table(
        "spotify_integrations",
        metadata,
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("access_token", sa.Text()),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        _install(
            monkeypatch,
            migration,
            SimpleNamespace(is_offline_mode=lambda: False),
            _Ops(conn),
        )
        with pytest.raises(RuntimeError, match="target columns are missing"):
            migration._backfill_spotify_integrations()
    engine.dispose()


def test_backfill_postgresql_and_generic_dialects_generate_safe_insert_forms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    users, _ = _tables(engine, user_fields=("spotify_access_token",))
    assert users is not None
    with engine.begin() as conn:
        conn.execute(users.insert(), {"id": 61, "spotify_access_token": "opaque"})
        original_inspect = sa_inspection.inspect
        original_package_inspect = sa.inspect
        for dialect_name in ("postgresql", "mysql"):
            proxy = _DialectProxy(conn, dialect_name)

            def inspect_proxy(
                subject: Any, *args: Any, _proxy: Any = proxy, **kwargs: Any
            ) -> Any:
                return original_inspect(
                    conn if subject is _proxy else subject, *args, **kwargs
                )

            monkeypatch.setattr(sa_inspection, "inspect", inspect_proxy)
            monkeypatch.setattr(migration.sa, "inspect", inspect_proxy)
            ops = _Ops(proxy, execute=lambda statement, *_a, **_kw: statement)
            _install(
                monkeypatch,
                migration,
                SimpleNamespace(is_offline_mode=lambda: False),
                ops,
            )
            migration._backfill_spotify_integrations()
            assert len(proxy.statements) == 1
            compiled = str(
                proxy.statements[0].compile(
                    dialect=(
                        postgresql.dialect()
                        if dialect_name == "postgresql"
                        else sqlite.dialect()
                    ),
                    compile_kwargs={"literal_binds": True},
                )
            ).upper()
            if dialect_name == "postgresql":
                assert "ON CONFLICT (USER_ID) DO NOTHING" in compiled
            else:
                assert "NOT (EXISTS" in compiled
                assert "WHERE" in compiled
            monkeypatch.setattr(sa_inspection, "inspect", original_inspect)
            monkeypatch.setattr(migration.sa, "inspect", original_package_inspect)
    engine.dispose()


_PREFERENCE_TYPES = {
    "dnd_enabled": sa.Boolean(),
    "dnd_start": sa.Time(),
    "dnd_end": sa.Time(),
    "timezone": sa.String(length=64),
}


def _preference_tables(
    engine: Any,
    *,
    user_fields: tuple[str, ...] = tuple(_PREFERENCE_TYPES),
) -> tuple[sa.Table, sa.Table]:
    metadata = sa.MetaData()
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        *(sa.Column(name, _PREFERENCE_TYPES[name]) for name in user_fields),
    )
    preferences = sa.Table(
        "user_preferences",
        metadata,
        sa.Column("user_id", sa.Integer(), primary_key=True),
        *(
            sa.Column(name, dtype, nullable=name != "dnd_enabled")
            for name, dtype in _PREFERENCE_TYPES.items()
        ),
    )
    metadata.create_all(engine)
    return users, preferences


def test_preferences_backfill_preserves_values_and_stays_in_caller_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        users, preferences = _preference_tables(engine)
        with engine.begin() as connection:
            connection.execute(
                users.insert(),
                [
                    {
                        "id": 11,
                        "dnd_enabled": True,
                        "dnd_start": time(23, 45, 30, 123456),
                        "dnd_end": time(6, 15, 1, 654321),
                        "timezone": "Asia/Kathmandu",
                    },
                    {
                        "id": 12,
                        "dnd_enabled": False,
                        "dnd_start": time(0),
                        "dnd_end": time(0),
                        "timezone": "Europe/Istanbul",
                    },
                    {
                        "id": 13,
                        "dnd_enabled": True,
                        "dnd_start": time(22),
                        "dnd_end": time(7),
                        "timezone": "America/St_Johns",
                    },
                ],
            )
            connection.execute(
                preferences.insert(),
                {"user_id": 13, "dnd_enabled": False},
            )

        with engine.connect() as connection:
            transaction = connection.begin()
            _install(
                monkeypatch,
                migration,
                SimpleNamespace(is_offline_mode=lambda: False),
                _Ops(connection),
            )
            migration._backfill_user_preferences()
            migration._backfill_user_preferences()
            assert connection.execute(
                sa.select(preferences).order_by(preferences.c.user_id)
            ).all() == [
                (
                    11,
                    True,
                    time(23, 45, 30, 123456),
                    time(6, 15, 1, 654321),
                    "Asia/Kathmandu",
                ),
                (12, False, time(0), time(0), "Europe/Istanbul"),
                (13, False, None, None, None),
            ]
            transaction.rollback()

        with engine.connect() as connection:
            assert connection.execute(sa.select(preferences)).all() == [
                (13, False, None, None, None)
            ]
            assert (
                connection.execute(
                    sa.select(sa.func.count()).select_from(users)
                ).scalar_one()
                == 3
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("legacy_field", "value", "expected"),
    [
        ("dnd_enabled", False, (21, False, None, None, None)),
        (
            "dnd_start",
            time(0, 0, 0, 1),
            (21, False, time(0, 0, 0, 1), None, None),
        ),
        ("dnd_end", time(0), (21, False, None, time(0), None)),
        ("timezone", "Asia/Kathmandu", (21, False, None, None, "Asia/Kathmandu")),
        ("timezone", None, (21, False, None, None, None)),
    ],
)
def test_preferences_backfill_keeps_each_surviving_legacy_field(
    monkeypatch: pytest.MonkeyPatch,
    legacy_field: str,
    value: Any,
    expected: tuple[Any, ...],
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        users, preferences = _preference_tables(engine, user_fields=(legacy_field,))
        with engine.begin() as connection:
            connection.execute(users.insert(), {"id": 21, legacy_field: value})
            _install(
                monkeypatch,
                migration,
                SimpleNamespace(is_offline_mode=lambda: False),
                _Ops(connection),
            )
            migration._backfill_user_preferences()
            assert connection.execute(sa.select(preferences)).one() == expected
    finally:
        engine.dispose()


def test_preferences_backfill_leaves_normal_parent_without_legacy_columns_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        users, preferences = _preference_tables(engine, user_fields=())
        with engine.begin() as connection:
            connection.execute(users.insert(), {"id": 31})
            _install(
                monkeypatch,
                migration,
                SimpleNamespace(is_offline_mode=lambda: False),
                _Ops(connection),
            )
            migration._backfill_user_preferences()
            assert connection.execute(sa.select(preferences)).all() == []
            assert connection.execute(sa.select(users.c.id)).all() == [(31,)]
    finally:
        engine.dispose()


def test_preferences_backfill_does_not_reflect_an_offline_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()

    def unexpected_bind() -> Any:
        raise AssertionError("offline preference backfill requested a connection")

    _install(
        monkeypatch,
        migration,
        SimpleNamespace(is_offline_mode=lambda: True),
        SimpleNamespace(get_bind=unexpected_bind),
    )
    migration._backfill_user_preferences()


def test_preferences_backfill_emits_postgresql_conflict_preserving_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect the emitted PostgreSQL statement; PG data proof is integration."""
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        _preference_tables(engine)
        with engine.begin() as connection:
            proxy = _DialectProxy(connection, "postgresql")
            original_inspect = sa_inspection.inspect

            def inspect_proxy(subject: Any, *args: Any, **kwargs: Any) -> Any:
                return original_inspect(
                    connection if subject is proxy else subject, *args, **kwargs
                )

            monkeypatch.setattr(sa_inspection, "inspect", inspect_proxy)
            monkeypatch.setattr(migration.sa, "inspect", inspect_proxy)
            _install(
                monkeypatch,
                migration,
                SimpleNamespace(is_offline_mode=lambda: False),
                _Ops(proxy),
            )
            migration._backfill_user_preferences()

            assert len(proxy.statements) == 1
            compiled = str(
                proxy.statements[0].compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            ).upper()
            assert "INSERT INTO USER_PREFERENCES" in compiled
            assert "NOT (EXISTS" in compiled
            assert "ON CONFLICT (USER_ID) DO NOTHING" in compiled
    finally:
        engine.dispose()


def test_preferences_backfill_rejects_present_null_enabled_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not silently convert an existing NULL boolean into a default value."""
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        users, preferences = _preference_tables(engine, user_fields=("dnd_enabled",))
        with engine.begin() as connection:
            connection.execute(
                users.insert(),
                [
                    {"id": 41, "dnd_enabled": False},
                    {"id": 42, "dnd_enabled": None},
                    {"id": 43, "dnd_enabled": True},
                ],
            )
            connection.execute(
                preferences.insert(), {"user_id": 43, "dnd_enabled": False}
            )
        with pytest.raises(sa.exc.IntegrityError, match="dnd_enabled"):
            with engine.begin() as connection:
                connection.execute(
                    preferences.insert(), {"user_id": 44, "dnd_enabled": False}
                )
                _install(
                    monkeypatch,
                    migration,
                    SimpleNamespace(is_offline_mode=lambda: False),
                    _Ops(connection),
                )
                migration._backfill_user_preferences()

        with engine.connect() as connection:
            assert connection.execute(
                sa.select(preferences).order_by(preferences.c.user_id)
            ).all() == [(43, False, None, None, None)]
            assert connection.execute(sa.select(users).order_by(users.c.id)).all() == [
                (41, False),
                (42, None),
                (43, True),
            ]
    finally:
        engine.dispose()
