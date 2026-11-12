"""Generate OpenAPI Spec must produce a parseable spec on a clean runner."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "generate-openapi.yml"
EPHEMERAL_STEP = "Configure ephemeral application secret"
GENERATE_STEP = "Generate OpenAPI spec"
# A hosted runner provides no application settings; keep only what the
# interpreter itself needs so the test cannot borrow the developer's values.
_PLATFORM_ENVIRONMENT = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "LANG",
    "LC_ALL",
)


def _job() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["generate"]


def _step(name: str) -> dict[str, Any]:
    matches = [step for step in _job()["steps"] if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _embedded_python(name: str) -> str:
    run = _step(name)["run"]
    before, delimiter, after = run.partition("uv run --frozen python - <<'PY'\n")
    assert delimiter and before
    body, end, _ = after.partition("\nPY\n")
    assert end
    return body


def test_job_supplies_the_settings_required_to_import_the_app() -> None:
    job = _job()
    assert job["env"] == {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "ENVIRONMENT": "testing",
        "SECRET_KEY": "",
    }
    names = [step.get("name") for step in job["steps"]]
    assert names.index(EPHEMERAL_STEP) < names.index(GENERATE_STEP)
    secret_run = _step(EPHEMERAL_STEP)["run"]
    assert 'secret="$(openssl rand -hex 32)"' in secret_run
    assert 'echo "::add-mask::$secret"' in secret_run
    assert 'printf \'SECRET_KEY=%s\\n\' "$secret" >> "$GITHUB_ENV"' in secret_run


def test_generation_writes_the_file_instead_of_redirecting_stdout() -> None:
    run = _step(GENERATE_STEP)["run"]
    assert run.startswith("set -euo pipefail\n")
    assert "> frontend/openapi.json" not in run
    assert run.rstrip("\n").endswith(
        "uv run --frozen python -c 'import json, sys; "
        'json.load(open(sys.argv[1], encoding="utf-8"))\' frontend/openapi.json'
    )


def test_generation_step_produces_a_parseable_spec_on_a_clean_runner(
    tmp_path: Path,
) -> None:
    environment = {
        name: os.environ[name] for name in _PLATFORM_ENVIRONMENT if name in os.environ
    }
    environment.update(_job()["env"])
    environment.update(
        {
            "SECRET_KEY": secrets.token_hex(32),
            "ENV_FILE_PATH": "",
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    (tmp_path / "frontend").mkdir()

    result = subprocess.run(  # noqa: S603  # fixed interpreter executes the checked-in workflow step
        [sys.executable, "-c", _embedded_python(GENERATE_STEP)],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    output = (tmp_path / "frontend" / "openapi.json").read_text(encoding="utf-8")
    spec = json.loads(output)
    assert spec["openapi"].startswith("3.")
    assert spec["paths"]
    assert output == json.dumps(spec, indent=2, sort_keys=True) + "\n"
