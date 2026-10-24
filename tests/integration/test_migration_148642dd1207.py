"""PostgreSQL regressions for the 148642dd1207 shadow-key conversion."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from psycopg import sql
from sqlalchemy import Text, event
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from app.core.config import settings
from app.models.spotify import SpotifyIntegration
from app.utils.encryption import (
    EncryptedString,
    decrypt_string,
    encrypt_string,
    reset_cached_cipher,
)
from tests.helpers import migration_148642dd1207_trace as ddl_trace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest.fixture(scope="module")
def migration_postgres():
    """Provide an isolated PostgreSQL instance with the required extension."""

    with PostgresContainer(
        "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
    ) as postgres:
        yield postgres


def test_invalid_fk_value_aborts_shadow_conversion_without_data_loss(
    migration_postgres,
) -> None:
    """Reject an invalid child key before PostgreSQL can evaluate an unsafe cast."""

    original_url = migration_postgres.get_connection_url()
    alembic_url = original_url.replace("+psycopg2", "+psycopg")
    sync_url = original_url.replace("+psycopg2", "")
    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = alembic_url

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", alembic_url)

    try:
        command.upgrade(config, "f7aa476e968a")
        with psycopg.connect(sync_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO groups (id) VALUES (%s)", ("1",))
                cursor.execute(
                    "CREATE TABLE invalid_group_refs "
                    "(id serial PRIMARY KEY, group_id varchar(20))"
                )
                cursor.execute(
                    "INSERT INTO invalid_group_refs (group_id) VALUES (%s)",
                    ("oops",),
                )
                cursor.execute(
                    "ALTER TABLE invalid_group_refs "
                    "ADD CONSTRAINT invalid_group_refs_group_fk "
                    "FOREIGN KEY (group_id) REFERENCES groups(id) NOT VALID"
                )
            connection.commit()

        with pytest.raises(Exception) as exc_info:
            command.upgrade(config, "148642dd1207")
        assert "groups FK column" in str(exc_info.value)

        with psycopg.connect(sync_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone() == ("f7aa476e968a",)
                cursor.execute(
                    "SELECT data_type, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'groups' AND column_name = 'id'"
                )
                assert cursor.fetchone() == ("character varying", 20)
                cursor.execute(
                    "SELECT data_type, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'invalid_group_refs' "
                    "AND column_name = 'group_id'"
                )
                assert cursor.fetchone() == ("character varying", 20)
                cursor.execute(
                    "SELECT COUNT(*) FROM invalid_group_refs WHERE group_id = %s",
                    ("oops",),
                )
                assert cursor.fetchone() == (1,)
                cursor.execute(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conname = 'invalid_group_refs_group_fk'"
                )
                assert cursor.fetchone() == ("invalid_group_refs_group_fk",)
    finally:
        if original_database_url is not None:
            os.environ["DATABASE_URL"] = original_database_url
        else:
            os.environ.pop("DATABASE_URL", None)


@contextmanager
def _owned_migration_scenario(migration_postgres) -> Iterator[dict[str, str]]:
    """Give each Spotify migration scenario a fresh database on the shared test PG."""
    base_url = make_url(migration_postgres.get_connection_url())
    database_name = f"aud348_spotify_{uuid4().hex}"
    admin_url = base_url.set(database="postgres", drivername="postgresql")
    admin_conninfo = admin_url.render_as_string(hide_password=False)
    identifier = sql.Identifier(database_name)
    database_created = False

    try:
        with psycopg.connect(admin_conninfo, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(identifier))
            database_created = True
            admin.execute(
                sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(identifier)
            )

        scenario_url = base_url.set(
            database=database_name, drivername="postgresql+psycopg"
        )
        yield {
            "alembic": scenario_url.render_as_string(hide_password=False),
            "sync": scenario_url.set(drivername="postgresql").render_as_string(
                hide_password=False
            ),
        }
    finally:
        if database_created:
            with psycopg.connect(admin_conninfo, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        identifier
                    )
                )


@pytest.fixture
def spotify_scenario_urls(migration_postgres) -> Iterator[dict[str, str]]:
    with _owned_migration_scenario(migration_postgres) as urls:
        yield urls


_SPOTIFY_LEGACY_FIELDS = (
    "spotify_user_id",
    "spotify_access_token",
    "spotify_refresh_token",
    "spotify_token_expires_at",
    "spotify_scope",
    "spotify_last_checked_at",
    "spotify_last_track_id",
    "spotify_last_track_url",
    "spotify_last_album_image_url",
)

_SPOTIFY_OPTIONAL_FIELDS = (
    "spotify_display_name",
    "spotify_is_connected",
    "spotify_is_playing",
    "spotify_last_track_name",
    "spotify_last_artist_name",
    "spotify_last_album_name",
)


@pytest.fixture(autouse=True)
def token_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "spotify_token_secret", key)
    reset_cached_cipher()
    yield key
    reset_cached_cipher()


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _prepare_parent_revision(
    config: Config,
    alembic_database_url: str,
    sync_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", alembic_database_url)
    command.upgrade(config, "f7aa476e968a")
    with psycopg.connect(sync_database_url) as connection:
        _add_legacy_spotify_fields(connection)


def _add_lowercase_role_values(connection: psycopg.Connection) -> None:
    # Keep AUD-327's uppercase-role path out of these focused backfill scenarios.
    for role in ("student", "teacher", "admin", "superuser", "anonymous"):
        connection.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}'")
    connection.commit()


def _add_legacy_spotify_fields(connection: psycopg.Connection) -> None:
    # The supported backfill shape has these columns even though the normal
    # migration ancestry removed them before this revision.
    for field, sql_type in (
        ("spotify_user_id", "text"),
        ("spotify_access_token", "text"),
        ("spotify_refresh_token", "text"),
        ("spotify_token_expires_at", "timestamptz"),
        ("spotify_scope", "text"),
        ("spotify_last_checked_at", "timestamptz"),
        ("spotify_last_track_id", "text"),
        ("spotify_last_track_url", "text"),
        ("spotify_last_album_image_url", "text"),
    ):
        connection.execute(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {field} {sql_type}"
        )


def _insert_user(
    connection: psycopg.Connection,
    user_id: int,
    spotify_fields: dict[str, object | None],
) -> None:
    columns = (
        "id",
        "email",
        "hashed_password",
        "role",
        "mfa_required",
        *_SPOTIFY_LEGACY_FIELDS,
        *_SPOTIFY_OPTIONAL_FIELDS,
    )
    values = (
        user_id,
        f"spotify-{user_id}@example.test",
        "unused-migration-test-hash",
        "student",
        False,
        *(spotify_fields[field] for field in _SPOTIFY_LEGACY_FIELDS),
        *(spotify_fields[field] for field in _SPOTIFY_OPTIONAL_FIELDS),
    )
    statement = sql.SQL("INSERT INTO users ({columns}) VALUES ({placeholders})").format(
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    connection.execute(statement, values)


def _legacy_record(
    *,
    access: str | None,
    refresh: str | None,
    spotify_user_id: str | None,
    scope: str | None,
    expires_at: datetime | None,
    checked_at: datetime | None,
    track_id: str | None,
    track_url: str | None,
    album_image_url: str | None,
    display_name: str | None = None,
    is_connected: bool | None = None,
    is_playing: bool | None = None,
    track_name: str | None = None,
    artist_name: str | None = None,
    album_name: str | None = None,
) -> dict[str, object | None]:
    return {
        "spotify_user_id": spotify_user_id,
        "spotify_access_token": access,
        "spotify_refresh_token": refresh,
        "spotify_token_expires_at": expires_at,
        "spotify_scope": scope,
        "spotify_display_name": display_name,
        "spotify_is_connected": is_connected,
        "spotify_is_playing": is_playing,
        "spotify_last_checked_at": checked_at,
        "spotify_last_track_id": track_id,
        "spotify_last_track_name": track_name,
        "spotify_last_artist_name": artist_name,
        "spotify_last_album_name": album_name,
        "spotify_last_track_url": track_url,
        "spotify_last_album_image_url": album_image_url,
    }


def _add_optional_legacy_fields(connection: psycopg.Connection) -> None:
    for field, sql_type in (
        ("spotify_display_name", "text"),
        ("spotify_is_connected", "boolean"),
        ("spotify_is_playing", "boolean"),
        ("spotify_last_track_name", "text"),
        ("spotify_last_artist_name", "text"),
        ("spotify_last_album_name", "text"),
    ):
        connection.execute(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {field} {sql_type}"
        )


def _create_existing_integrations_table(connection: psycopg.Connection) -> None:
    connection.execute(
        "CREATE TABLE spotify_integrations ("
        "user_id integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
        "spotify_user_id text, access_token text, refresh_token text, "
        "token_expires_at timestamptz, scope text, display_name text, "
        "is_connected boolean, is_playing boolean, last_checked_at timestamptz, "
        "last_track_id text, last_track_name text, last_artist_name text, "
        "last_album_name text, last_track_url text, last_album_image_url text)"
    )


def _assert_legacy_fields_removed(connection: psycopg.Connection) -> None:
    old_fields = set(_SPOTIFY_LEGACY_FIELDS)
    remaining = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'users'"
        )
    }
    assert old_fields.isdisjoint(remaining)


def _assert_model_encryption_contract(connection: psycopg.Connection) -> None:
    assert isinstance(SpotifyIntegration.__table__.c.access_token.type, EncryptedString)
    assert isinstance(
        SpotifyIntegration.__table__.c.refresh_token.type, EncryptedString
    )
    assert isinstance(SpotifyIntegration.__table__.c.access_token.type.impl, Text)
    assert isinstance(SpotifyIntegration.__table__.c.refresh_token.type.impl, Text)
    stored_types = dict(
        connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'spotify_integrations'"
        ).fetchall()
    )
    assert stored_types["access_token"] == "text"
    assert stored_types["refresh_token"] == "text"


def test_upgrade_copies_spotify_state_and_skips_empty_legacy_rows(
    spotify_scenario_urls: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _alembic_config(spotify_scenario_urls["alembic"])
    _prepare_parent_revision(
        config,
        spotify_scenario_urls["alembic"],
        spotify_scenario_urls["sync"],
        monkeypatch,
    )

    access_plain = f"access-{uuid4()}"
    refresh_plain = f"refresh-{uuid4()}"
    access = encrypt_string(access_plain)
    refresh = encrypt_string(refresh_plain)
    assert access is not None and refresh is not None
    expires_at = datetime(2026, 10, 24, 12, 30)
    checked_at = datetime(2026, 10, 23, 10, 15)
    complete_fields = _legacy_record(
        access=access,
        refresh=refresh,
        spotify_user_id=f"spotify-user-{uuid4()}",
        scope="user-read-playback-state",
        expires_at=expires_at,
        checked_at=checked_at,
        track_id=f"track-{uuid4()}",
        track_url="https://example.test/track/complete",
        album_image_url="https://example.test/image/complete",
        display_name="Legacy Spotify display name",
        is_connected=False,
        is_playing=True,
        track_name="Legacy track name",
        artist_name="Legacy artist name",
        album_name="Legacy album name",
    )
    partial_fields = _legacy_record(
        access=None,
        refresh=None,
        spotify_user_id=f"spotify-user-{uuid4()}",
        scope=None,
        expires_at=None,
        checked_at=None,
        track_id=None,
        track_url=None,
        album_image_url=None,
    )
    empty_fields = _legacy_record(
        access=None,
        refresh=None,
        spotify_user_id=None,
        scope=None,
        expires_at=None,
        checked_at=None,
        track_id=None,
        track_url=None,
        album_image_url=None,
    )

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _add_lowercase_role_values(connection)
        _add_optional_legacy_fields(connection)
        _insert_user(connection, 910001, complete_fields)
        _insert_user(connection, 910002, partial_fields)
        _insert_user(connection, 910003, empty_fields)

    command.upgrade(config, "148642dd1207")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _assert_legacy_fields_removed(connection)
        _assert_model_encryption_contract(connection)
        complete = connection.execute(
            "SELECT spotify_user_id, access_token, refresh_token, "
            "token_expires_at, scope, last_checked_at, last_track_id, "
            "last_track_url, last_album_image_url, display_name, is_connected, "
            "is_playing, last_track_name, last_artist_name, last_album_name "
            "FROM spotify_integrations WHERE user_id = %s",
            (910001,),
        ).fetchone()
        assert complete is not None
        assert complete[:3] == (
            complete_fields["spotify_user_id"],
            access,
            refresh,
        )
        assert complete[3] == expires_at.replace(tzinfo=UTC)
        assert complete[4] == complete_fields["spotify_scope"]
        assert complete[5] == checked_at.replace(tzinfo=UTC)
        assert complete[6:9] == (
            complete_fields["spotify_last_track_id"],
            complete_fields["spotify_last_track_url"],
            complete_fields["spotify_last_album_image_url"],
        )
        assert complete[9:] == (
            "Legacy Spotify display name",
            False,
            True,
            "Legacy track name",
            "Legacy artist name",
            "Legacy album name",
        )
        assert decrypt_string(complete[1]) == access_plain
        assert decrypt_string(complete[2]) == refresh_plain

        partial = connection.execute(
            "SELECT spotify_user_id, access_token, refresh_token, scope, "
            "token_expires_at, last_checked_at, last_track_id, last_track_url, "
            "last_album_image_url, is_connected, is_playing "
            "FROM spotify_integrations WHERE user_id = %s",
            (910002,),
        ).fetchone()
        assert partial == (
            partial_fields["spotify_user_id"],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            False,
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM spotify_integrations WHERE user_id = %s",
                (910003,),
            ).fetchone()[0]
            == 0
        )


def test_upgrade_copies_available_fields_from_a_partial_legacy_schema(
    spotify_scenario_urls: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _alembic_config(spotify_scenario_urls["alembic"])
    _prepare_parent_revision(
        config,
        spotify_scenario_urls["alembic"],
        spotify_scenario_urls["sync"],
        monkeypatch,
    )
    user_id = 915001
    track_id = f"partial-track-{uuid4()}"

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _add_lowercase_role_values(connection)
        connection.execute("ALTER TABLE users DROP COLUMN spotify_refresh_token")
        connection.execute(
            "INSERT INTO users (id, email, hashed_password, role, "
            "mfa_required, spotify_last_track_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                user_id,
                f"partial-{user_id}@example.test",
                "unused-migration-test-hash",
                "student",
                False,
                track_id,
            ),
        )

    command.upgrade(config, "148642dd1207")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _assert_legacy_fields_removed(connection)
        migrated = connection.execute(
            "SELECT access_token, refresh_token, last_track_id, is_connected, "
            "is_playing FROM spotify_integrations WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        assert migrated == (None, None, track_id, False, False)


def test_upgrade_does_not_overwrite_existing_spotify_integration_rows(
    spotify_scenario_urls: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _alembic_config(spotify_scenario_urls["alembic"])
    _prepare_parent_revision(
        config,
        spotify_scenario_urls["alembic"],
        spotify_scenario_urls["sync"],
        monkeypatch,
    )

    legacy_access = encrypt_string(f"legacy-access-{uuid4()}")
    legacy_refresh = encrypt_string(f"legacy-refresh-{uuid4()}")
    existing_access = encrypt_string(f"retained-access-{uuid4()}")
    existing_refresh = encrypt_string(f"retained-refresh-{uuid4()}")
    assert all(
        value is not None
        for value in (legacy_access, legacy_refresh, existing_access, existing_refresh)
    )
    existing_user_id = 920001
    new_user_id = 920002
    legacy_fields = _legacy_record(
        access=legacy_access,
        refresh=legacy_refresh,
        spotify_user_id=f"legacy-user-{uuid4()}",
        scope="legacy-scope",
        expires_at=datetime(2026, 10, 24, 12, 30),
        checked_at=datetime(2026, 10, 23, 10, 15),
        track_id=f"legacy-track-{uuid4()}",
        track_url="https://example.test/track/legacy",
        album_image_url="https://example.test/image/legacy",
    )
    new_fields = _legacy_record(
        access=legacy_access,
        refresh=legacy_refresh,
        spotify_user_id=f"new-user-{uuid4()}",
        scope="new-scope",
        expires_at=datetime(2026, 10, 24, 12, 30),
        checked_at=datetime(2026, 10, 23, 10, 15),
        track_id=f"new-track-{uuid4()}",
        track_url="https://example.test/track/new",
        album_image_url="https://example.test/image/new",
    )

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _add_lowercase_role_values(connection)
        _add_optional_legacy_fields(connection)
        _insert_user(connection, existing_user_id, legacy_fields)
        _insert_user(connection, new_user_id, new_fields)
        _create_existing_integrations_table(connection)
        connection.execute(
            "INSERT INTO spotify_integrations ("
            "user_id, spotify_user_id, access_token, refresh_token, scope, "
            "display_name, is_connected, is_playing, last_track_id, "
            "last_track_name, last_artist_name, last_album_name, last_track_url, "
            "last_album_image_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s)",
            (
                existing_user_id,
                "retained-spotify-identity",
                existing_access,
                existing_refresh,
                "retained-scope",
                "retained-display-name",
                True,
                False,
                "retained-track-id",
                "retained-track-name",
                "retained-artist-name",
                "retained-album-name",
                "https://example.test/track/retained",
                "https://example.test/image/retained",
            ),
        )

    command.upgrade(config, "148642dd1207")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _assert_legacy_fields_removed(connection)
        _assert_model_encryption_contract(connection)
        retained = connection.execute(
            "SELECT spotify_user_id, access_token, refresh_token, scope, "
            "display_name, is_connected, is_playing, last_track_id, "
            "last_track_name, last_artist_name, last_album_name, last_track_url, "
            "last_album_image_url "
            "FROM spotify_integrations WHERE user_id = %s",
            (existing_user_id,),
        ).fetchone()
        assert retained == (
            "retained-spotify-identity",
            existing_access,
            existing_refresh,
            "retained-scope",
            "retained-display-name",
            True,
            False,
            "retained-track-id",
            "retained-track-name",
            "retained-artist-name",
            "retained-album-name",
            "https://example.test/track/retained",
            "https://example.test/image/retained",
        )
        assert decrypt_string(retained[1]) == decrypt_string(existing_access)
        assert decrypt_string(retained[2]) == decrypt_string(existing_refresh)

        inserted = connection.execute(
            "SELECT spotify_user_id, access_token, refresh_token, scope, "
            "last_track_id, last_track_url, last_album_image_url, "
            "is_connected, is_playing "
            "FROM spotify_integrations WHERE user_id = %s",
            (new_user_id,),
        ).fetchone()
        assert inserted == (
            new_fields["spotify_user_id"],
            legacy_access,
            legacy_refresh,
            "new-scope",
            new_fields["spotify_last_track_id"],
            new_fields["spotify_last_track_url"],
            new_fields["spotify_last_album_image_url"],
            True,
            False,
        )
        assert decrypt_string(inserted[1]) == decrypt_string(legacy_access)
        assert decrypt_string(inserted[2]) == decrypt_string(legacy_refresh)


@pytest.fixture
def legacy_preferences_config(
    spotify_scenario_urls: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> Config:
    """Restore the historical preference shape in a fresh, fixture-owned DB."""
    config = _alembic_config(spotify_scenario_urls["alembic"])
    monkeypatch.setenv("DATABASE_URL", spotify_scenario_urls["alembic"])
    command.upgrade(config, "f7aa476e968a")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        _add_lowercase_role_values(connection)
        # The normal ancestry removed these columns in 202511240001. Recreate
        # their original 23d991e593b5/202505250001 definitions to exercise the
        # surviving-legacy-columns branch that 148642dd1207 explicitly handles.
        connection.execute(
            "ALTER TABLE users "
            "ADD COLUMN dnd_enabled boolean NOT NULL DEFAULT false, "
            "ADD COLUMN dnd_start time without time zone, "
            "ADD COLUMN dnd_end time without time zone, "
            "ADD COLUMN timezone varchar(64)"
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO users (id, email, hashed_password, role, "
                "mfa_required, dnd_enabled, dnd_start, dnd_end, timezone) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        930001,
                        "preferences-930001@example.test",
                        "unused-migration-test-hash",
                        "student",
                        False,
                        True,
                        time(23, 45, 30, 123456),
                        time(6, 15, 1, 654321),
                        "Asia/Kathmandu",
                    ),
                    (
                        930002,
                        "preferences-930002@example.test",
                        "unused-migration-test-hash",
                        "student",
                        False,
                        False,
                        time(0),
                        time(0),
                        "Europe/Istanbul",
                    ),
                    (
                        930003,
                        "preferences-930003@example.test",
                        "unused-migration-test-hash",
                        "student",
                        False,
                        False,
                        None,
                        None,
                        "America/St_Johns",
                    ),
                ],
            )
    return config


def _assert_legacy_preferences_removed(connection: psycopg.Connection) -> None:
    remaining = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'users'"
        )
    }
    assert {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}.isdisjoint(remaining)


def test_upgrade_preserves_legacy_user_preferences(
    legacy_preferences_config: Config,
    spotify_scenario_urls: dict[str, str],
) -> None:
    """Do not discard quiet hours or timezone when creating user_preferences."""
    command.upgrade(legacy_preferences_config, "148642dd1207")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert version == ("148642dd1207",)
        migrated = connection.execute(
            "SELECT user_id, dnd_enabled, dnd_start, dnd_end, timezone "
            "FROM user_preferences ORDER BY user_id"
        ).fetchall()
        assert migrated == [
            (
                930001,
                True,
                time(23, 45, 30, 123456),
                time(6, 15, 1, 654321),
                "Asia/Kathmandu",
            ),
            (930002, False, time(0), time(0), "Europe/Istanbul"),
            (930003, False, None, None, "America/St_Johns"),
        ]
        _assert_legacy_preferences_removed(connection)


def test_upgrade_backfills_missing_preferences_without_overwriting_existing_rows(
    legacy_preferences_config: Config,
    spotify_scenario_urls: dict[str, str],
) -> None:
    """Existing destination rows win, including explicit false and NULL fields."""
    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        connection.execute(
            "CREATE TABLE user_preferences ("
            "user_id integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
            "dnd_enabled boolean NOT NULL, "
            "dnd_start time without time zone, "
            "dnd_end time without time zone, timezone varchar(64))"
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO user_preferences "
                "(user_id, dnd_enabled, dnd_start, dnd_end, timezone) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    (930001, False, None, None, None),
                    (930003, True, time(11, 30), time(12, 30), "Pacific/Chatham"),
                ],
            )

    command.upgrade(legacy_preferences_config, "148642dd1207")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert version == ("148642dd1207",)
        migrated = connection.execute(
            "SELECT user_id, dnd_enabled, dnd_start, dnd_end, timezone "
            "FROM user_preferences ORDER BY user_id"
        ).fetchall()
        assert migrated == [
            (930001, False, None, None, None),
            (930002, False, time(0), time(0), "Europe/Istanbul"),
            (930003, True, time(11, 30), time(12, 30), "Pacific/Chatham"),
        ]
        _assert_legacy_preferences_removed(connection)


def test_null_legacy_enabled_aborts_upgrade_without_losing_preferences(
    legacy_preferences_config: Config,
    spotify_scenario_urls: dict[str, str],
) -> None:
    """An incompatible legacy NULL must abort, not be replaced or discarded."""
    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        connection.execute("ALTER TABLE users ALTER COLUMN dnd_enabled DROP NOT NULL")
        connection.execute("UPDATE users SET dnd_enabled = NULL WHERE id = 930002")
        original = connection.execute(
            "SELECT id, dnd_enabled, dnd_start, dnd_end, timezone "
            "FROM users ORDER BY id"
        ).fetchall()

    with pytest.raises(sa.exc.IntegrityError, match="dnd_enabled"):
        command.upgrade(legacy_preferences_config, "148642dd1207")

    with psycopg.connect(spotify_scenario_urls["sync"]) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("f7aa476e968a",)
        assert connection.execute(
            "SELECT to_regclass('public.user_preferences')"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'groups' "
            "AND column_name = 'id'"
        ).fetchone() == ("character varying",)
        assert (
            connection.execute(
                "SELECT id, dnd_enabled, dnd_start, dnd_end, timezone "
                "FROM users ORDER BY id"
            ).fetchall()
            == original
        )


# This diagnostic is deliberately test-only. It does not alter the production
# renderer, scanner configuration, migration, or exception policy.
_TRACE_TABLE_DDL = """
CREATE SCHEMA aud148_diag;
CREATE TABLE aud148_diag.executed_ddl (
    ordinal bigint GENERATED ALWAYS AS IDENTITY,
    outer_ordinal integer NOT NULL,
    site text NOT NULL,
    ddl text NOT NULL
)
"""
_TRACE_FIXTURE_DDL = """
CREATE SCHEMA aud148_fixture;
INSERT INTO public.groups (id, name) VALUES ('1', 'first'), ('02', 'second');
CREATE TABLE aud148_fixture.child_cascade (
    id integer PRIMARY KEY,
    group_id varchar(20),
    CONSTRAINT aud148_child_cascade_fk FOREIGN KEY (group_id)
        REFERENCES public.groups(id) ON UPDATE CASCADE ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE aud148_fixture."child quoted" (
    id integer PRIMARY KEY,
    "group key" varchar(20),
    CONSTRAINT aud148_child_quoted_fk FOREIGN KEY ("group key")
        REFERENCES public.groups(id) MATCH FULL ON DELETE SET NULL
);
CREATE TABLE aud148_fixture.child_unvalidated (
    id integer PRIMARY KEY,
    group_id varchar(20)
);
INSERT INTO aud148_fixture.child_cascade VALUES (1, '1'), (2, NULL);
INSERT INTO aud148_fixture."child quoted" VALUES (1, '02'), (2, NULL)
"""
_CATALOG_QUERIES = {
    "schemas": """
        SELECT nspname, nspowner::regrole::text, nspacl::text
        FROM pg_namespace
        WHERE nspname !~ '^pg_' AND nspname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY nspname
    """,
    "relations": """
        SELECT n.nspname, c.relname, c.relkind, c.relpersistence,
               c.relowner::regrole::text, c.relacl::text, c.reloptions,
               c.relrowsecurity, c.relforcerowsecurity,
               pg_get_expr(c.relpartbound, c.oid),
               obj_description(c.oid, 'pg_class')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY n.nspname, c.relname
    """,
    "columns": """
        SELECT n.nspname, c.relname, a.attnum, a.attname,
               format_type(a.atttypid, a.atttypmod), a.attnotnull,
               a.attidentity, a.attgenerated,
               pg_get_expr(d.adbin, d.adrelid)
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE a.attnum > 0 AND NOT a.attisdropped
          AND n.nspname !~ '^pg_' AND n.nspname NOT IN
              ('information_schema', 'aud148_diag')
        ORDER BY n.nspname, c.relname, a.attnum
    """,
    "constraints": """
        SELECT n.nspname, c.relname, k.conname, k.contype,
               k.convalidated, k.condeferrable, k.condeferred,
               pg_get_constraintdef(k.oid, true)
        FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY n.nspname, c.relname, k.conname
    """,
    "indexes": """
        SELECT n.nspname, t.relname, i.relname, x.indisprimary, x.indisunique,
               x.indisvalid, x.indisready, x.indislive, pg_get_indexdef(i.oid)
        FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY n.nspname, t.relname, i.relname
    """,
    "triggers": """
        SELECT n.nspname, c.relname, t.tgisinternal,
               CASE WHEN t.tgisinternal THEN NULL ELSE t.tgname END,
               k.conname, p.proname, t.tgtype, t.tgenabled,
               encode(t.tgargs, 'hex'),
               CASE WHEN t.tgisinternal THEN NULL
                    ELSE pg_get_triggerdef(t.oid, true) END
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_proc p ON p.oid = t.tgfoid
        LEFT JOIN pg_constraint k ON k.oid = t.tgconstraint
        WHERE n.nspname !~ '^pg_' AND n.nspname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY 1, 2, 3, 4, 5, 6, 7, 8, 9
    """,
    "enum_labels": """
        SELECT n.nspname, t.typname, e.enumsortorder, e.enumlabel
        FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY n.nspname, t.typname, e.enumsortorder
    """,
    "policies": """
        SELECT schemaname, tablename, policyname, permissive, roles,
               cmd, qual, with_check
        FROM pg_policies
        WHERE schemaname !~ '^pg_' AND schemaname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY schemaname, tablename, policyname
    """,
    "sequences": """
        SELECT schemaname, sequencename, sequenceowner, data_type::text,
               start_value, min_value, max_value, increment_by, cycle,
               cache_size, last_value
        FROM pg_sequences
        WHERE schemaname !~ '^pg_' AND schemaname NOT IN
            ('information_schema', 'aud148_diag')
        ORDER BY schemaname, sequencename
    """,
}


def _prepare_ddl_inventory(
    urls, monkeypatch, *, orphan=False, integer_key=False, duplicate_index=True
) -> Config:
    config = _alembic_config(urls["alembic"])
    monkeypatch.setenv("DATABASE_URL", urls["alembic"])
    command.upgrade(config, "f7aa476e968a")
    with psycopg.connect(urls["sync"]) as connection:
        _add_lowercase_role_values(connection)
        if integer_key:
            assert not orphan
            connection.execute(
                "ALTER TABLE groups ALTER COLUMN id TYPE INTEGER USING id::integer"
            )
        connection.execute(_TRACE_TABLE_DDL)
        fixture_ddl = (
            _TRACE_FIXTURE_DDL.replace("varchar(20)", "integer")
            if integer_key
            else _TRACE_FIXTURE_DDL
        )
        connection.execute(fixture_ddl)
        connection.execute(
            "INSERT INTO aud148_fixture.child_unvalidated VALUES (1, %s)",
            ("99" if orphan else "02",),
        )
        connection.execute(
            "ALTER TABLE aud148_fixture.child_unvalidated "
            "ADD CONSTRAINT aud148_child_unvalidated_fk FOREIGN KEY (group_id) "
            "REFERENCES public.groups(id) NOT VALID"
        )
        if integer_key:
            connection.execute(
                "ALTER TABLE aud148_fixture.child_unvalidated "
                "VALIDATE CONSTRAINT aud148_child_unvalidated_fk"
            )
        if not duplicate_index:
            connection.execute("DROP INDEX IF EXISTS ix_groups_id")
    return config


def _inventory_snapshot(sync_url):
    """Compare user catalogs and row digests, never emit application row data."""
    with psycopg.connect(sync_url) as connection:
        connection.execute("SET search_path = public")
        trace_objects = connection.execute(
            "SELECT c.relname, c.relkind FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'aud148_diag' ORDER BY c.relname"
        ).fetchall()
        assert trace_objects == [
            ("executed_ddl", "r"),
            ("executed_ddl_ordinal_seq", "S"),
        ]
        catalog = {
            name: connection.execute(query).fetchall()
            for name, query in _CATALOG_QUERIES.items()
        }
        tables = connection.execute(
            "SELECT n.nspname, c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind IN ('r', 'p') AND n.nspname !~ '^pg_' "
            "AND n.nspname NOT IN ('information_schema', 'aud148_diag') "
            "ORDER BY n.nspname, c.relname"
        ).fetchall()
        data = {}
        for namespace, table in tables:
            rows = connection.execute(
                sql.SQL(
                    "SELECT to_jsonb(row)::text FROM {} AS row "
                    "ORDER BY to_jsonb(row)::text LIMIT 1001"
                ).format(sql.Identifier(namespace, table))
            ).fetchall()
            assert len(rows) <= 1000, "Only bounded synthetic fixtures are supported"
            encoded = json.dumps(rows, ensure_ascii=True).encode("utf-8")
            data[namespace + "." + table] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        sequence_state = {}
        for row in catalog["sequences"]:
            namespace, sequence = row[:2]
            sequence_state[namespace + "." + sequence] = connection.execute(
                sql.SQL("SELECT last_value, is_called FROM {}").format(
                    sql.Identifier(namespace, sequence)
                )
            ).fetchone()
        # OIDs and autogenerated RI trigger names are represented by stable
        # qualified objects, constraint names and trigger action functions.
        return {
            "catalog": catalog,
            "data": data,
            "sequence_state": sequence_state,
        }


def _execute_ddl_inventory(config, urls, recorder, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", urls["alembic"])
    actual_blob = ddl_trace.git_blob_id(ddl_trace.MIGRATION_PATH.read_bytes())
    assert actual_blob == ddl_trace.SOURCE_GIT_BLOB
    engine = sa.create_engine(urls["alembic"])
    listeners = (
        ("begin", recorder.on_begin, {}),
        ("commit", recorder.on_commit, {}),
        ("rollback", recorder.on_rollback, {}),
        ("before_cursor_execute", recorder.before_cursor_execute, {"retval": True}),
    )
    try:
        with engine.connect() as connection:
            for name, listener, options in listeners:
                event.listen(connection, name, listener, **options)
            config.attributes["connection"] = connection
            try:
                command.upgrade(config, "148642dd1207")
            finally:
                # Keep listeners installed through cleanup of a failed operation.
                if connection.in_transaction():
                    connection.rollback()
                config.attributes.pop("connection", None)
                for name, listener, _ in reversed(listeners):
                    event.remove(connection, name, listener)
    finally:
        engine.dispose()


def test_expanded_ddl_inventory_matches_unmodified_populated_control(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Produce inventory, not a waiver, after proving instrumentation equivalence."""
    source = ddl_trace.MIGRATION_PATH.read_bytes()
    ddl_trace.reviewed_sites(source)
    with (
        _owned_migration_scenario(migration_postgres) as control_urls,
        _owned_migration_scenario(migration_postgres) as traced_urls,
    ):
        control_config = _prepare_ddl_inventory(control_urls, monkeypatch)
        traced_config = _prepare_ddl_inventory(traced_urls, monkeypatch)
        control_before = _inventory_snapshot(control_urls["sync"])
        traced_before = _inventory_snapshot(traced_urls["sync"])
        assert control_before == traced_before
        control = ddl_trace.ExpandedDdlTrace(source, instrument=False)
        traced = ddl_trace.ExpandedDdlTrace(source, instrument=True)
        _execute_ddl_inventory(control_config, control_urls, control, monkeypatch)
        _execute_ddl_inventory(traced_config, traced_urls, traced, monkeypatch)

        assert control.replacements == []
        assert control.events == traced.events
        control_snapshot = _inventory_snapshot(control_urls["sync"])
        traced_snapshot = _inventory_snapshot(traced_urls["sync"])
        assert control_snapshot == traced_snapshot
        assert [e["kind"] for e in traced.events].count("begin") == 1
        assert [e["kind"] for e in traced.events].count("commit") == 1
        assert not any(e["kind"] == "rollback" for e in traced.events)

        with psycopg.connect(control_urls["sync"]) as connection:
            assert connection.execute(
                "SELECT count(*) FROM aud148_diag.executed_ddl"
            ).fetchone() == (0,)
        with psycopg.connect(traced_urls["sync"]) as connection:
            rows = connection.execute(
                "SELECT outer_ordinal, site, ddl "
                "FROM aud148_diag.executed_ddl ORDER BY ordinal"
            ).fetchall()
            assert connection.execute(
                "SELECT id FROM public.groups ORDER BY id"
            ).fetchall() == [(1,), (2,)]
            assert connection.execute(
                'SELECT "group key" FROM aud148_fixture."child quoted" WHERE id = 1'
            ).fetchone() == (2,)
            assert connection.execute(
                "SELECT convalidated FROM pg_constraint "
                "WHERE conname = 'aud148_child_unvalidated_fk'"
            ).fetchone() == (True,)
            postgres_version = connection.execute("SELECT version()").fetchone()[0]

        assert len(rows) <= 100, "The nested DDL fixture inventory must stay finite"
        expanded = traced.expanded_sql(rows)
        statements = [row[2] for row in rows]
        assert "ALTER TABLE groups DROP COLUMN id" in statements
        assert "ALTER TABLE groups DROP COLUMN id__integer" in statements
        assert any(
            statement.startswith(
                'ALTER TABLE aud148_fixture."child quoted" ALTER COLUMN "group key" '
                "TYPE INTEGER"
            )
            for statement in statements
        )
        assert (
            sum(
                site == "child_fk_restore" and "aud148_fixture." in statement
                for _, site, statement in rows
            )
            == 3
        )

        sql_path = tmp_path / "148642dd1207.expanded.sql"
        evidence_path = tmp_path / "148642dd1207.trace.json"
        sql_path.write_text(expanded, encoding="utf-8")
        evidence = {
            "status": "diagnostic-only-not-an-exception",
            "migration_blob": ddl_trace.SOURCE_GIT_BLOB,
            "helper_sha256": hashlib.sha256(
                Path(ddl_trace.__file__).read_bytes()
            ).hexdigest(),
            "fixture_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "workflow_sha": os.getenv("GITHUB_SHA"),
            "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
            "postgres_version": postgres_version,
            "excluded_objects": [
                "aud148_diag",
                "aud148_diag.executed_ddl",
                "aud148_diag.executed_ddl_ordinal_seq",
            ],
            "original_cursor_events": traced.events,
            "replacements": traced.replacements,
            "nested_ddl": [
                {
                    "outer_ordinal": ordinal,
                    "site": site,
                    "sql": statement,
                    "sql_sha256": hashlib.sha256(statement.encode("utf-8")).hexdigest(),
                }
                for ordinal, site, statement in rows
            ],
            "equivalent_snapshot": traced_snapshot,
            "expanded_sql_sha256": hashlib.sha256(expanded.encode("utf-8")).hexdigest(),
        }
        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print("AUD148_EXPANDED_SQL=" + str(sql_path))
        print("AUD148_TRACE_EVIDENCE=" + str(evidence_path))


def test_convertible_orphan_rolls_back_cutover_and_diagnostic_rows(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure after key replacement is not successful trace-inventory evidence."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(urls, monkeypatch, orphan=True)
        before = _inventory_snapshot(urls["sync"])
        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=True
        )
        with pytest.raises(sa.exc.IntegrityError, match="aud148_child_unvalidated_fk"):
            _execute_ddl_inventory(config, urls, recorder, monkeypatch)
        assert _inventory_snapshot(urls["sync"]) == before
        assert any(event["kind"] == "rollback" for event in recorder.events)
        assert not any(event["kind"] == "commit" for event in recorder.events)
        assert {row["site"] for row in recorder.replacements} == {
            site.name for site in recorder.sites
        }
        with psycopg.connect(urls["sync"]) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("f7aa476e968a",)
            assert connection.execute(
                "SELECT count(*) FROM aud148_diag.executed_ddl"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT convalidated FROM pg_constraint "
                "WHERE conname = 'aud148_child_unvalidated_fk'"
            ).fetchone() == (False,)
        with pytest.raises(ddl_trace.TraceContractError, match="one transaction"):
            recorder.expanded_sql([])


def _shadow_check_catalog(connection):
    return connection.execute(
        "SELECT c.contype::text, c.convalidated, pg_get_constraintdef(c.oid), "
        "pg_get_expr(c.conbin, c.conrelid), c.conkey, a.attnum "
        "FROM pg_constraint c JOIN pg_attribute a "
        "ON a.attrelid = c.conrelid AND a.attname = 'id__integer' "
        "WHERE c.conrelid = 'public.groups'::regclass "
        "AND c.conname = 'ck_groups_id_shadow_not_null'"
    ).fetchone()


@pytest.mark.parametrize("validated", [True, False], ids=["validated", "not_valid"])
def test_existing_exact_shadow_check_is_reused_from_real_pg_catalog(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    validated: bool,
) -> None:
    """Catalog output, rather than a simplified mock, defines the reuse contract."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(urls, monkeypatch)
        with psycopg.connect(urls["sync"]) as connection:
            connection.execute("ALTER TABLE groups ADD COLUMN id__integer integer")
            connection.execute("UPDATE groups SET id__integer = id::integer")
            definition = "CHECK (id__integer IS NOT NULL)"
            if not validated:
                definition += " NOT VALID"
            connection.execute(
                sql.SQL(
                    "ALTER TABLE groups ADD CONSTRAINT ck_groups_id_shadow_not_null {}"
                ).format(sql.SQL(definition))
            )
            catalog = _shadow_check_catalog(connection)
            assert catalog is not None
            assert catalog[0] == "c"
            assert catalog[1] is validated
            assert catalog[4] == [catalog[5]]
            assert catalog[3] == "(id__integer IS NOT NULL)"
            assert catalog[2].endswith(" NOT VALID") is (not validated)

        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=False
        )
        _execute_ddl_inventory(config, urls, recorder, monkeypatch)
        statements = [e["sql"] for e in recorder.events if e["kind"] == "cursor"]
        assert not any(
            "ADD CONSTRAINT ck_groups_id_shadow_not_null" in statement
            for statement in statements
        )
        assert [e["kind"] for e in recorder.events].count("commit") == 1
        assert not any(e["kind"] == "rollback" for e in recorder.events)
        with psycopg.connect(urls["sync"]) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("148642dd1207",)
            assert connection.execute(
                "SELECT id, name FROM groups ORDER BY id"
            ).fetchall() == [(1, "first"), (2, "second")]
            assert connection.execute(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid = 'public.groups'::regclass "
                "AND conname = 'ck_groups_id_shadow_not_null'"
            ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("case", "definition", "constraint_type", "same_column"),
    [
        ("weaker", "CHECK (id__integer > 0)", "c", True),
        ("wrong_type", "UNIQUE (id__integer)", "u", True),
        ("wrong_column", "CHECK (other_integer IS NOT NULL)", "c", False),
        ("quoted_uppercase", 'CHECK ("ID__INTEGER" IS NOT NULL)', "c", False),
    ],
    ids=["weaker", "wrong_type", "wrong_column", "quoted_uppercase"],
)
def test_existing_shadow_check_rejects_wrong_real_pg_catalog_identity(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    definition: str,
    constraint_type: str,
    same_column: bool,
) -> None:
    """A same-name constraint must protect the exact lowercase shadow column."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(urls, monkeypatch)
        with psycopg.connect(urls["sync"]) as connection:
            connection.execute(
                "ALTER TABLE groups ADD COLUMN id__integer integer, "
                "ADD COLUMN other_integer integer DEFAULT 900, "
                'ADD COLUMN "ID__INTEGER" integer DEFAULT 901'
            )
            connection.execute("UPDATE groups SET id__integer = id::integer")
            connection.execute(
                sql.SQL(
                    "ALTER TABLE groups ADD CONSTRAINT ck_groups_id_shadow_not_null {}"
                ).format(sql.SQL(definition))
            )
            catalog = _shadow_check_catalog(connection)
            assert catalog is not None
            assert catalog[0] == constraint_type
            assert catalog[1] is True
            assert (catalog[4] == [catalog[5]]) is same_column
            if case == "quoted_uppercase":
                assert catalog[3] == '("ID__INTEGER" IS NOT NULL)'

        before = _inventory_snapshot(urls["sync"])
        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=False
        )
        with pytest.raises(RuntimeError, match="does not match"):
            _execute_ddl_inventory(config, urls, recorder, monkeypatch)
        assert _inventory_snapshot(urls["sync"]) == before
        assert any(e["kind"] == "rollback" for e in recorder.events)
        assert not any(e["kind"] == "commit" for e in recorder.events)
        assert not any(
            "CREATE TEMP TABLE _groups_fk_restore" in e.get("sql", "")
            for e in recorder.events
        )
        with psycopg.connect(urls["sync"]) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("f7aa476e968a",)


