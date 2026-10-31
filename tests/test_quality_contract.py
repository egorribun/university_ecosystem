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


def _quality_validator_module() -> object:
    module_directory = str(REPOSITORY_ROOT / "scripts" / "quality")
    sys.path.insert(0, module_directory)
    try:
        import validate_quality_contract as validator
    finally:
        sys.path.remove(module_directory)
    return validator


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


def test_quality_contract_declares_v3_manifest_semantics(tmp_path: Path) -> None:
    contract = _load_contract()
    declaration = contract["coverage_manifest"]
    assert isinstance(declaration, dict)
    assert declaration == {"schema_version": 3, "normalizer_version": "3.0.0"}

    declaration["schema_version"] = 2
    result = _run_contract(tmp_path, contract)
    assert result.returncode != 0
    assert "coverage_manifest.schema_version must equal 3" in result.stderr


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


def test_rejects_every_supported_component_floor_below_100(tmp_path: Path) -> None:
    contract = _load_contract()
    components = contract["components"]
    assert isinstance(components, dict)
    lowered_fields: list[str] = []
    for component_name, component in components.items():
        assert isinstance(component, dict)
        coverage = component["coverage"]
        assert isinstance(coverage, dict)
        for metric, threshold in coverage.items():
            if threshold == 0:
                continue
            coverage[metric] = 99
            lowered_fields.append(f"{component_name}.coverage.{metric}")

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert lowered_fields
    for field in lowered_fields:
        assert f"{field} must be at least 100" in result.stderr


def test_zero_component_floor_requires_explicit_unsupported_status(
    tmp_path: Path,
) -> None:
    contract = _load_contract()
    # Go line coverage is a trusted derived metric and therefore has a 100%
    # floor. A forged zero floor must not regain the historical implicit N/A
    # bypass when the status matrix does not declare ``unsupported``.
    contract["components"]["go-gateway"]["coverage"]["lines"] = 0

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "go-gateway.coverage.lines must be at least 100; zero floor requires "
        "metric_statuses.go-gateway.lines to allow unsupported"
    ) in result.stderr


def test_contract_declares_explicit_metric_status_semantics() -> None:
    contract = _load_contract()
    statuses = contract["metric_statuses"]
    assert isinstance(statuses, dict)
    assert statuses["python"]["functions"] == ["derived", "unsupported"]
    assert statuses["go-gateway"]["lines"] == ["derived"]
    assert statuses["go-gateway"]["statements"] == ["native"]
    assert statuses["go-gateway"]["branches"] == ["unsupported"]
    assert statuses["rust-crypto"]["statements"] == ["unsupported"]


def test_rejects_contract_without_explicit_metric_status_semantics(
    tmp_path: Path,
) -> None:
    contract = _load_contract()
    del contract["metric_statuses"]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "contract is missing required key: metric_statuses" in result.stderr


def test_rejects_incomplete_metric_status_semantics(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["metric_statuses"]["frontend"]["branches"] = ["missing"]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "metric_statuses.frontend.branches contains unsupported status: missing"
        in result.stderr
    )


def test_rejects_coverage_scope_outside_declared_source_roots(tmp_path: Path) -> None:
    contract = _load_contract()
    coverage_scope = contract["coverage_scope"]
    assert isinstance(coverage_scope, dict)
    coverage_scope["python"] = ["services/gateway"]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "coverage_scope.python[0] must be contained by source_roots.python"
        in result.stderr
    )


def test_rejects_missing_coverage_scope_without_traceback(tmp_path: Path) -> None:
    contract = _load_contract()
    del contract["coverage_scope"]

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "contract is missing required key: coverage_scope" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "metric",
    ("lines", "statements", "branches", "functions", "tier0"),
)
def test_rejects_aggregate_coverage_minimum_below_100(
    tmp_path: Path,
    metric: str,
) -> None:
    contract = _load_contract()
    contract["coverage_minimums"][metric] = 99

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert f"coverage_minimums.{metric} must equal 100" in result.stderr


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
    contract["coverage_reports"][0]["path"] = root_path

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "coverage_reports[0].path must not refer to the repository root"
        in result.stderr
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
    contract["coverage_reports"][0]["path"] = r"\outside-repo\coverage.xml"

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert (
        "coverage_reports[0].path must be a repository-relative path" in result.stderr
    )


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
    assert "version must equal 2" in result.stderr


