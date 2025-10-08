from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

# Import models for Base metadata registration side effects.
import app.models  # noqa: F401
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.database import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_config(tmp_path: Path, name: str) -> tuple[Config, str]:
    db_path = tmp_path / name
    async_url = f"sqlite+aiosqlite:///{db_path}"
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", async_url)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    config.attributes["_previous_database_url"] = previous_url
    return config, f"sqlite:///{db_path}"


def _inspect(url: str) -> sa.engine.Engine:
    return sa.create_engine(url)


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
    assert {"dnd_enabled", "dnd_start", "dnd_end"}.issubset(user_columns)
    assert insp.has_table("push_subscriptions")
    engine.dispose()


def test_alembic_upgrade_from_multiple_heads(tmp_path):
    config, sync_url = _make_config(tmp_path, "multi-head.sqlite")
    engine = _inspect(sync_url)
    metadata = sa.MetaData()
    version = sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String(32), primary_key=True),
    )
    metadata.create_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(version.insert().values(version_num="23d991e593b5"))
        conn.execute(version.insert().values(version_num="f9d2b1f5e2d0"))
    engine.dispose()

    try:
        command.upgrade(config, "head")
    finally:
        previous_url = config.attributes.get("_previous_database_url")
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url

    engine = _inspect(sync_url)
    with engine.begin() as conn:
        rows = conn.execute(version.select()).fetchall()
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert {row[0] for row in rows} == set(heads)
    engine.dispose()