def test_stale_shadow_value_aborts_before_fk_capture_with_exact_rollback(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backfilling a NULL neighbor must roll back with a rejected stale value."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(urls, monkeypatch)
        with psycopg.connect(urls["sync"]) as connection:
            connection.execute("ALTER TABLE groups ADD COLUMN id__integer integer")
            connection.execute("UPDATE groups SET id__integer = 999 WHERE id = '1'")
        before = _inventory_snapshot(urls["sync"])
        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=False
        )

        with pytest.raises(sa.exc.DBAPIError, match="does not match the validated"):
            _execute_ddl_inventory(config, urls, recorder, monkeypatch)

        assert _inventory_snapshot(urls["sync"]) == before
        assert any(e["kind"] == "rollback" for e in recorder.events)
        assert not any(e["kind"] == "commit" for e in recorder.events)
        assert not any(
            "CREATE TEMP TABLE _groups_fk_restore" in e.get("sql", "")
            for e in recorder.events
        )
        with psycopg.connect(urls["sync"]) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("f7aa476e968a",)
            assert connection.execute(
                "SELECT id, id__integer FROM groups ORDER BY id"
            ).fetchall() == [("02", None), ("1", 999)]


def test_shadow_cutover_omits_only_transient_validation_after_null_backfill(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep guards, locking and final-key validation without a redundant scan."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(urls, monkeypatch)
        with psycopg.connect(urls["sync"]) as connection:
            connection.execute("ALTER TABLE groups ADD COLUMN id__integer integer")
            assert connection.execute(
                "SELECT count(*) FROM groups WHERE id__integer IS NULL"
            ).fetchone() == (2,)

        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=False
        )
        original_before_cursor = recorder.before_cursor_execute
        shadow_check = (
            "ALTER TABLE groups ADD CONSTRAINT ck_groups_id_shadow_not_null "
            "CHECK (id__integer IS NOT NULL) NOT VALID"
        )
        exclusion_locks = []

        def observe_check(connection, cursor, statement, parameters, context, many):
            if statement == shadow_check:
                pid = connection.connection.driver_connection.info.backend_pid
                with psycopg.connect(urls["sync"], connect_timeout=5) as observer:
                    observer.execute("SET LOCAL statement_timeout = '2s'")
                    exclusion_locks.append(
                        observer.execute(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks "
                            "WHERE pid = %s AND relation = 'public.groups'::regclass "
                            "AND mode = 'AccessExclusiveLock' AND granted)",
                            (pid,),
                        ).fetchone()[0]
                    )
            return original_before_cursor(
                connection, cursor, statement, parameters, context, many
            )

        monkeypatch.setattr(recorder, "before_cursor_execute", observe_check)
        _execute_ddl_inventory(config, urls, recorder, monkeypatch)
        assert exclusion_locks == [True]
        kinds = [e["kind"] for e in recorder.events]
        assert kinds.count("begin") == kinds.count("commit") == 1
        assert "rollback" not in kinds
        statements = [e["sql"] for e in recorder.events if e["kind"] == "cursor"]
        source_guard = next(
            i
            for i, statement in enumerate(statements)
            if "groups.id contains a value that cannot be converted" in statement
        )
        equality_guard = next(
            i
            for i, statement in enumerate(statements)
            if "id__integer IS DISTINCT FROM id::integer" in statement
        )
        capture = next(
            i
            for i, statement in enumerate(statements)
            if "CREATE TEMP TABLE _groups_fk_restore ON COMMIT DROP" in statement
        )
        fill = statements.index(
            "UPDATE groups SET id__integer = id::integer WHERE id__integer IS NULL"
        )
        final_validation = statements.index(
            "ALTER TABLE groups VALIDATE CONSTRAINT ck_groups_id_not_null"
        )
        primary_key = statements.index(
            "ALTER TABLE groups ADD CONSTRAINT groups_pkey "
            "PRIMARY KEY USING INDEX groups_pkey_idx"
        )
        assert (
            source_guard
            < fill
            < equality_guard
            < statements.index(shadow_check)
            < capture
            < final_validation
            < primary_key
        )
        assert (
            statements.index("SET LOCAL lock_timeout = '10s'")
            < statements.index("SET LOCAL statement_timeout = '60s'")
            < source_guard
        )
        assert any(
            "pg_advisory_xact_lock(824148642)" in statement
            for statement in statements[:source_guard]
        )
        with psycopg.connect(urls["sync"]) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("148642dd1207",)
            assert connection.execute(
                "SELECT id, name FROM groups ORDER BY id"
            ).fetchall() == [(1, "first"), (2, "second")]
            assert connection.execute(
                "SELECT attnotnull FROM pg_attribute "
                "WHERE attrelid = 'public.groups'::regclass AND attname = 'id'"
            ).fetchone() == (True,)
            assert connection.execute(
                "SELECT count(*) FROM pg_attribute "
                "WHERE attrelid = 'public.groups'::regclass "
                "AND attname = 'id__integer' AND NOT attisdropped"
            ).fetchone() == (0,)

        assert [
            statement
            for statement in statements
            if statement.startswith("ALTER TABLE ")
            and "VALIDATE CONSTRAINT" in statement
        ] == [
            "ALTER TABLE groups VALIDATE CONSTRAINT ck_groups_id_not_null",
            "ALTER TABLE active_sessions VALIDATE CONSTRAINT "
            "ck_active_sessions_signing_key_not_null",
        ]


