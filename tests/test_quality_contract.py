from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    REPOSITORY_ROOT / "scripts" / "quality" / "validate_quality_contract.py"
)
QUALITY_CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"

if not QUALITY_CONTRACT_PATH.exists():
    # QUALITY-100 @egorribun: Skip when contract is absent under sandbox environments
    pytest.skip("Quality contract file not found", allow_module_level=True)


def _run_validator(
    cwd: Path,
    contract: Path | None = None,
    manifest: Path | None = None,
    mutation_registry: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(VALIDATOR_PATH)]
    if contract is not None:
        command.extend(("--contract", str(contract)))
    if manifest is not None:
        command.extend(("--manifest", str(manifest)))
    if mutation_registry is not None:
        command.extend(("--mutation-registry", str(mutation_registry)))

    # The executable and validator path are test-controlled absolute paths.
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=cwd,
        text=True,
    )


def _load_contract() -> dict[str, object]:
    return deepcopy(json.loads(QUALITY_CONTRACT_PATH.read_text(encoding="utf-8")))


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
    created_on: str | None = None,
    expires_on: str | None = None,
) -> dict[str, str]:
    created = created_on or date.today().isoformat()
    expires = (
        expires_on or (date.fromisoformat(created) + timedelta(days=29)).isoformat()
    )
    return {
        "id": exclusion_id,
        "path": path,
        "reason": "generated source is verified by its generator contract",
        "owner": "platform-quality",
        "issue": "QUALITY-1",
        "created_on": created,
        "expires_on": expires,
        "evidence": "generator-contract.log",
    }


def _quarantine(
    *,
    quarantine_id: str,
    test: str,
    path: str = "frontend/src/routes/router.ts",
    created_on: str | None = None,
    expires_on: str | None = None,
) -> dict[str, str]:
    created = created_on or date.today().isoformat()
    expires = (
        expires_on or (date.fromisoformat(created) + timedelta(days=29)).isoformat()
    )
    return {
        "id": quarantine_id,
        "test": test,
        "path": path,
        "reason": "deterministic reproducer pending",
        "owner": "platform-quality",
        "issue": "QUALITY-1",
        "created_on": created,
        "expires_on": expires,
        "evidence": "trace.zip",
    }


def _mutation_exclusion(
    *,
    exclusion_id: str = "equivalent-log-message",
    path: str = "app/core/logging.py",
) -> dict[str, str]:
    return {
        "id": exclusion_id,
        "path": path,
        "reason": "mutant changes log text without changing observable behavior",
        "owner": "@egorribun",
        "issue": "QUALITY-2",
        "created_on": date.today().isoformat(),
        "expires_on": (date.today() + timedelta(days=29)).isoformat(),
        "evidence": "tests/test_logging_contract.py",
    }


