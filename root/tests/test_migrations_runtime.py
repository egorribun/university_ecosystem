from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.database import Base
from app.models import (
    models,  # noqa: F401  # ensure tables are registered with Base metadata
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_config(
    tmp_path: Path, name: str, use_async: bool = True
) -> tuple[Config, str]:
    db_path = tmp_path / name
    async_url = f"sqlite+aiosqlite:///{db_path}"
    sync_url = f"sqlite:///{db_path}?timeout=30"
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))

    target_url = async_url if use_async else sync_url
    config.set_main_option("sqlalchemy.url", target_url)

    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target_url
    config.attributes["_previous_database_url"] = previous_url
    return config, sync_url


def _inspect(url: str) -> sa.engine.Engine:
    return sa.create_engine(url, poolclass=sa.pool.NullPool)


@pytest.mark.parametrize(
    "dbname",
    ["clean.sqlite", "idempotent.sqlite"],
)
def test_alembic_upgrade_head(tmp_path, dbname):
    config, sync_url = _make_config(tmp_path, dbname)
    engine = _inspect(sync_url)
    if "idempotent" in dbname:
        metadata = sa.MetaData()
        sa.Table(
            "users",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
        )
        sa.Table(
            "push_subscriptions",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("endpoint", sa.Text, nullable=False),
            sa.Column("p256dh", sa.String(200), nullable=False),
            sa.Column("auth", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("user_agent", sa.String(512)),
            sa.Column("last_seen_at", sa.DateTime(timezone=True)),
            sa.Column(
                "topics",
                sa.JSON,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.Index("ix_push_subscriptions_endpoint", "endpoint", unique=True),
            sa.Index("ix_push_subscriptions_user_id", "user_id"),
            sa.Index("ix_push_subscriptions_created_at", "created_at"),
            sa.Index("ix_push_subscriptions_last_seen_at", "last_seen_at"),
        )
        metadata.create_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()

    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
    finally:
        previous_url = config.attributes.get("_previous_database_url")
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url

    engine = _inspect(sync_url)
    insp = sa.inspect(engine)
    assert insp.has_table("users")
    user_columns = {col["name"] for col in insp.get_columns("users")}
    # Columns dnd_enabled, dnd_start, dnd_end, timezone were moved to user_preferences table
    # mfa_required and mfa_default_method remain in users table
    assert {"mfa_required", "mfa_default_method"}.issubset(user_columns)
    assert "mfa_recovery_codes_generated_at" not in user_columns

    # Verify user_preferences table exists with the DND and timezone columns
    assert insp.has_table("user_preferences")
    user_prefs_columns = {col["name"] for col in insp.get_columns("user_preferences")}
    assert {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}.issubset(
        user_prefs_columns
    )

    assert insp.has_table("push_subscriptions")

    for table_name in {
        "mfa_totp_enrollments",
        "mfa_challenges",
    }:
        assert insp.has_table(table_name)

    assert not insp.has_table("mfa_recovery_codes")

    assert not insp.has_table("mfa_webauthn_credentials")

    challenge_columns = {col["name"] for col in insp.get_columns("mfa_challenges")}
    assert {"user_id", "session_id", "challenge_type", "expires_at"}.issubset(
        challenge_columns
    )
    challenge_fks = insp.get_foreign_keys("mfa_challenges")
    assert any(fk["referred_table"] == "active_sessions" for fk in challenge_fks)
    engine.dispose()


def test_alembic_upgrade_from_multiple_heads(tmp_path):
    config, _ = _make_config(tmp_path, "multi-head.sqlite", use_async=False)
    # Use in-memory database to avoid locking issues on Windows
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    version = sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String(32), primary_key=True),
    )
    metadata.create_all(engine)
    Base.metadata.create_all(engine)

    # Keep connection open and share it with alembic
    with engine.connect() as connection:
        # Manually add columns that are expected by migrations but missing from current models
        connection.execute(sa.text("ALTER TABLE users ADD COLUMN dnd_enabled BOOLEAN"))
        connection.execute(sa.text("ALTER TABLE users ADD COLUMN dnd_start VARCHAR"))
        connection.execute(sa.text("ALTER TABLE users ADD COLUMN dnd_end VARCHAR"))
        connection.execute(sa.text("ALTER TABLE users ADD COLUMN timezone VARCHAR"))

        connection.execute(version.insert().values(version_num="23d991e593b5"))
        connection.execute(version.insert().values(version_num="f9d2b1f5e2d0"))
        connection.commit()

        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        # Verify using the same connection
        rows = connection.execute(version.select()).fetchall()

    engine.dispose()

    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert {row[0] for row in rows} == set(heads)
