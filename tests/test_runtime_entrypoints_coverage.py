"""Behavioral coverage for runtime entrypoints and optional integrations."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import runpy
import sys
import tomllib
from collections.abc import Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from app import worker
from app.core import profiling, uvloop_setup
from app.deps.cache import BaseCache

pytestmark = pytest.mark.filterwarnings(
    "ignore:.*found in sys.modules after import.*:RuntimeWarning"
)


def test_runtime_entrypoints_are_part_of_the_coverage_universe() -> None:
    config = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    omitted = set(config["tool"]["coverage"]["run"].get("omit", ()))

    assert omitted.isdisjoint(
        {
            "app/worker.py",
            "app/__main__.py",
            "app/core/uvloop_setup.py",
            "app/core/profiling.py",
        }
    )


def test_worker_run_configures_logging_and_executes_async_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = Mock()
    received: list[Coroutine[Any, Any, None]] = []

    def run_coroutine(coroutine: Coroutine[Any, Any, None]) -> None:
        received.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(logging, "basicConfig", configured)
    monkeypatch.setattr(asyncio, "run", run_coroutine)

    worker.run()

    configured.assert_called_once_with(level=logging.INFO)
    assert len(received) == 1
    assert received[0].cr_code.co_name == "main"


def test_worker_run_treats_keyboard_interrupt_as_clean_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(coroutine: Coroutine[Any, Any, None]) -> None:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "run", interrupt)

    worker.run()


def test_root_module_main_delegates_to_typer_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_module = importlib.import_module("app.__main__")
    typer_app = Mock()
    monkeypatch.setattr(root_module, "app", typer_app)

    root_module.main()

    typer_app.assert_called_once_with()


def test_root_module_executes_its_script_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_module = importlib.import_module("app.cli.__main__")
    typer_app = Mock()
    monkeypatch.setattr(cli_module, "app", typer_app)

    runpy.run_module("app.__main__", run_name="__main__")

    typer_app.assert_called_once_with()


def test_cli_module_executes_its_script_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import typer

    invoke = Mock()
    monkeypatch.setattr(typer.Typer, "__call__", invoke)

    runpy.run_module("app.cli.__main__", run_name="__main__")

    invoke.assert_called_once_with()


@pytest.mark.parametrize(
    "module_name",
    [
        "app.management.normalize_static",
        "app.management.stories_cleanup",
        "app.management.weekly_cleanup",
        "app.scripts.backfill_uuids",
        "app.services.email_change_cleanup",
        "app.services.mfa_challenge_cleanup",
        "app.services.password_reset_cleanup",
        "app.services.session_cleanup",
        "app.services.story_cleanup",
        "app.worker",
        "app.workers.notifications",
        "app.workers.outbox",
    ],
)
def test_asyncio_modules_execute_their_script_entrypoints(
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[Coroutine[Any, Any, object]] = []

    def close_coroutine(coroutine: Coroutine[Any, Any, object]) -> None:
        received.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", close_coroutine)

    runpy.run_module(module_name, run_name="__main__")

    assert len(received) == 1


def test_reset_mfa_executes_its_script_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[Coroutine[Any, Any, object]] = []

    def close_coroutine(coroutine: Coroutine[Any, Any, object]) -> None:
        received.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", close_coroutine)
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        Mock(return_value=SimpleNamespace()),
    )

    runpy.run_module("app.management.reset_mfa", run_name="__main__")

    assert len(received) == 1


@pytest.mark.asyncio
async def test_base_cache_requires_concrete_data_operations() -> None:
    cache = BaseCache()

    with pytest.raises(NotImplementedError):
        await cache.get("key")
    with pytest.raises(NotImplementedError):
        await cache.set("key", {"value": 1})
    with pytest.raises(NotImplementedError):
        await cache.invalidate("key")
    assert await cache.close() is None


def test_configure_uvloop_installs_available_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = object()
    event_loop_policy = Mock(return_value=policy)
    set_policy = Mock()
    monkeypatch.setitem(
        sys.modules,
        "uvloop",
        SimpleNamespace(EventLoopPolicy=event_loop_policy),
    )
    monkeypatch.setattr(asyncio, "set_event_loop_policy", set_policy)

    assert uvloop_setup.configure_uvloop() is True
    event_loop_policy.assert_called_once_with()
    set_policy.assert_called_once_with(policy)


def test_configure_uvloop_falls_back_when_optional_dependency_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "uvloop", None)

    assert uvloop_setup.configure_uvloop() is False


def test_configure_uvloop_falls_back_when_policy_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = RuntimeError("unsupported policy")
    event_loop_policy = Mock(side_effect=error)
    warning = Mock()
    monkeypatch.setitem(
        sys.modules,
        "uvloop",
        SimpleNamespace(EventLoopPolicy=event_loop_policy),
    )
    monkeypatch.setattr(uvloop_setup.logger, "warning", warning)

    assert uvloop_setup.configure_uvloop() is False
    warning.assert_called_once_with(
        "Failed to configure uvloop: %s",
        error,
    )


def test_get_loop_implementation_falls_back_when_policy_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        asyncio,
        "get_event_loop_policy",
        Mock(side_effect=RuntimeError("policy unavailable")),
    )

    assert uvloop_setup.get_loop_implementation() == "unknown"


def test_pyroscope_profiler_uses_explicit_server_address() -> None:
    profiler = profiling.PyroscopeProfiler(server_address="http://profile:4040")

    assert profiler.server_address == "http://profile:4040"


def test_pyroscope_profiler_uses_default_server_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYROSCOPE_SERVER_ADDRESS", raising=False)

    profiler = profiling.PyroscopeProfiler()

    assert profiler.server_address == "http://pyroscope:4040"


def test_pyroscope_configure_falls_back_when_optional_sdk_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning = Mock()
    monkeypatch.setitem(sys.modules, "pyroscope", None)
    monkeypatch.setattr(profiling._logger, "warning", warning)

    profiling.PyroscopeProfiler().configure()

    warning.assert_called_once()


def test_pyroscope_configure_contains_sdk_initialization_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = RuntimeError("collector unavailable")
    configure = Mock(side_effect=error)
    log_error = Mock()
    monkeypatch.setitem(
        sys.modules,
        "pyroscope",
        SimpleNamespace(configure=configure),
    )
    monkeypatch.setattr(profiling._logger, "error", log_error)

    profiling.PyroscopeProfiler().configure()

    log_error.assert_called_once_with("Failed to initialize Pyroscope: %s", error)


def test_noop_profiler_records_disabled_state(monkeypatch: pytest.MonkeyPatch) -> None:
    debug = Mock()
    monkeypatch.setattr(profiling._logger, "debug", debug)

    profiling.NoOpProfiler().configure()

    debug.assert_called_once_with("Profiling is disabled (NoOpProfiler active).")


@pytest.mark.parametrize("value", [None, "false", "1"])
def test_get_profiler_defaults_to_noop(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("ENABLE_PROFILING", raising=False)
    else:
        monkeypatch.setenv("ENABLE_PROFILING", value)

    assert isinstance(profiling.get_profiler(), profiling.NoOpProfiler)


def test_get_profiler_enables_pyroscope_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_PROFILING", "TRUE")

    assert isinstance(profiling.get_profiler(), profiling.PyroscopeProfiler)
