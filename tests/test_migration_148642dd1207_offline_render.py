from __future__ import annotations

import io
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("direction", "needle"),
    [
        ("upgrade", "ID__INTEGER INTEGER"),
        ("downgrade", "ID__VARCHAR VARCHAR(20)"),
    ],
)
def test_offline_render_uses_project_default_revision_location(
    monkeypatch: pytest.MonkeyPatch, direction: str, needle: str
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://migration_test@127.0.0.1:5432/migration_test",
    )
    buffer = io.StringIO()
    config = Config(str(PROJECT_ROOT / "alembic.ini"), output_buffer=buffer)
    assert config.get_main_option("script_location") == "alembic"

    if direction == "upgrade":
        command.upgrade(config, "f7aa476e968a:148642dd1207", sql=True)
    else:
        command.downgrade(config, "148642dd1207:f7aa476e968a", sql=True)

    assert needle in buffer.getvalue().upper()
