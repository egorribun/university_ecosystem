from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    REPOSITORY_ROOT / "scripts" / "quality" / "validate_quality_contract.py"
)

_CANONICAL_CONTRACT = """
{
  "version": 1,
  "policy": {
    "patch_coverage": 100,
    "viable_mutant_score": 100,
    "required_pr_matrix": true
  },
  "coverage_minimums": {
    "lines": 99,
    "statements": 99,
    "branches": 98,
    "functions": 98,
    "tier0": 100
  },
  "components": {
    "python": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "frontend": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "go-gateway": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "go-ws-hub": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "go-file-processor": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "rust-native": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "rust-pyo3-sanitizer": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "rust-wasm-sanitizer": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "infrastructure": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "workflows": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}},
    "scripts": {"coverage": {"lines": 99, "statements": 99, "branches": 98, "functions": 98}}
  },
  "tier0": {"coverage": {"lines": 100, "statements": 100, "branches": 100, "functions": 100}},
  "required_artifacts": ["coverage.xml", "frontend/coverage/lcov.info"],
  "exclusions": [],
  "quarantines": []
}
"""


def _run_validator(
    cwd: Path,
    contract: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(VALIDATOR_PATH)]
    if contract is not None:
        command.extend(("--contract", str(contract)))

    # The executable and validator path are test-controlled absolute paths.
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=cwd,
        text=True,
    )


def _load_contract() -> dict[str, object]:
    return json.loads(_CANONICAL_CONTRACT)


def _run_contract(
    cwd: Path,
    contract: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    contract_path = cwd / "quality-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    return _run_validator(cwd, contract_path)


def _exclusion(
    *,
    exclusion_id: str = "generated-client",
    path: str = "frontend/src/generated/client.ts",
    created_on: str = "2026-07-01",
    expires_on: str = "2026-07-30",
) -> dict[str, str]:
    return {
        "id": exclusion_id,
        "path": path,
        "reason": "generated source is verified by its generator contract",
        "owner": "platform-quality",
        "issue": "QUALITY-1",
        "created_on": created_on,
        "expires_on": expires_on,
        "evidence": "generator-contract.log",
    }


def test_repository_quality_contract_is_accepted_from_another_directory(
    tmp_path: Path,
) -> None:
    result = _run_validator(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Quality contract is valid.\n"


def test_rejects_component_floor_below_programme_minimum(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["components"]["python"]["coverage"]["branches"] = 97

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "python.coverage.branches must be at least 98" in result.stderr


def test_rejects_expired_unowned_quarantine(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["quarantines"] = [
        {
            "id": "frontend-router-flake",
            "test": "frontend/src/__tests__/router.test.ts",
            "path": "frontend/src/routes/router.ts",
            "reason": "deterministic reproducer pending",
            "owner": "",
            "issue": "QUALITY-1",
            "created_on": "2026-06-01",
            "expires_on": "2026-06-30",
            "evidence": "trace.zip",
        }
    ]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "quarantines[0].owner must be a non-empty string" in result.stderr
    assert "quarantines[0].expires_on must be after validation day" in result.stderr


def test_rejects_duplicate_exclusion_ids(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["exclusions"] = [
        _exclusion(),
        _exclusion(path="frontend/src/generated/schema.ts"),
    ]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "exclusions[1].id duplicates exclusions[0].id" in result.stderr


def test_rejects_wildcard_exclusion_paths(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["exclusions"] = [_exclusion(path="frontend/src/generated/*.ts")]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "exclusions[0].path must not contain a wildcard" in result.stderr


def test_rejects_missing_required_components(tmp_path: Path) -> None:
    contract = _load_contract()
    del contract["components"]["frontend"]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "components is missing required component: frontend" in result.stderr


def test_rejects_non_integer_contract_version(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["version"] = 1.0

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "version must equal 1" in result.stderr


def test_rejects_tier0_coverage_below_100(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["tier0"]["coverage"]["functions"] = 99

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "tier0.coverage.functions must equal 100" in result.stderr


def test_rejects_malformed_json_with_usage_error(tmp_path: Path) -> None:
    contract_path = tmp_path / "quality-contract.json"
    contract_path.write_text('{"version": 1,', encoding="utf-8")

    result = _run_validator(tmp_path, contract_path)

    assert result.returncode == 2
    assert "ERROR: invalid JSON" in result.stderr


def test_rejects_duplicate_json_keys_with_usage_error(tmp_path: Path) -> None:
    contract_path = tmp_path / "quality-contract.json"
    contract_path.write_text('{"version": 1, "version": 1}', encoding="utf-8")

    result = _run_validator(tmp_path, contract_path)

    assert result.returncode == 2
    assert "ERROR: duplicate JSON key: version" in result.stderr


def test_rejects_expiry_more_than_30_days_after_creation(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["exclusions"] = [
        _exclusion(created_on="2026-07-01", expires_on="2026-08-01")
    ]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "exclusions[0].expires_on must be at most 30 days after created_on"
        in result.stderr
    )
