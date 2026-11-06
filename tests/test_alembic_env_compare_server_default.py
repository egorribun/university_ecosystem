"""AUD-434 regressions for JSON server defaults and Alembic integration."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.autogenerate.compare.server_defaults import _compare_computed_default
from alembic.config import Config
from alembic.operations.ops import AlterColumnOp
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from alembic.util import DispatchPriority, PriorityDispatcher, PriorityDispatchResult
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

import app.models as models
from alembic import context as alembic_context
from app.core.db import retained_table_metadata, schema_drift
from app.core.db.retained_table_metadata import build_migration_metadata

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "alembic" / "env.py"
BASELINE_FILE = ROOT / "alembic" / "versions" / "202611020000_mvp_baseline.py"
PLUGIN_FILE = ROOT / "app" / "core" / "db" / "alembic_json_server_defaults.py"
_PLUGIN_MODULE_NAME = "aud434_candidate_json_server_default_plugin"
_PLUGIN_SPEC = importlib.util.spec_from_file_location(_PLUGIN_MODULE_NAME, PLUGIN_FILE)
assert _PLUGIN_SPEC is not None and _PLUGIN_SPEC.loader is not None
PLUGIN_MODULE: Any = importlib.util.module_from_spec(_PLUGIN_SPEC)
sys.modules[_PLUGIN_MODULE_NAME] = PLUGIN_MODULE
_PLUGIN_SPEC.loader.exec_module(PLUGIN_MODULE)
PLUGIN_NAME: str = PLUGIN_MODULE.PLUGIN_NAME
compare_json_server_default = PLUGIN_MODULE.compare_json_server_default


def _online_configure_keywords() -> dict[str, ast.expr]:
    tree = ast.parse(ENV_FILE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_configure_context"
    )
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "configure"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "context"
    ]
    assert len(calls) == 1
    return {keyword.arg: keyword.value for keyword in calls[0].keywords if keyword.arg}


def _is_constant(value: ast.expr | None, expected: object) -> bool:
    return isinstance(value, ast.Constant) and value.value is expected


def test_online_context_compares_server_defaults_for_alembic_check() -> None:
    keywords = _online_configure_keywords()
    assert _is_constant(keywords.get("compare_server_default"), True)
    plugins = keywords.get("autogenerate_plugins")
    assert isinstance(plugins, ast.Tuple)
    assert len(plugins.elts) == 2
    assert isinstance(plugins.elts[0], ast.Constant)
    assert plugins.elts[0].value == "alembic.autogenerate.*"
    assert isinstance(plugins.elts[1], ast.Name)
    assert plugins.elts[1].id == "_JSON_SERVER_DEFAULT_PLUGIN"
    plugin_name = next(
        node.value
        for node in ast.walk(ast.parse(ENV_FILE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_JSON_SERVER_DEFAULT_PLUGIN"
            for target in node.targets
        )
    )
    assert isinstance(plugin_name, ast.Constant)
    assert plugin_name.value == PLUGIN_NAME


def test_online_context_keeps_its_existing_comparison_options() -> None:
    keywords = _online_configure_keywords()
    for name in (
        "compare_type",
        "render_as_batch",
        "transactional_ddl",
        "transaction_per_migration",
    ):
        assert _is_constant(keywords.get(name), True), name
    assert {"include_object", "process_revision_directives"} <= keywords.keys()


def _compare_plugin(
    inspected_column: sa.Column[Any],
    metadata_column: sa.Column[Any],
    *,
    dialect: Any | None = None,
    table_name: str = "push_subscriptions",
    column_name: str = "topics",
) -> tuple[PriorityDispatchResult, AlterColumnOp]:
    alter = AlterColumnOp(table_name, column_name)
    result = compare_json_server_default(
        SimpleNamespace(dialect=dialect or postgresql.dialect()),
        alter,
        None,
        table_name,
        column_name,
        inspected_column,
        metadata_column,
    )
    return result, alter


def test_json_default_plugin_reports_only_the_target_json_expression_drift() -> None:
    metadata_column = sa.Column("topics", sa.JSON, server_default=sa.text("'[]'::json"))
    inspected_column = sa.Column(
        "topics",
        sa.JSON,
        server_default=sa.text("'[\"aud434-drift\"]'::json"),
    )
    result, alter = _compare_plugin(inspected_column, metadata_column)

    assert result is PriorityDispatchResult.STOP
    assert alter.existing_server_default is inspected_column.server_default
    assert alter.modify_server_default is metadata_column.server_default


def test_json_default_plugin_accepts_matching_expression_defaults() -> None:
    inspected_column = sa.Column(
        "topics", sa.JSON, server_default=sa.text("'[]'::json")
    )
    metadata_column = sa.Column("topics", sa.JSON, server_default=sa.text("'[]'::json"))
    result, alter = _compare_plugin(inspected_column, metadata_column)

    assert result is PriorityDispatchResult.STOP
    assert alter.existing_server_default is inspected_column.server_default
    assert alter.modify_server_default is False


def test_json_default_plugin_accepts_matching_string_defaults() -> None:
    inspected_column = sa.Column("topics", sa.JSON, server_default="'[]'::json")
    metadata_column = sa.Column("topics", sa.JSON, server_default="'[]'::json")
    result, alter = _compare_plugin(inspected_column, metadata_column)

    assert result is PriorityDispatchResult.STOP
    assert alter.existing_server_default is inspected_column.server_default
    assert alter.modify_server_default is False


def test_json_default_plugin_accepts_missing_defaults_on_both_sides() -> None:
    inspected_column = sa.Column("topics", sa.JSON)
    metadata_column = sa.Column("topics", sa.JSON)
    result, alter = _compare_plugin(inspected_column, metadata_column)

    assert result is PriorityDispatchResult.STOP
    assert alter.existing_server_default is None
    assert alter.modify_server_default is False


@pytest.mark.parametrize(
    ("dialect", "table_name", "column_name", "inspected_type", "metadata_type"),
    [
        (sqlite.dialect(), "push_subscriptions", "topics", sa.JSON, sa.JSON),
        (postgresql.dialect(), "other_table", "topics", sa.JSON, sa.JSON),
        (postgresql.dialect(), "push_subscriptions", "other", sa.JSON, sa.JSON),
        (postgresql.dialect(), "push_subscriptions", "topics", sa.String, sa.JSON),
        (postgresql.dialect(), "push_subscriptions", "topics", sa.JSON, sa.String),
    ],
)
def test_json_default_plugin_falls_through_outside_target_scope(
    dialect: Any,
    table_name: str,
    column_name: str,
    inspected_type: Any,
    metadata_type: Any,
) -> None:
    inspected_column = sa.Column(
        column_name,
        inspected_type,
        server_default=sa.text("'[]'::json"),
    )
    metadata_column = sa.Column(
        column_name,
        metadata_type,
        server_default=sa.text("'[\"different\"]'::json"),
    )
    result, alter = _compare_plugin(
        inspected_column,
        metadata_column,
        dialect=dialect,
        table_name=table_name,
        column_name=column_name,
    )

    assert result is PriorityDispatchResult.CONTINUE
    assert alter.existing_server_default is False
    assert alter.modify_server_default is False


@pytest.mark.parametrize("computed_side", ["inspected", "metadata"])
def test_json_default_plugin_leaves_computed_defaults_to_alembic(
    computed_side: str,
) -> None:
    default_column = sa.Column("topics", sa.JSON, server_default=sa.text("'[]'::json"))
    computed_column = sa.Column(
        "topics", sa.JSON, sa.Computed("json_build_array()", persisted=True)
    )
    inspected_column, metadata_column = (
        (computed_column, default_column)
        if computed_side == "inspected"
        else (default_column, computed_column)
    )
    result, alter = _compare_plugin(inspected_column, metadata_column)

    assert result is PriorityDispatchResult.CONTINUE
    assert alter.existing_server_default is False
    assert alter.modify_server_default is False


@pytest.mark.parametrize("computed_side", ["inspected", "metadata"])
def test_json_plugin_falls_through_to_native_computed_comparator(
    computed_side: str,
) -> None:
    dispatcher = PriorityDispatcher()
    dispatcher.dispatch_for(
        "column",
        subgroup="server_default",
        qualifier="postgresql",
        priority=DispatchPriority.FIRST,
    )(compare_json_server_default)
    dispatcher.dispatch_for(
        "column", subgroup="server_default", qualifier="postgresql"
    )(_compare_computed_default)

    default_column = sa.Column("topics", sa.JSON, server_default=sa.text("'[]'::json"))
    computed_column = sa.Column(
        "topics", sa.JSON, sa.Computed("json_build_array()", persisted=True)
    )
    inspected_column, metadata_column = (
        (computed_column, default_column)
        if computed_side == "inspected"
        else (default_column, computed_column)
    )
    alter = AlterColumnOp("push_subscriptions", "topics")

    with pytest.warns(
        UserWarning,
        match=r"Computed default on push_subscriptions\.topics cannot be modified",
    ):
        dispatcher.dispatch("column", qualifier="postgresql")(
            SimpleNamespace(dialect=postgresql.dialect()),
            alter,
            None,
            "push_subscriptions",
            "topics",
            inspected_column,
            metadata_column,
        )

    assert alter.modify_server_default is False


def test_plugin_setup_registers_first_postgresql_column_comparator() -> None:
    registrations: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _PluginRecorder:
        def add_autogenerate_comparator(self, *args: Any, **kwargs: Any) -> None:
            registrations.append((args, kwargs))

    PLUGIN_MODULE.setup(_PluginRecorder())

    assert registrations == [
        (
            (compare_json_server_default, "column", "server_default"),
            {"qualifier": "postgresql", "priority": DispatchPriority.FIRST},
        )
    ]


def test_plugin_register_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, str]] = []

    def _record_registration(module: Any, plugin_name: str) -> None:
        calls.append((module, plugin_name))

    monkeypatch.setattr(
        PLUGIN_MODULE,
        "Plugin",
        SimpleNamespace(setup_plugin_from_module=_record_registration),
    )
    monkeypatch.setattr(PLUGIN_MODULE, "_registered", False)

    PLUGIN_MODULE.register()
    PLUGIN_MODULE.register()

    assert calls == [(PLUGIN_MODULE, PLUGIN_NAME)]


def test_candidate_env_registers_plugin_and_keeps_native_comparator_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "app.core.db.alembic_json_server_defaults"
    registrations: list[tuple[Any, str]] = []

    def _record_registration(module: Any, plugin_name: str) -> None:
        registrations.append((module, plugin_name))

    monkeypatch.setattr(
        PLUGIN_MODULE,
        "Plugin",
        SimpleNamespace(setup_plugin_from_module=_record_registration),
    )
    monkeypatch.setattr(PLUGIN_MODULE, "_registered", False)
    monkeypatch.setitem(sys.modules, module_name, PLUGIN_MODULE)
    configured: list[dict[str, Any]] = []
    metadata = object()
    include_object = object()
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("ENV_FILE_PATH", "")
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    monkeypatch.setattr(
        alembic_context,
        "configure",
        lambda **kwargs: configured.append(kwargs),
    )
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)
    monkeypatch.setattr(alembic_context, "run_migrations", lambda: None)
    monkeypatch.setattr(
        retained_table_metadata,
        "build_migration_metadata",
        lambda _metadata, dialect_name: metadata,
    )
    monkeypatch.setattr(
        schema_drift,
        "build_partition_aware_include_object",
        lambda _connection: include_object,
    )

    config = Config()
    config.set_main_option("script_location", str(ENV_FILE.parent))
    config.attributes["connection"] = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )
    script = ScriptDirectory.from_config(config)
    try:
        with EnvironmentContext(config, script):
            env_name = "aud434_candidate_alembic_env"
            env_spec = importlib.util.spec_from_file_location(env_name, ENV_FILE)
            assert env_spec is not None and env_spec.loader is not None
            env_module: Any = importlib.util.module_from_spec(env_spec)
            sys.modules[env_name] = env_module
            try:
                env_spec.loader.exec_module(env_module)
            finally:
                sys.modules.pop(env_name, None)
    finally:
        config.attributes.pop("connection", None)

    assert len(configured) == 1
    options = configured[0]
    assert options["connection"].dialect.name == "postgresql"
    assert options["target_metadata"] is metadata
    assert options["include_object"] is include_object
    assert options["compare_server_default"] is True
    assert options["autogenerate_plugins"] == (
        "alembic.autogenerate.*",
        PLUGIN_NAME,
    )
    assert registrations == [(PLUGIN_MODULE, PLUGIN_NAME)]
    assert PLUGIN_MODULE._registered is True


class _PostgresBind:
    class dialect:
        name = "postgresql"

    def execute(self, _statement: Any) -> Any:
        return SimpleNamespace(fetchone=lambda: None)


class _RecordingOp:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def get_bind(self) -> _PostgresBind:
        return _PostgresBind()

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))


def _baseline_create_table(table: str) -> str:
    spec = importlib.util.spec_from_file_location(
        "baseline_default_probe", BASELINE_FILE
    )
    assert spec is not None and spec.loader is not None
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorder = _RecordingOp()
    module.op = recorder
    module.upgrade()
    prefix = f"CREATE TABLE public.{table} ("
    created = [
        statement for statement in recorder.statements if statement.startswith(prefix)
    ]
    assert len(created) == 1, table
    return created[0]


def _topics_default(create_table: str) -> str:
    lines = [line.strip() for line in create_table.splitlines()]
    topics = [line for line in lines if line.startswith("topics ")]
    assert len(topics) == 1, create_table
    match = re.search(r"DEFAULT (.+) NOT NULL", topics[0], re.IGNORECASE)
    assert match is not None, topics[0]
    return match.group(1)


def test_push_subscription_topics_default_agrees_between_model_and_baseline() -> None:
    """AUD-434: the model and the baseline spell one PostgreSQL default for topics."""
    metadata = build_migration_metadata(models.Base.metadata, dialect_name="postgresql")
    model_table = metadata.tables["push_subscriptions"]
    model_ddl = str(CreateTable(model_table).compile(dialect=postgresql.dialect()))

    model_default = _topics_default(model_ddl)
    baseline_default = _topics_default(_baseline_create_table("push_subscriptions"))

    assert model_default == baseline_default == "'[]'::json"
