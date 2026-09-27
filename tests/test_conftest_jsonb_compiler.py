from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy.dialects import sqlite
from sqlalchemy.dialects.postgresql import JSONB


def test_loaded_root_jsonb_compiler_returns_sqlite_text(
    request: pytest.FixtureRequest,
) -> None:
    root_conftest_path = Path(__file__).with_name("conftest.py").resolve()
    root_plugins = [
        plugin
        for plugin in request.config.pluginmanager.get_plugins()
        if isinstance(plugin, ModuleType)
        and plugin.__file__ is not None
        and Path(plugin.__file__).resolve() == root_conftest_path
    ]
    assert len(root_plugins) == 1
    callback = root_plugins[0]._compile_jsonb_sqlite
    dialect = sqlite.dialect()

    assert (
        callback(JSONB(), dialect.type_compiler_instance, literal_binds=True) == "TEXT"
    )
