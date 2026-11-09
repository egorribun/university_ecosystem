"""Source-bound tests for the dependency-free message contract generator."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts/generate_message_contract.py"
CANONICAL_SOURCE = REPOSITORY_ROOT / "app/core/chat_constants.py"
GENERATED_CONTRACT = REPOSITORY_ROOT / "frontend/src/api/schemas/messageLimits.ts"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("message_contract_generator", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def generator() -> ModuleType:
    return _load_generator()


@pytest.fixture
def isolated_source(generator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    source = tmp_path / "app/core/chat_constants.py"
    source.parent.mkdir(parents=True)
    source.write_text("CHAT_MAX_MESSAGE_LENGTH = 17\n", encoding="utf-8")
    legacy = tmp_path / "app/core/config/storage.py"
    legacy.parent.mkdir()
    legacy.write_text("CHAT_MAX_MESSAGE_LENGTH = 999\n", encoding="utf-8")
    monkeypatch.setattr(generator, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(generator, "SOURCE", source)
    return source


def test_generator_reads_the_authoritative_literal_without_application_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "app" or name.startswith("app."):
            attempted.append(name)
            raise AssertionError("The generator must not import application modules")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as isolated:
        isolated.setattr(builtins, "__import__", guarded_import)
        generator = _load_generator()
        assert generator.SOURCE == CANONICAL_SOURCE
        rendered = generator._render()

    assert attempted == []
    assert rendered.encode("utf-8") == GENERATED_CONTRACT.read_bytes()


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        ("CHAT_MAX_MESSAGE_LENGTH = 17\n", 17),
        ("CHAT_MAX_MESSAGE_LENGTH: int = 17\n", 17),
        ("UNRELATED = 999\nCHAT_MAX_MESSAGE_LENGTH = 17\n", 17),
        (
            "raise AssertionError('source must not execute')\n"
            "CHAT_MAX_MESSAGE_LENGTH = 17\n",
            17,
        ),
        ("CHAT_MAX_MESSAGE_LENGTH = 0\n", 0),
    ],
)
def test_generator_reads_literal_assignments_without_executing_source(
    generator, isolated_source: Path, declaration: str, expected: int
) -> None:
    isolated_source.write_text(declaration, encoding="utf-8")
    assert generator._message_limit() == expected


@pytest.mark.parametrize(
    ("source_text", "error_type"),
    [
        (None, FileNotFoundError),
        ("", RuntimeError),
        ("UNRELATED = 17\n", RuntimeError),
        ("from app.core.config.storage import CHAT_MAX_MESSAGE_LENGTH\n", RuntimeError),
        ("CHAT_MAX_MESSAGE_LENGTH = '17'\n", RuntimeError),
        ("CHAT_MAX_MESSAGE_LENGTH = 17.0\n", RuntimeError),
        ("CHAT_MAX_MESSAGE_LENGTH = 8 + 9\n", RuntimeError),
        ("CHAT_MAX_MESSAGE_LENGTH: int\n", RuntimeError),
        ("CHAT_MAX_MESSAGE_LENGTH = (\n", SyntaxError),
    ],
)
def test_missing_or_malformed_source_never_falls_back_to_legacy_literal(
    generator, isolated_source: Path, source_text: str | None, error_type
) -> None:
    if source_text is None:
        isolated_source.unlink()
    else:
        isolated_source.write_text(source_text, encoding="utf-8")

    with pytest.raises(error_type):
        generator._render()


@pytest.mark.parametrize("value", ["True", "False"])
def test_boolean_literals_cannot_be_rendered_as_typescript_numeric_values(
    generator, isolated_source: Path, value: str
) -> None:
    isolated_source.write_text(f"CHAT_MAX_MESSAGE_LENGTH = {value}\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        generator._render()


def test_changed_literal_updates_only_the_generated_numeric_value(
    generator, isolated_source: Path
) -> None:
    before = generator._render()
    isolated_source.write_text("CHAT_MAX_MESSAGE_LENGTH = 29\n", encoding="utf-8")
    after = generator._render()
    assert after == before.replace(
        "CHAT_MESSAGE_MAX_LENGTH = 17 as const",
        "CHAT_MESSAGE_MAX_LENGTH = 29 as const",
    )
    assert after != before


@pytest.mark.parametrize("target_state", ["current", "stale", "missing"])
def test_check_reports_drift_without_writing_the_generated_file(
    generator,
    isolated_source: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target_state: str,
) -> None:
    target = tmp_path / "messageLimits.ts"
    if target_state != "missing":
        content = generator._render() if target_state == "current" else "stale\n"
        target.write_text(content, encoding="utf-8")
    before = target.read_bytes() if target.exists() else None
    monkeypatch.setattr(generator, "TARGET", target)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])

    assert generator.main() == (0 if target_state == "current" else 1)
    assert (target.read_bytes() if target.exists() else None) == before
    output = capsys.readouterr().out
    if target_state == "current":
        assert output == ""
    else:
        assert "stale generated message contract:" in output


def test_generation_writes_exact_rendered_bytes_to_the_owned_target(
    generator,
    isolated_source: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "generated/messageLimits.ts"
    monkeypatch.setattr(generator, "TARGET", target)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    expected = generator._render().encode("utf-8")

    assert generator.main() == 0
    assert target.read_bytes() == expected
