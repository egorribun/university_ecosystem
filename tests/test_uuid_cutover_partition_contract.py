from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "202602010003_final_cutover_swap.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("uuid_cutover_partition", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inherited_partition_constraint_is_detected_on_postgres() -> None:
    migration = _load_migration()
    bind = MagicMock()
    bind.dialect = SimpleNamespace(name="postgresql")
    bind.execute.return_value.scalar_one_or_none.return_value = 1

    assert migration._is_inherited_partition_constraint(
        bind,
        "data_access_logs_default",
        "data_access_logs_default_legacy_id_created_at_key",
    )
    params = bind.execute.call_args.args[1]
    assert params == {
        "table_name": "data_access_logs_default",
        "constraint_name": "data_access_logs_default_legacy_id_created_at_key",
    }


def test_sqlite_never_queries_postgres_partition_catalogs() -> None:
    migration = _load_migration()
    bind = MagicMock()
    bind.dialect = SimpleNamespace(name="sqlite")

    assert not migration._is_inherited_partition_constraint(bind, "child", "uq")
    bind.execute.assert_not_called()
