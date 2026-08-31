from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

pytest_plugins = ("tests.test_quality_normalizer_v2",)

from tests.test_quality_normalizer_v2 import (
    SCHEMA_PATH,
    _full_arguments,
    _head,
    _run,
)


def test_normalizer_emits_explicit_source_tested_and_base_identity(
    evidence_repo: Path,
) -> None:
    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["schema_version"] == 3
    current = _head(evidence_repo)
    assert manifest["commit_sha"] == current
    assert manifest["tested_commit_sha"] == current
    assert manifest["source_head_sha"] == current
    assert manifest["base_sha"] == current
    assert manifest["base_ref"] == "local"
    Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))).validate(
        manifest
    )


def test_schema_v3_rejects_manifest_without_commit_provenance_fields() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    manifest = {
        "schema_version": 2,
        "commit_sha": "0" * 40,
    }

    errors = list(validator.iter_errors(manifest))

    assert errors
    assert any("3 was expected" in error.message for error in errors)


def test_normalizer_rejects_nonlocal_provenance_without_explicit_identity(
    evidence_repo: Path,
) -> None:
    arguments = [*_full_arguments(evidence_repo)]
    arguments[arguments.index("--provenance-mode") + 1] = "github-actions"

    result = _run(evidence_repo, arguments)

    assert result.returncode == 2
    assert "provenance" in result.stderr


def test_normalizer_preserves_pull_request_source_and_tested_commits(
    evidence_repo: Path,
) -> None:
    arguments = [*_full_arguments(evidence_repo)]
    arguments[arguments.index("--provenance-mode") + 1] = "github-actions"
    current = _head(evidence_repo)
    source = "1" * 40
    base = "2" * 40
    arguments.extend(
        [
            "--source-head-sha",
            source,
            "--base-sha",
            base,
            "--base-ref",
            "main",
            "--workflow-run-id",
            "123",
            "--workflow-run-attempt",
            "1",
            "--workflow-event",
            "pull_request",
            "--workflow-repository",
            "example/university-ecosystem",
            "--workflow-ref",
            "refs/pull/1/merge",
            "--workflow-job",
            "quality",
        ]
    )

    result = _run(evidence_repo, arguments)

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["source_head_sha"] == source
    assert manifest["tested_commit_sha"] == current
    assert manifest["base_sha"] == base
    assert manifest["base_ref"] == "main"


def test_validator_rejects_swapped_source_and_tested_identity(
    evidence_repo: Path,
) -> None:
    result = _run(evidence_repo, _full_arguments(evidence_repo))
    assert result.returncode == 0, result.stderr
    manifest_path = evidence_repo / "artifacts/coverage/quality-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_head_sha"], manifest["tested_commit_sha"] = (
        "1" * 40,
        "2" * 40,
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    from scripts.quality.validate_quality_contract import validate_manifest_evidence

    contract = json.loads(
        (evidence_repo / "quality/quality-contract.json").read_text(encoding="utf-8")
    )
    errors = validate_manifest_evidence(
        manifest,
        contract=contract,
        manifest_path=manifest_path,
        repository_root=evidence_repo,
        schema_path=evidence_repo / "quality/coverage-manifest.schema.json",
    )

    assert any("commit_sha must equal tested_commit_sha" in error for error in errors)
    assert any(
        "tested_commit_sha must equal current repository HEAD" in error
        for error in errors
    )
