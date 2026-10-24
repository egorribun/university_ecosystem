"""PostgreSQL regressions for the 148642dd1207 shadow-key conversion."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from psycopg import sql
from sqlalchemy import Text
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


@pytest.fixture
def spotify_scenario_urls(migration_postgres) -> Iterator[dict[str, str]]:
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