def test_repository_quality_contract_is_accepted_from_another_directory(
    tmp_path: Path,
) -> None:
    result = _run_validator(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Quality contract is valid.\n"


def test_mutation_registry_is_validated_by_default(tmp_path: Path) -> None:
    registry_path = tmp_path / "mutation-exclusions.json"
    registry_path.write_text(
        json.dumps({"version": 1, "exclusions": [_mutation_exclusion()]}),
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, mutation_registry=registry_path)

    assert result.returncode == 0, result.stderr


def test_mutation_registry_rejects_expired_or_incomplete_exclusion(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "mutation-exclusions.json"
    exclusion = _mutation_exclusion()
    exclusion["owner"] = ""
    exclusion["expires_on"] = (date.today() - timedelta(days=1)).isoformat()
    registry_path.write_text(
        json.dumps({"version": 1, "exclusions": [exclusion]}),
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, mutation_registry=registry_path)

    assert result.returncode == 1
    assert "mutation_exclusions[0].owner must be a non-empty string" in result.stderr
    assert (
        "mutation_exclusions[0].expires_on must be after validation day"
        in result.stderr
    )


def test_mutation_registry_rejects_duplicate_paths(tmp_path: Path) -> None:
    registry_path = tmp_path / "mutation-exclusions.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "exclusions": [
                    _mutation_exclusion(),
                    _mutation_exclusion(exclusion_id="equivalent-log-call"),
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, mutation_registry=registry_path)

    assert result.returncode == 1
    assert (
        "mutation_exclusions[1].path duplicates mutation_exclusions[0].path"
        in result.stderr
    )


def test_rejects_component_floor_below_programme_minimum(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["components"]["python"]["coverage"]["branches"] = 81

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "python.coverage.branches must be at least 82" in result.stderr


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


@pytest.mark.parametrize("root_path", (".", "./", ".\\"))
def test_rejects_repository_root_artifact_paths(
    tmp_path: Path,
    root_path: str,
) -> None:
    contract = _load_contract()
    contract["required_artifacts"] = [root_path]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "required_artifacts[0] must not refer to the repository root" in result.stderr
    )


@pytest.mark.parametrize("root_path", (".", "./", ".\\"))
def test_rejects_repository_root_exclusion_paths(
    tmp_path: Path,
    root_path: str,
) -> None:
    contract = _load_contract()
    contract["exclusions"] = [_exclusion(path=root_path)]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "exclusions[0].path must not refer to the repository root" in result.stderr


def test_rejects_windows_rooted_artifact_paths(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["required_artifacts"] = [r"\outside-repo\coverage.xml"]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "required_artifacts[0] must be a repository-relative path" in result.stderr


def test_accepts_quarantines_with_shared_path_and_distinct_tests(
    tmp_path: Path,
) -> None:
    contract = _load_contract()
    contract["quarantines"] = [
        _quarantine(
            quarantine_id="frontend-router-flake",
            test="frontend/src/__tests__/router.test.ts",
        ),
        _quarantine(
            quarantine_id="frontend-router-a11y-flake",
            test="frontend/src/__tests__/router-a11y.test.ts",
        ),
    ]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Quality contract is valid.\n"


def test_rejects_duplicate_quarantine_test_path_pair(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["quarantines"] = [
        _quarantine(
            quarantine_id="frontend-router-flake",
            test="frontend/src/__tests__/router.test.ts",
        ),
        _quarantine(
            quarantine_id="frontend-router-flake-duplicate",
            test="frontend/src/__tests__/router.test.ts",
        ),
    ]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "quarantines[1].test and path duplicate "
        "quarantines[0].test and path" in result.stderr
    )
    assert "quarantines[1].path duplicates quarantines[0].path" not in result.stderr


def test_rejects_unexpected_exclusion_fields(tmp_path: Path) -> None:
    contract = _load_contract()
    exclusion = _exclusion()
    exclusion["test"] = "frontend/src/__tests__/generated.test.ts"
    contract["exclusions"] = [exclusion]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "exclusions[0] contains unsupported key: test" in result.stderr


def test_rejects_unexpected_quarantine_fields(tmp_path: Path) -> None:
    contract = _load_contract()
    quarantine = _quarantine(
        quarantine_id="frontend-router-flake",
        test="frontend/src/__tests__/router.test.ts",
    )
    quarantine["unexpected"] = "value"
    contract["quarantines"] = [quarantine]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "quarantines[0] contains unsupported key: unexpected" in result.stderr


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


def test_manifest_enforces_tier0_coverage_per_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "quality-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "tier0": {
                    "files": [
                        {
                            "path": "app/api/auth/login.py",
                            "metrics": {
                                "lines": {
                                    "status": "native",
                                    "percent": 100,
                                },
                                "branches": {
                                    "status": "native",
                                    "percent": 100,
                                },
                                "functions": {
                                    "status": "native",
                                    "percent": 99.0,
                                },
                            },
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, manifest=manifest_path)

    assert result.returncode == 1
    assert "app/api/auth/login.py.functions must equal 100%" in result.stderr


def test_manifest_accepts_fully_covered_tier0_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "quality-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "tier0": {
                    "files": [
                        {
                            "path": "app/api/auth/login.py",
                            "metrics": {
                                metric: {"status": "native", "percent": 100}
                                for metric in ("lines", "branches", "functions")
                            },
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, manifest=manifest_path)

    assert result.returncode == 0
    assert "Quality contract is valid." in result.stdout


def test_rejects_malformed_json_with_usage_error(tmp_path: Path) -> None:
    contract_path = tmp_path / "quality-contract.json"
    contract_path.write_text('{"version": 1,', encoding="utf-8")

    result = _run_validator(tmp_path, contract_path)

    assert result.returncode == 2
    assert "ERROR: invalid JSON" in result.stderr


def test_rejects_deeply_nested_json_with_usage_error(tmp_path: Path) -> None:
    contract_path = tmp_path / "quality-contract.json"
    depth = 100_000
    contract_path.write_text(
        '{"nested":' * depth + "0" + "}" * depth,
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, contract_path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "ERROR: invalid JSON: nesting exceeds supported depth\n"
    assert "Traceback" not in result.stderr


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