def _assert_groups_primary_key(connection) -> None:
    """Prove the PK owns a valid, ready, exact one-column btree on groups.id."""
    assert connection.execute(
        """
        SELECT c.conname, i.relname,
               c.convalidated AND c.conkey = ARRAY[a.attnum]
               AND x.indisprimary AND x.indisunique
               AND x.indisvalid AND x.indisready AND x.indislive
               AND x.indnkeyatts = 1 AND x.indnatts = 1
               AND x.indkey[0] = a.attnum
               AND x.indexprs IS NULL AND x.indpred IS NULL
               AND am.amname = 'btree' AND a.attnotnull
        FROM pg_constraint c
        JOIN pg_index x ON x.indexrelid = c.conindid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_am am ON am.oid = i.relam
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attname = 'id'
        WHERE c.conrelid = 'public.groups'::regclass AND c.contype = 'p'
        """
    ).fetchall() == [("groups_pkey", "groups_pkey", True)]


def _assert_group_fixture_foreign_keys(connection) -> None:
    assert connection.execute(
        """
        SELECT conname, convalidated, condeferrable, condeferred,
               confmatchtype, confupdtype, confdeltype
        FROM pg_constraint
        WHERE connamespace = 'aud148_fixture'::regnamespace AND contype = 'f'
        ORDER BY conname
        """
    ).fetchall() == [
        ("aud148_child_cascade_fk", True, True, True, "s", "c", "c"),
        ("aud148_child_quoted_fk", True, False, False, "f", "a", "n"),
        ("aud148_child_unvalidated_fk", True, False, False, "s", "a", "a"),
    ]


