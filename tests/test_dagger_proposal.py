from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, ClassVar

import pytest


class _FakeContainer:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    def from_(self, image: str) -> _FakeContainer:
        self._calls.append(("from", image))
        return self

    def with_directory(self, path: str, source: object) -> _FakeContainer:
        self._calls.append(("with_directory", path, source))
        return self

    def with_workdir(self, path: str) -> _FakeContainer:
        self._calls.append(("with_workdir", path))
        return self

    def with_exec(self, command: list[str]) -> _FakeContainer:
        self._calls.append(("with_exec", tuple(command)))
        return self

    async def stdout(self) -> str:
        self._calls.append(("stdout",))
        return "fake output"

    async def exit_code(self) -> int:
        self._calls.append(("exit_code",))
        return 0


class _FakeHost:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    def directory(self, path: str) -> object:
        source = object()
        self._calls.append(("directory", path, source))
        return source


class _FakeClient:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self._calls = calls

    def host(self) -> _FakeHost:
        self._calls.append(("host",))
        return _FakeHost(self._calls)

    def container(self) -> _FakeContainer:
        self._calls.append(("container",))
        return _FakeContainer(self._calls)


class _FakeConnection:
    instances: ClassVar[list[_FakeConnection]] = []

    def __init__(self, config: object) -> None:
        self.config = config
        self.calls: list[tuple[str, Any]] = [("connection", config)]
        self.client = _FakeClient(self.calls)
        self.__class__.instances.append(self)

    async def __aenter__(self) -> _FakeClient:
        self.calls.append(("enter",))
        return self.client

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.calls.append(("exit", exc_type, exc, tb))


@pytest.mark.asyncio
async def test_dagger_pipeline_executes_all_declared_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_dagger = ModuleType("dagger")
    fake_dagger.Config = lambda **kwargs: SimpleNamespace(**kwargs)
    fake_dagger.Connection = _FakeConnection
    monkeypatch.setitem(sys.modules, "dagger", fake_dagger)
    sys.modules.pop("app.core.ci.dagger_proposal", None)

    proposal = importlib.import_module("app.core.ci.dagger_proposal")
    _FakeConnection.instances.clear()

    await proposal.pipeline()

    assert len(_FakeConnection.instances) == 1
    connection = _FakeConnection.instances[0]
    assert connection.config.log_output is sys.stdout
    assert connection.calls[0][0] == "connection"
    assert connection.calls[1] == ("enter",)
    assert connection.calls[-1][0] == "exit"
    assert [item[:2] for item in connection.calls if item[0] == "from"] == [
        ("from", "ghcr.io/astral-sh/uv:python3.13-bookworm-slim"),
        ("from", "golang:1.24-alpine"),
        ("from", "trufflesecurity/trufflehog:latest"),
    ]
    assert [item[1] for item in connection.calls if item[0] == "with_workdir"] == [
        "/src",
        "/src/services/gateway",
    ]
    assert [item[1] for item in connection.calls if item[0] == "with_exec"] == [
        ("uv", "lock", "--check"),
        ("uv", "sync", "--frozen"),
        ("uv", "run", "pytest", "tests"),
        ("go", "build", "-o", "gateway", "./cmd/gateway"),
        ("./gateway", "--help"),
        ("trufflehog", "filesystem", "/src", "--fail"),
    ]
    assert [item[0] for item in connection.calls].count("stdout") == 2
    assert [item[0] for item in connection.calls].count("exit_code") == 1
