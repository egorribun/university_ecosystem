"""Exercise the actual Make recipe with synthetic generation inputs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    ProcessOutcome,
    run_private_process,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = {
    "openapi": "3.1.0",
    "info": {"version": "1", "title": "Synthetic contract"},
    "paths": {},
}
_APP_SOURCE = dedent(
    """\
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    marker = root / "synthetic-app-imported"
    marker.write_text("yes", encoding="utf-8")

    class SyntheticApp:
        def openapi(self):
            if (root / "fail-export").exists():
                raise RuntimeError("synthetic export failure")
            source = (root / "schema-input.json").read_text(encoding="utf-8")
            return json.loads(source)

    app = SyntheticApp()
    """
)
_NPM_SOURCE = dedent(
    """\
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    frontend = root / "frontend"
    arguments = sys.argv[1:]
    normalize_args = ["exec", "--", "prettier", "--write", "openapi.json"]
    generate_args = ["run", "generate:api", "--prefix", str(frontend)]
    normalizing = arguments == normalize_args
    generating = arguments == generate_args
    if not (normalizing or generating):
        raise SystemExit(91)
    if normalizing and Path.cwd() != frontend:
        raise SystemExit(92)

    schema_path = frontend / "openapi.json"
    schema_text = schema_path.read_text(encoding="utf-8")
    entry = {
        "stage": "normalize" if normalizing else "generate",
        "argv": arguments,
        "cwd": str(Path.cwd()),
        "schema_text": schema_text,
        "schema": json.loads(schema_text),
    }
    calls_path = root / "npm-calls.jsonl"
    with calls_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\\n")

    if normalizing and (root / "fail-normalize").exists():
        raise SystemExit(23)
    if generating and (root / "fail-generate").exists():
        raise SystemExit(24)
    if generating:
        outputs = ("src/api/generated", "src/tests/mocks/generated")
        for relative in outputs:
            output = frontend / relative
            output.mkdir(parents=True, exist_ok=True)
            marker = output / "synthetic.txt"
            marker.write_text("generated", encoding="utf-8")
    """
)


def _run(argv: tuple[str, ...], cwd: Path, environment: dict[str, str]):
    request = PrivateProcessRequest(
        argv=argv,
        cwd=str(cwd),
        env=environment,
        stdout_limit=32_768,
        stderr_limit=32_768,
    )
    deadline = Deadline.after(10.0, clock=time.monotonic)
    result = run_private_process(request, deadline=deadline)
    assert result.outcome is ProcessOutcome.EXITED
    assert result.local_cleanup is LocalCleanup.CONFIRMED
    return result


@pytest.fixture
def generation_fixture(tmp_path: Path):
    assert os.name == "posix", "Hosted contract requires POSIX process support"
    make = shutil.which("make")
    assert make is not None, "Hosted runner must provide GNU make"
    make_path = Path(make).resolve()
    assert make_path.is_file()
    assert os.access(make_path, os.X_OK)

    root = tmp_path / "generation"
    root.mkdir()
    bin_path = root / "bin"
    bin_path.mkdir()
    python_path = Path(sys.executable).resolve()
    assert python_path.is_file()
    (bin_path / "python3").symlink_to(python_path)
    environment = {
        "PATH": str(bin_path),
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    version = _run((str(make_path), "--version"), root, environment)
    assert version.returncode == 0
    assert b"GNU Make" in version.stdout

    make_source = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    (root / "Makefile").write_text(make_source, encoding="utf-8")
    app_path = root / "app"
    app_path.mkdir()
    (app_path / "__init__.py").write_text("", encoding="utf-8")
    (app_path / "main.py").write_text(_APP_SOURCE, encoding="utf-8")
    input_path = root / "schema-input.json"
    input_path.write_text(json.dumps(_SCHEMA), encoding="utf-8")

    frontend = root / "frontend"
    frontend.mkdir()
    original = '{"previous": true}\n'
    schema_path = frontend / "openapi.json"
    schema_path.write_text(original, encoding="utf-8")

    npm_path = bin_path / "npm"
    npm_source = f"#!{python_path}\n{_NPM_SOURCE}"
    npm_path.write_text(npm_source, encoding="utf-8")
    npm_path.chmod(0o700)
    return root, make_path, environment, original


def _calls(root: Path) -> list[dict]:
    path = root / "npm-calls.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_generate_api_preserves_schema_and_orders_generation(generation_fixture):
    root, make_path, environment, _original = generation_fixture
    result = _run((str(make_path), "generate-api"), root, environment)

    assert result.returncode == 0
    marker = root / "synthetic-app-imported"
    assert marker.read_text(encoding="utf-8") == "yes"
    calls = _calls(root)
    assert [call["stage"] for call in calls] == ["normalize", "generate"]
    expected = json.dumps(_SCHEMA, indent=2, sort_keys=True) + "\n"
    assert all(call["schema"] == _SCHEMA for call in calls)
    assert all(call["schema_text"] == expected for call in calls)

    frontend = root / "frontend"
    schema_path = frontend / "openapi.json"
    assert schema_path.read_text(encoding="utf-8") == expected
    for relative in ("src/api/generated", "src/tests/mocks/generated"):
        output = frontend / relative / "synthetic.txt"
        assert output.read_text(encoding="utf-8") == "generated"


def test_generate_api_export_failure_preserves_previous_schema(generation_fixture):
    root, make_path, environment, original = generation_fixture
    (root / "fail-export").touch()
    result = _run((str(make_path), "generate-api"), root, environment)

    assert result.returncode != 0
    assert (root / "synthetic-app-imported").is_file()
    assert _calls(root) == []
    schema_path = root / "frontend" / "openapi.json"
    assert schema_path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("failure", "expected_stages"),
    [
        ("fail-normalize", ["normalize"]),
        ("fail-generate", ["normalize", "generate"]),
    ],
)
def test_generate_api_downstream_failure_preserves_schema(
    generation_fixture, failure: str, expected_stages: list[str]
):
    root, make_path, environment, _original = generation_fixture
    (root / failure).touch()
    result = _run((str(make_path), "generate-api"), root, environment)

    assert result.returncode != 0
    assert [call["stage"] for call in _calls(root)] == expected_stages
    schema_path = root / "frontend" / "openapi.json"
    assert json.loads(schema_path.read_text(encoding="utf-8")) == _SCHEMA
    assert not (root / "frontend" / "src").exists()