def _assert_groups_key_dml(connection) -> None:
    """Exercise constraints, then roll back all probe writes."""
    with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
        connection.execute("INSERT INTO groups (id, name) VALUES (1, 'duplicate')")
    with pytest.raises(psycopg.errors.NotNullViolation), connection.transaction():
        connection.execute("INSERT INTO groups (id, name) VALUES (NULL, 'null key')")
    with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
        connection.execute('INSERT INTO aud148_fixture."child quoted" VALUES (99, 99)')

    connection.execute("UPDATE groups SET id = 11 WHERE id = 1")
    assert connection.execute(
        "SELECT group_id FROM aud148_fixture.child_cascade WHERE id = 1"
    ).fetchone() == (11,)
    connection.execute("DELETE FROM groups WHERE id = 11")
    assert connection.execute(
        "SELECT count(*) FROM aud148_fixture.child_cascade WHERE id = 1"
    ).fetchone() == (0,)
    connection.execute(
        "UPDATE aud148_fixture.child_unvalidated SET group_id = NULL WHERE id = 1"
    )
    connection.execute("DELETE FROM groups WHERE id = 2")
    assert connection.execute(
        'SELECT "group key" FROM aud148_fixture."child quoted" WHERE id = 1'
    ).fetchone() == (None,)
    connection.rollback()