def test_rejects_tier0_coverage_below_100(tmp_path: Path) -> None:
    contract = _load_contract()
    contract["tier0"]["coverage"]["functions"] = 99

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert "tier0.coverage.functions must equal 100" in result.stderr


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("expiry", "expires_on must be after validation day"),
        ("unknown_path", "canonical Alembic Python path"),
        ("duplicate_path", "duplicates an earlier baseline"),
        ("source_hash", "contains unsupported key: source_sha256"),
        ("extra_record", "exactly 131 approved paths"),
        ("changed_approved_path", "immutable baseline digest"),
        ("metric_baseline", "immutable baseline digest"),
    ),
)
def test_legacy_migration_exception_fails_closed_on_policy_changes(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    contract = _load_contract()
    policy = contract["tier0"]["legacy_migration_baselines"]
    records = policy["files"]
    if mutation == "expiry":
        policy["expires_on"] = date.today().isoformat()
    elif mutation == "unknown_path":
        records[-1]["path"] = "app/services/unauthorized.py"
    elif mutation == "duplicate_path":
        records[-1]["path"] = records[0]["path"]
    elif mutation == "source_hash":
        records[0]["source_sha256"] = "0" * 64
    elif mutation == "extra_record":
        records.append(records[0])
    elif mutation == "changed_approved_path":
        records[0]["path"] = "alembic/versions/202607020001_create_range_partitions.py"
    elif mutation == "metric_baseline":
        records[0]["metrics"]["lines"]["covered"] += 1
    else:
        raise AssertionError(f"unexpected policy mutation: {mutation}")

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert message in result.stderr


def test_nonbaseline_migration_functions_require_evidence_at_validator_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    path = "alembic/versions/future_revision.py"
    rule = "migration-fixture-rule"
    monkeypatch.setattr(validator, "_load_canonical_tier0_rules", lambda *_: [rule])
    monkeypatch.setattr(
        validator,
        "_expected_tier0_inventory",
        lambda *_: {("python", path)},
    )
    monkeypatch.setattr(
        validator,
        "_validate_legacy_migration_source_binding",
        lambda *_: ([], frozenset()),
    )
    monkeypatch.setattr(validator, "_safe_repository_file", lambda *_: Path(__file__))
    monkeypatch.setattr(validator, "_tier0_rule_matches", lambda *_: True)

    unsupported = {
        "status": "unsupported",
        "covered": None,
        "total": None,
        "percent": None,
        "reason_code": "fixture_counter_unavailable",
    }
    unsupported_errors = validator._validate_tier0_manifest(
        _future_migration_tier0_manifest(path, rule, unsupported, contract),
        contract,
        REPOSITORY_ROOT,
    )
    assert any(
        f"{path}.functions is unsupported but its component floor is 100" in error
        for error in unsupported_errors
    )

    derived_zero = {
        "status": "derived",
        "covered": 0,
        "total": 0,
        "percent": 100.0,
        "derivation": "AST source contains no function definitions",
    }
    accepted_errors = validator._validate_tier0_manifest(
        _future_migration_tier0_manifest(path, rule, derived_zero, contract),
        contract,
        REPOSITORY_ROOT,
    )
    assert accepted_errors == []


def _future_migration_tier0_manifest(
    path: str,
    rule: str,
    function_metric: dict[str, object],
    contract: dict[str, object],
) -> dict[str, object]:
    measured = {"status": "native", "covered": 1, "total": 1, "percent": 100.0}
    return _tier0_manifest_for_metrics(
        path,
        rule,
        {
            "lines": measured,
            "statements": measured,
            "branches": measured,
            "functions": function_metric,
        },
        contract,
    )


def _tier0_manifest_for_metrics(
    path: str,
    rule: str,
    file_metrics: dict[str, dict[str, object]],
    contract: dict[str, object],
) -> dict[str, object]:
    aggregate_metrics = {name: dict(metric) for name, metric in file_metrics.items()}
    summary = {
        name: {
            "applicable_files": int(metric["status"] in {"native", "derived"}),
            "not_applicable_files": int(metric["status"] == "unsupported"),
        }
        for name, metric in file_metrics.items()
    }
    return {
        "coverage_scope": contract["coverage_scope"],
        "source_roots": contract["source_roots"],
        "tier0": {
            "status": "ready",
            "errors": [],
            "rules": [rule],
            "files": [{"path": path, "component": "python", "metrics": file_metrics}],
            "metric_summary": summary,
            "coverage": aggregate_metrics,
        },
    }


def _prepare_legacy_migration_manifest_case(
    monkeypatch: pytest.MonkeyPatch,
    validator: object,
    contract: dict[str, object],
    path: str,
    unchanged_paths: frozenset[str],
) -> str:
    rule = "migration-fixture-rule"
    monkeypatch.setattr(validator, "_load_canonical_tier0_rules", lambda *_: [rule])
    monkeypatch.setattr(
        validator, "_expected_tier0_inventory", lambda *_: {("python", path)}
    )
    monkeypatch.setattr(
        validator,
        "_validate_legacy_migration_source_binding",
        lambda *_: ([], unchanged_paths),
    )
    monkeypatch.setattr(validator, "_safe_repository_file", lambda *_: Path(__file__))
    monkeypatch.setattr(validator, "_tier0_rule_matches", lambda *_: True)
    return rule


def _full_coverage_metrics() -> dict[str, dict[str, object]]:
    metrics = {
        metric: {"status": "native", "covered": 100, "total": 100, "percent": 100.0}
        for metric in ("lines", "statements", "branches")
    }
    metrics["functions"] = {
        "status": "derived",
        "covered": 100,
        "total": 100,
        "percent": 100.0,
        "derivation": (
            "AST function entries covered when the first executable body line "
            "is reported as executed"
        ),
    }
    return metrics


@pytest.mark.parametrize(
    "path",
    (
        "alembic/versions/148642dd1207_fix_missing_tables.py",
        "alembic/versions/202509010001_merge_push_topics_and_email_heads.py",
    ),
)
def test_changed_listed_migration_at_100_percent_passes_strict_floor(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    declared_paths = frozenset(
        record["path"]
        for record in contract["tier0"]["legacy_migration_baselines"]["files"]
    )
    unchanged_paths = declared_paths - {path}
    rule = _prepare_legacy_migration_manifest_case(
        monkeypatch, validator, contract, path, unchanged_paths
    )
    manifest = _tier0_manifest_for_metrics(
        path, rule, _full_coverage_metrics(), contract
    )

    errors = validator._validate_tier0_manifest(manifest, contract, REPOSITORY_ROOT)

    assert errors == []


@pytest.mark.parametrize(
    "path",
    (
        "alembic/versions/148642dd1207_fix_missing_tables.py",
        "alembic/versions/202509010001_merge_push_topics_and_email_heads.py",
    ),
)
@pytest.mark.parametrize(
    "metric_name", ("lines", "statements", "branches", "functions")
)
def test_changed_listed_migration_rejects_99_percent_for_every_metric(
    monkeypatch: pytest.MonkeyPatch, path: str, metric_name: str
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    declared_paths = frozenset(
        record["path"]
        for record in contract["tier0"]["legacy_migration_baselines"]["files"]
    )
    unchanged_paths = declared_paths - {path}
    rule = _prepare_legacy_migration_manifest_case(
        monkeypatch, validator, contract, path, unchanged_paths
    )
    metrics = _full_coverage_metrics()
    metrics[metric_name] = {
        **metrics[metric_name],
        "covered": 99,
        "total": 100,
        "percent": 99.0,
    }
    manifest = _tier0_manifest_for_metrics(path, rule, metrics, contract)

    errors = validator._validate_tier0_manifest(manifest, contract, REPOSITORY_ROOT)

    assert any(
        f"{path}.{metric_name} is applicable and must equal 100%" in error
        for error in errors
    )


@pytest.mark.parametrize(
    "path",
    (
        "alembic/versions/148642dd1207_fix_missing_tables.py",
        "alembic/versions/202509010001_merge_push_topics_and_email_heads.py",
    ),
)
def test_changed_listed_migration_rejects_unsupported_function_evidence(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    declared_paths = frozenset(
        record["path"]
        for record in contract["tier0"]["legacy_migration_baselines"]["files"]
    )
    unchanged_paths = declared_paths - {path}
    rule = _prepare_legacy_migration_manifest_case(
        monkeypatch, validator, contract, path, unchanged_paths
    )
    metrics = _full_coverage_metrics()
    metrics["functions"] = {
        "status": "unsupported",
        "covered": None,
        "total": None,
        "percent": None,
        "reason_code": "fixture_counter_unavailable",
    }
    manifest = _tier0_manifest_for_metrics(path, rule, metrics, contract)

    errors = validator._validate_tier0_manifest(manifest, contract, REPOSITORY_ROOT)

    assert any(
        f"{path}.functions is unsupported but its component floor is 100" in error
        for error in errors
    )


def test_unchanged_listed_migration_keeps_approved_no_decrease_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    path = "alembic/versions/148642dd1207_fix_missing_tables.py"
    baseline_records = {
        record["path"]: record
        for record in contract["tier0"]["legacy_migration_baselines"]["files"]
    }
    unchanged_paths = frozenset(baseline_records)
    rule = _prepare_legacy_migration_manifest_case(
        monkeypatch, validator, contract, path, unchanged_paths
    )
    baseline_metrics = baseline_records[path]["metrics"]
    metrics: dict[str, dict[str, object]] = {}
    for metric_name, baseline in baseline_metrics.items():
        metric = dict(baseline)
        metric["percent"] = validator._expected_metric_percent(
            baseline["covered"], baseline["total"]
        )
        metrics[metric_name] = metric
    manifest = _tier0_manifest_for_metrics(path, rule, metrics, contract)

    errors = validator._validate_tier0_manifest(manifest, contract, REPOSITORY_ROOT)

    assert errors == []


def test_legacy_migration_exception_is_source_bound_to_approved_subset() -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    policy = contract["tier0"]["legacy_migration_baselines"]
    declared_paths = {record["path"] for record in policy["files"]}

    errors, unchanged_paths = validator._validate_legacy_migration_source_binding(
        contract, REPOSITORY_ROOT
    )

    assert len(declared_paths) == 131
    assert policy["expires_on"] == "2026-11-13"
    assert errors == []
    assert set(unchanged_paths) <= declared_paths
    assert len(unchanged_paths) == len(set(unchanged_paths))


def test_legacy_migration_exception_treats_changed_blob_as_strict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    original_errors, original_unchanged = (
        validator._validate_legacy_migration_source_binding(contract, REPOSITORY_ROOT)
    )
    assert original_errors == []
    changed_path = sorted(original_unchanged)[0]
    changed_source = tmp_path / "changed-migration.py"
    changed_source.write_text("revision = 'changed'\n", encoding="utf-8")
    original_safe_file = validator._safe_repository_file

    def safe_file_with_changed_blob(
        repository_root: Path, path: str, field: str, errors: list[str]
    ) -> Path | None:
        if path == changed_path:
            return changed_source
        return original_safe_file(repository_root, path, field, errors)

    monkeypatch.setattr(validator, "_safe_repository_file", safe_file_with_changed_blob)
    errors, unchanged_paths = validator._validate_legacy_migration_source_binding(
        contract, REPOSITORY_ROOT
    )

    assert errors == []
    assert changed_path not in unchanged_paths
    assert set(unchanged_paths) == set(original_unchanged) - {changed_path}


@pytest.mark.parametrize(
    "replacement_path",
    (
        "alembic/versions/202607020001_create_range_partitions.py",
        "alembic/versions/202610120001_dnd_wall_clock_time.py",
        "alembic/versions/new_unreviewed_revision.py",
        "app/services/not_a_migration.py",
    ),
)
def test_legacy_migration_exception_rejects_unapproved_record_edits(
    replacement_path: str,
) -> None:
    validator = _quality_validator_module()
    contract = _load_contract()
    policy = contract["tier0"]["legacy_migration_baselines"]
    policy["files"][0]["path"] = replacement_path
    errors: list[str] = []

    validator._validate_legacy_migration_baselines(
        policy, today=date(2026, 10, 23), errors=errors
    )

    assert any("immutable baseline digest" in error for error in errors)


def test_legacy_migration_baseline_allows_improvement_but_rejects_regression() -> None:
    validator = _quality_validator_module()
    baseline = {"status": "native", "covered": 8, "total": 10}
    improved = {"status": "native", "covered": 9, "total": 10, "percent": 90.0}
    regressed = {"status": "native", "covered": 7, "total": 10, "percent": 70.0}

    assert (
        validator.validate_metric_at_legacy_baseline(
            improved,
            baseline,
            field="alembic/versions/sample.py.lines",
            allowed_statuses=frozenset({"native"}),
        )
        == []
    )
    assert any(
        "covered regressed" in error
        for error in validator.validate_metric_at_legacy_baseline(
            regressed,
            baseline,
            field="alembic/versions/sample.py.lines",
            allowed_statuses=frozenset({"native"}),
        )
    )


def test_python_aggregate_misses_must_equal_current_migration_residual() -> None:
    validator = _quality_validator_module()
    allowed = validator.validate_metric_with_exact_missing(
        {"status": "native", "covered": 95, "total": 100, "percent": 95.0},
        expected_missing=5,
        field="components.python.lines",
        allowed_statuses=frozenset({"native"}),
    )
    additional_app_gap = validator.validate_metric_with_exact_missing(
        {"status": "native", "covered": 94, "total": 100, "percent": 94.0},
        expected_missing=5,
        field="components.python.lines",
        allowed_statuses=frozenset({"native"}),
    )

    assert allowed == []
    assert any("legacy-migration residual" in error for error in additional_app_gap)


@pytest.mark.parametrize("field", ("patch_coverage", "viable_mutant_score"))
def test_rejects_policy_floor_below_100(tmp_path: Path, field: str) -> None:
    contract = _load_contract()
    policy = contract["policy"]
    assert isinstance(policy, dict)
    policy[field] = 99

    result = _run_contract(tmp_path, contract)

    assert result.returncode == 1
    assert f"policy.{field} must equal 100" in result.stderr


def test_manifest_rejects_obsolete_v1_shape_before_semantic_validation(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "quality-manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "tier0": {"files": []}}),
        encoding="utf-8",
    )

    result = _run_validator(tmp_path, manifest=manifest_path)

    assert result.returncode == 1
    assert "schema" in result.stderr


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
