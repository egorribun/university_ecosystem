"""AUD-416: the seeded WASM binary fuzz campaign runs in the frontend WASM job."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_TESTS = ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml"
FUZZER = ROOT / "frontend" / "scripts" / "wasm-fuzzer.mjs"


def _wasm_tests_steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(FRONTEND_TESTS.read_text(encoding="utf-8"))
    return workflow["jobs"]["wasm-tests"]["steps"]


def test_seeded_wasm_fuzz_campaign_runs_after_wasm_contracts() -> None:
    steps = _wasm_tests_steps()
    names = [step.get("name") for step in steps]
    contracts_index = names.index("Run frontend WASM and quality contracts")
    fuzz_index = names.index("Run seeded WASM binary fuzz campaign")

    assert fuzz_index == contracts_index + 1
    fuzz_step = steps[fuzz_index]
    assert fuzz_step["run"] == "node scripts/wasm-fuzzer.mjs"
    assert fuzz_step["env"]["WASM_FUZZ_SEED"] == "20261101"
    assert fuzz_step["env"]["WASM_FUZZ_ITERATIONS"] == "100000"


def test_fuzz_campaign_command_resolves_inside_frontend_working_directory() -> None:
    workflow = yaml.safe_load(FRONTEND_TESTS.read_text(encoding="utf-8"))
    job = workflow["jobs"]["wasm-tests"]
    working_directory = job["defaults"]["run"]["working-directory"]
    assert working_directory == "${{ inputs.working-directory }}"
    assert FUZZER.is_file()