@pytest.mark.parametrize("integer_key", [False, True], ids=["legacy", "integer"])
@pytest.mark.parametrize("duplicate_index", [False, True], ids=["absent", "present"])
def test_groups_cutover_uses_only_the_exact_primary_key_index(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    integer_key: bool,
    duplicate_index: bool,
) -> None:
    """The conversion must not build a second btree already supplied by the PK."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(
            urls,
            monkeypatch,
            integer_key=integer_key,
            duplicate_index=duplicate_index,
        )
        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=False
        )
        _execute_ddl_inventory(config, urls, recorder, monkeypatch)
        kinds = [event["kind"] for event in recorder.events]
        assert kinds.count("begin") == kinds.count("commit") == 1
        assert "rollback" not in kinds
        statements = [
            event["sql"] for event in recorder.events if event["kind"] == "cursor"
        ]
        assert statements.count("DROP INDEX IF EXISTS ix_groups_id") == int(
            duplicate_index
        )
        if not integer_key:
            assert (
                statements.index(
                    "ALTER TABLE groups VALIDATE CONSTRAINT ck_groups_id_not_null"
                )
                < statements.index(
                    "CREATE UNIQUE INDEX IF NOT EXISTS groups_pkey_idx ON groups (id)"
                )
                < statements.index(
                    "ALTER TABLE groups ADD CONSTRAINT groups_pkey "
                    "PRIMARY KEY USING INDEX groups_pkey_idx"
                )
            )
        with psycopg.connect(urls["sync"]) as connection:
            _assert_groups_primary_key(connection)
            _assert_group_fixture_foreign_keys(connection)
            assert connection.execute(
                "SELECT id, name FROM groups ORDER BY id"
            ).fetchall() == [(1, "first"), (2, "second")]
            assert connection.execute(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'public.groups'::regclass AND attname = 'id'"
            ).fetchone() == ("integer",)
            assert connection.execute(
                "SELECT attname FROM pg_attribute "
                "WHERE attrelid = 'public.groups'::regclass AND NOT attisdropped "
                "AND attname IN ('id__integer', 'id__varchar')"
            ).fetchall() == []
            assert connection.execute(
                "SELECT to_regclass('public.groups_pkey_idx')"
            ).fetchone() == (None,)
            _assert_groups_key_dml(connection)
            assert connection.execute(
                """
                SELECT i.relname
                FROM pg_index x
                JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attname = 'id'
                WHERE x.indrelid = 'public.groups'::regclass
                  AND a.attnum = ANY(x.indkey)
                ORDER BY i.relname
                """
            ).fetchall() == [("groups_pkey",)]
        assert (
            "CREATE INDEX IF NOT EXISTS ix_groups_id ON groups (id)" not in statements
        )


@pytest.mark.parametrize("duplicate_index", [False, True], ids=["absent", "present"])
def test_groups_index_cutover_failure_restores_exact_catalog_and_data(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    duplicate_index: bool,
) -> None:
    """A late FK rejection rolls back the PK and every original index exactly."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(
            urls, monkeypatch, orphan=True, duplicate_index=duplicate_index
        )
        before = _inventory_snapshot(urls["sync"])
        recorder = ddl_trace.ExpandedDdlTrace(
            ddl_trace.MIGRATION_PATH.read_bytes(), instrument=False
        )
        with pytest.raises(sa.exc.IntegrityError) as error:
            _execute_ddl_inventory(config, urls, recorder, monkeypatch)
        assert error.value.orig.sqlstate == "23503"
        kinds = [event["kind"] for event in recorder.events]
        assert kinds.count("begin") == kinds.count("rollback") == 1
        assert "commit" not in kinds
        statements = [
            event["sql"] for event in recorder.events if event["kind"] == "cursor"
        ]
        assert (
            "ALTER TABLE groups ADD CONSTRAINT groups_pkey "
            "PRIMARY KEY USING INDEX groups_pkey_idx"
        ) in statements
        assert _inventory_snapshot(urls["sync"]) == before


