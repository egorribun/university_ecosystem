"""Regression tests for the process scope of Alembic offline shims."""

from __future__ import annotations

import logging
import textwrap
from io import StringIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command, op

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "alembic" / "env.py"


def _make_script(tmp_path: Path, *, upgrade_body: str) -> Path:
    script_dir = tmp_path / "alembic"
    versions_dir = script_dir / "versions"
    versions_dir.mkdir(parents=True)
    (script_dir / "env.py").write_text(
        ENV_FILE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    migration = (
        "from alembic import op\n"
        "import sqlalchemy as sa\n\n"
        "revision = 'offline_scope_probe'\n"
        "down_revision = None\n"
        "branch_labels = None\n"
        "depends_on = None\n\n"
        "def upgrade():\n"
        f"{textwrap.indent(upgrade_body.strip(), '    ')}\n\n"
        "def downgrade():\n"
        "    pass\n"
    )
    (versions_dir / "offline_scope_probe.py").write_text(migration, encoding="utf-8")
    return script_dir


def _make_config(script_dir: Path, *, database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"), output_buffer=StringIO())
    config.set_main_option("script_location", str(script_dir))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _patch_identity() -> tuple[object, object]:
    return op.get_bind, sa.inspect


def _restore_patch_identity(identity: tuple[object, object]) -> None:
    op.get_bind = identity[0]
    sa.inspect = identity[1]


def test_online_upgrade_does_not_leave_offline_shims_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    database_url = "sqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    script_dir = _make_script(tmp_path, upgrade_body="op.execute(sa.text('SELECT 1'))")
    original = _patch_identity()
    application_logger = logging.getLogger("app.auth")
    previous_disabled = application_logger.disabled
    application_logger.disabled = False
    try:
        command.upgrade(
            _make_config(script_dir, database_url=database_url),
            "head",
        )
        after_upgrade = _patch_identity()
        logger_disabled_after_upgrade = application_logger.disabled
    finally:
        _restore_patch_identity(original)
        application_logger.disabled = previous_disabled

    assert after_upgrade == original
    assert logger_disabled_after_upgrade is False


def test_offline_upgrade_restores_shims_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    database_url = "postgresql+asyncpg://migration@localhost:5432/test"
    monkeypatch.setenv("DATABASE_URL", database_url)
    script_dir = _make_script(
        tmp_path,
        upgrade_body=(
            "result = op.get_bind().execute(sa.text('SELECT 1'))\n"
            "assert result.fetchone() is None\n"
            "assert sa.inspect(op.get_bind()).get_table_names() == []"
        ),
    )
    original = _patch_identity()
    try:
        command.upgrade(
            _make_config(script_dir, database_url=database_url),
            "head",
            sql=True,
        )
        after_upgrade = _patch_identity()
    finally:
        _restore_patch_identity(original)

    assert after_upgrade == original


def test_offline_upgrade_restores_shims_when_migration_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    database_url = "postgresql+asyncpg://migration@localhost:5432/test"
    monkeypatch.setenv("DATABASE_URL", database_url)
    script_dir = _make_script(
        tmp_path,
        upgrade_body=(
            "result = op.get_bind().execute(sa.text('SELECT 1'))\n"
            "assert result.fetchone() is None\n"
            "assert sa.inspect(op.get_bind()).get_table_names() == []\n"
            "raise RuntimeError('intentional offline migration failure')"
        ),
    )
    original = _patch_identity()
    try:
        with pytest.raises(RuntimeError, match="intentional offline migration failure"):
            command.upgrade(
                _make_config(script_dir, database_url=database_url),
                "head",
                sql=True,
            )
        after_upgrade = _patch_identity()
    finally:
        _restore_patch_identity(original)

    assert after_upgrade == original