def _run_groups_key_helper(urls, *, downgrade: bool) -> None:
    """Run the real key helper in its own transaction, without stamping Alembic."""
    source = ddl_trace.MIGRATION_PATH.read_bytes()
    assert ddl_trace.git_blob_id(source) == ddl_trace.SOURCE_GIT_BLOB
    config = _alembic_config(urls["alembic"])
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("148642dd1207")
    assert revision is not None
    migration = revision.module
    engine = sa.create_engine(urls["alembic"])
    try:
        with engine.begin() as connection:
            with EnvironmentContext(config, scripts) as environment:
                environment.configure(connection=connection)
                with Operations.context(environment.get_context()):
                    helper = (
                        migration._postgresql_groups_id_downgrade
                        if downgrade
                        else migration._postgresql_groups_id_upgrade
                    )
                    helper(sa.inspect(connection))
                    assert connection.in_transaction()
    finally:
        engine.dispose()


@pytest.mark.parametrize("duplicate_index", [False, True], ids=["absent", "present"])
def test_groups_key_helper_round_trip_restores_legacy_index_and_foreign_keys(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    duplicate_index: bool,
) -> None:
    """This is a key-helper rollback control, not a full revision downgrade."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _prepare_ddl_inventory(urls, monkeypatch)
        command.upgrade(config, "148642dd1207")
        with psycopg.connect(urls["sync"]) as connection:
            if duplicate_index:
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS ix_groups_id ON groups (id)"
                )
            else:
                connection.execute("DROP INDEX IF EXISTS ix_groups_id")

        _run_groups_key_helper(urls, downgrade=True)
        with psycopg.connect(urls["sync"]) as connection:
            _assert_groups_primary_key(connection)
            _assert_group_fixture_foreign_keys(connection)
            assert connection.execute(
                "SELECT id, name FROM groups ORDER BY id"
            ).fetchall() == [("1", "first"), ("2", "second")]
            assert connection.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod), x.indisvalid,
                       x.indisready, x.indislive, x.indisunique
                FROM pg_index x
                JOIN pg_attribute a ON a.attrelid = x.indrelid
                  AND a.attnum = x.indkey[0]
                WHERE x.indexrelid = 'public.ix_groups_id'::regclass
                  AND x.indrelid = 'public.groups'::regclass
                  AND x.indnkeyatts = 1 AND a.attname = 'id'
                """
            ).fetchall() == [("character varying(20)", True, True, True, False)]
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("148642dd1207",)

        _run_groups_key_helper(urls, downgrade=False)
        with psycopg.connect(urls["sync"]) as connection:
            _assert_groups_primary_key(connection)
            _assert_group_fixture_foreign_keys(connection)
            assert connection.execute(
                "SELECT id, name FROM groups ORDER BY id"
            ).fetchall() == [(1, "first"), (2, "second")]
            _assert_groups_key_dml(connection)


@pytest.mark.parametrize("duplicate_index", [False, True], ids=["absent", "present"])
def test_groups_successors_do_not_require_the_duplicate_id_index(
    migration_postgres,
    monkeypatch: pytest.MonkeyPatch,
    duplicate_index: bool,
) -> None:
    """Exercise the real sequence and UUID chain on a canonical populated schema."""
    with _owned_migration_scenario(migration_postgres) as urls:
        config = _alembic_config(urls["alembic"])
        monkeypatch.setenv("DATABASE_URL", urls["alembic"])
        command.upgrade(config, "f7aa476e968a")
        with psycopg.connect(urls["sync"]) as connection:
            _add_lowercase_role_values(connection)
            connection.execute(
                "INSERT INTO groups (id, name) VALUES ('1', 'first'), ('02', 'second')"
            )
        command.upgrade(config, "148642dd1207")
        with psycopg.connect(urls["sync"]) as connection:
            # Stage each index state only in this isolated control database.
            if duplicate_index:
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS ix_groups_id ON groups (id)"
                )
            else:
                connection.execute("DROP INDEX IF EXISTS ix_groups_id")
            _assert_groups_primary_key(connection)
            connection.execute(
                "INSERT INTO users "
                "(id, email, hashed_password, role, mfa_required, group_id) "
                "VALUES (101, 'index-control@example.test', "
                "'unused-migration-test-hash', 'student', false, 1)"
            )

        command.upgrade(config, "2956fd6376cc")
        with psycopg.connect(urls["sync"]) as connection:
            assert connection.execute(
                "INSERT INTO groups (name) VALUES ('third') RETURNING id"
            ).fetchone() == (3,)
            assert connection.execute(
                "SELECT pg_get_serial_sequence('public.groups', 'id')"
            ).fetchone() == ("public.groups_id_seq",)

        command.upgrade(config, "202602010004")
        with psycopg.connect(urls["sync"]) as connection:
            _assert_groups_primary_key(connection)
            rows = connection.execute(
                "SELECT name, id::text, pg_typeof(id)::text FROM groups ORDER BY name"
            ).fetchall()
            assert [row[0] for row in rows] == ["first", "second", "third"]
            assert all(row[2] == "uuid" for row in rows)
            assert len({UUID(row[1]) for row in rows}) == 3
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone() == ("202602010004",)
            assert connection.execute(
                "SELECT attname FROM pg_attribute "
                "WHERE attrelid = 'public.groups'::regclass "
                "AND attname = 'legacy_id' AND NOT attisdropped"
            ).fetchall() == []
            assert connection.execute(
                "SELECT g.name, pg_typeof(u.group_id)::text "
                "FROM users u JOIN groups g ON g.id = u.group_id "
                "WHERE u.email = 'index-control@example.test'"
            ).fetchall() == [("first", "uuid")]
