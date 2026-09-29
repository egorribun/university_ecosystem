from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.quality.coverage_provenance import (
    API_RETRY_SELECTION_RECEIPT_SCHEMA_VERSION,
    ProvenanceError,
    main,
    merge_metadata,
    write_api_selection_receipt,
    write_metadata,
)

# Construct the fixture SHA instead of embedding a high-entropy literal that
# secret scanners would reasonably treat as a credential candidate.
WORKFLOW_SHA = "a" * 40
WORKFLOW_REF = "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
COLLECTED_AT = "2026-08-25T12:34:56Z"
GIT = shutil.which("git")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    assert GIT is not None
    subprocess.run([GIT, "init", "-q"], cwd=tmp_path, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [
            GIT,
            "-c",
            "user.name=Quality Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def _head(repository: Path) -> str:
    assert GIT is not None
    return subprocess.check_output(  # noqa: S603
        [GIT, "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()


def _consumer(repository: Path, **overrides: str) -> dict[str, str]:
    values = {
        "expected_sha": _head(repository),
        "identity_provider": "github-actions",
        "repository": "example/university-ecosystem",
        "workflow_ref": WORKFLOW_REF,
        "workflow_sha": WORKFLOW_SHA,
        "run_id": "123456789",
        "run_attempt": "2",
        "event": "pull_request",
        "job": "coverage-policy-gate",
        "artifact": "quality-evidence-test",
        "collected_at": COLLECTED_AT,
    }
    values.update(overrides)
    return values


def _metadata(
    repository: Path,
    *,
    relative_path: str = "frontend/coverage/coverage-provenance.json",
    artifact: str = "frontend-coverage-attempt-1",
    run_attempt: str = "1",
    report_path: str = "frontend/coverage/coverage-final.json",
    component: str = "frontend",
    report_format: str = "istanbul-json",
) -> Path:
    report = repository / report_path
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_bytes(b'{"covered":true}\n')
    output = repository / relative_path
    write_metadata(
        repository_root=repository,
        output_path=output,
        reports=[
            (
                component,
                report_format,
                report_path,
                report_path,
            )
        ],
        tool_versions={"node": "24.7.0"},
        expected_sha=_head(repository),
        identity_provider="github-actions",
        repository="example/university-ecosystem",
        workflow_ref=WORKFLOW_REF,
        workflow_sha=WORKFLOW_SHA,
        run_id="123456789",
        run_attempt=run_attempt,
        event="pull_request",
        job="unit-tests",
        artifact=artifact,
        collected_at=COLLECTED_AT,
    )
    return output


def _contract(
    repository: Path,
    report_path: str,
    *extra_reports: tuple[str, str, str],
) -> Path:
    output = repository / "quality/quality-contract.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "coverage_reports": [
                    {
                        "component": "frontend",
                        "format": "istanbul-json",
                        "path": report_path,
                    },
                    *(
                        {
                            "component": component,
                            "format": report_format,
                            "path": path,
                        }
                        for component, report_format, path in extra_reports
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )
    return output


def _receipt_selection(
    repository: Path,
    metadata: Path,
    *,
    producer_job: str = "unit-tests",
    producer_attempt: int = 1,
    artifact_id: int = 917,
    artifact_name: str | None = None,
    artifact_digest: str | None = None,
) -> tuple[Path, str, int, int, str, str]:
    resolved_artifact_name = artifact_name or (
        f"frontend-coverage-attempt-{producer_attempt}"
    )
    resolved_artifact_digest = artifact_digest or ("sha256:" + "c" * 64)
    return (
        metadata.relative_to(repository),
        producer_job,
        producer_attempt,
        artifact_id,
        resolved_artifact_name,
        resolved_artifact_digest,
    )


def _receipt_identity(repository: Path) -> dict[str, str]:
    consumer = _consumer(repository)
    return {
        key: consumer[key]
        for key in (
            "expected_sha",
            "repository",
            "workflow_ref",
            "workflow_sha",
            "run_id",
            "run_attempt",
            "event",
            "job",
        )
    }


def _write_single_receipt(repository: Path) -> tuple[Path, Path]:
    metadata = _metadata(repository)
    receipt = repository / "api-selection-receipt.json"
    write_api_selection_receipt(
        repository_root=repository,
        output_path=receipt,
        selections=[_receipt_selection(repository, metadata)],
        **_receipt_identity(repository),
    )
    return metadata, receipt


def _merge_api_receipt(
    repository: Path,
    metadata_paths: list[Path],
    receipt: Path,
    *,
    contract: Path | None = None,
    producer_expectations: dict[Path, tuple[str, str]] | None = None,
    **consumer_overrides: str,
) -> dict[str, object]:
    values = _consumer(repository)
    values.update(consumer_overrides)
    expectations = producer_expectations or {
        metadata_path: ("unit-tests", "frontend-coverage-attempt-1")
        for metadata_path in metadata_paths
    }
    contract_path = contract or _contract(
        repository, "frontend/coverage/coverage-final.json"
    )
    return merge_metadata(
        repository_root=repository,
        contract_path=contract_path,
        metadata_paths=metadata_paths,
        output_path=repository / "aggregate.json",
        tool_versions={"quality-provenance": "2.0.0"},
        producer_expectations=expectations,
        retry_selection_receipt=receipt,
        **values,
    )


def test_api_receipt_allows_selected_prior_attempt_and_rechecks_hashes(
    repository: Path,
) -> None:
    metadata = _metadata(repository)
    contract = _contract(repository, "frontend/coverage/coverage-final.json")
    receipt = repository / "artifacts/coverage/provenance/api-selection-receipt.json"
    write_api_selection_receipt(
        repository_root=repository,
        output_path=receipt,
        selections=[_receipt_selection(repository, metadata)],
        **_receipt_identity(repository),
    )
    with pytest.raises(ProvenanceError, match=r"producer\.run_attempt"):
        merge_metadata(
            repository_root=repository,
            contract_path=contract,
            metadata_paths=[metadata],
            output_path=repository / "aggregate-without-receipt.json",
            tool_versions={"quality-provenance": "2.0.0"},
            producer_expectations={
                metadata: ("unit-tests", "frontend-coverage-attempt-1")
            },
            **_consumer(repository),
        )

    aggregate = merge_metadata(
        repository_root=repository,
        contract_path=contract,
        metadata_paths=[metadata],
        output_path=repository / "aggregate.json",
        tool_versions={"quality-provenance": "2.0.0"},
        producer_expectations={metadata: ("unit-tests", "frontend-coverage-attempt-1")},
        retry_selection_receipt=receipt,
        **_consumer(repository),
    )
    assert aggregate["reports"][0]["path"] == "frontend/coverage/coverage-final.json"
    parsed_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    assert (
        parsed_receipt["schema_version"] == API_RETRY_SELECTION_RECEIPT_SCHEMA_VERSION
    )
    assert (
        parsed_receipt["selections"][0]["metadata_sha256"]
        == hashlib.sha256(metadata.read_bytes()).hexdigest()
    )
    report = repository / "frontend/coverage/coverage-final.json"
    receipt_report = parsed_receipt["selections"][0]["reports"][0]
    assert receipt_report["sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
    assert receipt_report["byte_size"] == report.stat().st_size


def test_api_receipt_must_cover_hashes_and_exact_producer_identity(
    repository: Path,
) -> None:
    metadata = _metadata(repository)
    contract = _contract(repository, "frontend/coverage/coverage-final.json")
    receipt = repository / "api-selection-receipt.json"
    write_api_selection_receipt(
        repository_root=repository,
        output_path=receipt,
        selections=[_receipt_selection(repository, metadata)],
        **_receipt_identity(repository),
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["selections"][0]["metadata_sha256"] = "0" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="API selection receipt"):
        merge_metadata(
            repository_root=repository,
            contract_path=contract,
            metadata_paths=[metadata],
            output_path=repository / "aggregate.json",
            tool_versions={"quality-provenance": "2.0.0"},
            producer_expectations={
                metadata: ("unit-tests", "frontend-coverage-attempt-1")
            },
            retry_selection_receipt=receipt,
            **_consumer(repository),
        )


def test_api_receipt_rejects_report_bytes_changed_after_receipt(
    repository: Path,
) -> None:
    metadata = _metadata(repository)
    contract = _contract(repository, "frontend/coverage/coverage-final.json")
    receipt = repository / "api-selection-receipt.json"
    write_api_selection_receipt(
        repository_root=repository,
        output_path=receipt,
        selections=[_receipt_selection(repository, metadata)],
        **_receipt_identity(repository),
    )
    # Keep the size stable so the test exercises the digest check rather than
    # only the independently recorded byte-size check.
    (repository / "frontend/coverage/coverage-final.json").write_bytes(
        b'{"covered":fals}\n'
    )
    with pytest.raises(ProvenanceError, match=r"reports\[0\]\.sha256 mismatch"):
        merge_metadata(
            repository_root=repository,
            contract_path=contract,
            metadata_paths=[metadata],
            output_path=repository / "aggregate.json",
            tool_versions={"quality-provenance": "2.0.0"},
            producer_expectations={
                metadata: ("unit-tests", "frontend-coverage-attempt-1")
            },
            retry_selection_receipt=receipt,
            **_consumer(repository),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commit_sha", "f" * 40),
        ("repository", "attacker/example"),
        ("run_id", "999999999"),
        ("run_attempt", "3"),
        ("workflow_ref", "attacker/example/.github/workflows/ci.yml@main"),
        ("workflow_sha", "e" * 40),
        ("event", "workflow_dispatch"),
        ("job", "untrusted-job"),
    ],
)
def test_api_receipt_rejects_every_consumer_identity_mismatch(
    repository: Path, field: str, value: str
) -> None:
    metadata, receipt = _write_single_receipt(repository)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["consumer"][field] = value
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=rf"consumer\.{field} mismatch"):
        _merge_api_receipt(repository, [metadata], receipt)


@pytest.mark.parametrize(
    ("producer_attempt", "artifact_name", "expected_artifact", "match"),
    [
        (
            0,
            "frontend-coverage-attempt-1",
            "frontend-coverage-attempt-1",
            "producer_attempt must be a positive integer",
        ),
        (
            3,
            "frontend-coverage-attempt-3",
            "frontend-coverage-attempt-3",
            "producer attempt is from the future",
        ),
    ],
)
def test_api_receipt_rejects_invalid_or_future_producer_attempt(
    repository: Path,
    producer_attempt: int,
    artifact_name: str,
    expected_artifact: str,
    match: str,
) -> None:
    metadata, receipt = _write_single_receipt(repository)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["selections"][0]["producer_attempt"] = producer_attempt
    payload["selections"][0]["artifact_name"] = artifact_name
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=match):
        _merge_api_receipt(
            repository,
            [metadata],
            receipt,
            producer_expectations={
                metadata: ("unit-tests", expected_artifact),
            },
        )


@pytest.mark.parametrize("duplicate_field", ["artifact_id", "artifact_name"])
def test_api_receipt_rejects_duplicate_artifact_identity(
    repository: Path, duplicate_field: str
) -> None:
    first = _metadata(repository)
    second = _metadata(
        repository,
        relative_path="frontend/coverage/coverage-provenance-second.json",
        artifact="frontend-coverage-second-attempt-1",
        report_path="frontend/coverage/coverage-final-second.json",
    )
    first_selection = _receipt_selection(repository, first)
    second_selection = _receipt_selection(
        repository,
        second,
        artifact_id=918,
        artifact_name="frontend-coverage-second-attempt-1",
    )
    receipt = repository / "api-selection-receipt.json"
    write_api_selection_receipt(
        repository_root=repository,
        output_path=receipt,
        selections=[first_selection, second_selection],
        **_receipt_identity(repository),
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    first_record = next(
        selection
        for selection in payload["selections"]
        if selection["artifact_name"] == "frontend-coverage-attempt-1"
    )
    second_record = next(
        selection
        for selection in payload["selections"]
        if selection["artifact_name"] == "frontend-coverage-second-attempt-1"
    )
    if duplicate_field == "artifact_id":
        second_record["artifact_id"] = first_record["artifact_id"]
        expectations = {
            first: ("unit-tests", "frontend-coverage-attempt-1"),
            second: ("unit-tests", "frontend-coverage-second-attempt-1"),
        }
        match = "duplicate artifact id"
    else:
        second_record["artifact_name"] = first_record["artifact_name"]
        expectations = {
            first: ("unit-tests", "frontend-coverage-attempt-1"),
            second: ("unit-tests", "frontend-coverage-attempt-1"),
        }
        match = "duplicate artifact name"
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    contract = _contract(
        repository,
        "frontend/coverage/coverage-final.json",
        ("frontend", "istanbul-json", "frontend/coverage/coverage-final-second.json"),
    )
    with pytest.raises(ProvenanceError, match=match):
        _merge_api_receipt(
            repository,
            [first, second],
            receipt,
            contract=contract,
            producer_expectations=expectations,
        )


def test_api_receipt_rejects_invalid_artifact_digest(repository: Path) -> None:
    metadata, receipt = _write_single_receipt(repository)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["selections"][0]["artifact_digest"] = "sha256:" + "z" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match="artifact_digest must be a SHA-256"):
        _merge_api_receipt(repository, [metadata], receipt)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (
            "producer_job",
            "untrusted-job",
            "producer job does not match expectation",
        ),
        (
            "artifact_name",
            "untrusted-artifact-attempt-1",
            "artifact name does not match expectation",
        ),
    ],
)
def test_api_receipt_rejects_mismatched_producer_identity(
    repository: Path, field: str, value: str, match: str
) -> None:
    metadata, receipt = _write_single_receipt(repository)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["selections"][0][field] = value
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=match):
        _merge_api_receipt(repository, [metadata], receipt)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (
            "sha256",
            "0" * 64,
            "canonical metadata report inventory does not match",
        ),
        (
            "byte_size",
            999,
            "canonical metadata report inventory does not match",
        ),
        (
            "path",
            "frontend/coverage/other-report.json",
            "canonical metadata report inventory does not match",
        ),
        (
            "path",
            "../outside.json",
            "must be a safe repository-relative POSIX path",
        ),
    ],
)
def test_api_receipt_rejects_report_hash_size_or_path_tampering(
    repository: Path, field: str, value: object, match: str
) -> None:
    metadata, receipt = _write_single_receipt(repository)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["selections"][0]["reports"][0][field] = value
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=match):
        _merge_api_receipt(repository, [metadata], receipt)


def test_api_receipt_writer_rejects_wrong_head_without_output(
    repository: Path,
) -> None:
    metadata = _metadata(repository)
    output = repository / "artifacts/api-selection-receipt.json"
    identity = _receipt_identity(repository)
    identity["expected_sha"] = "f" * 40

    with pytest.raises(
        ProvenanceError, match="expected_sha does not match current repository HEAD"
    ):
        write_api_selection_receipt(
            repository_root=repository,
            output_path=output,
            selections=[_receipt_selection(repository, metadata)],
            **identity,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("repository", "", "repository must be a non-empty string"),
        ("workflow_sha", "not-a-sha", "workflow_sha must be an exact lowercase"),
        ("run_attempt", "0", "run_attempt must be a positive decimal identifier"),
    ],
)
def test_api_receipt_writer_rejects_invalid_identity_without_output(
    repository: Path, field: str, value: str, match: str
) -> None:
    metadata = _metadata(repository)
    output = repository / "artifacts/api-selection-receipt.json"
    identity = _receipt_identity(repository)
    identity[field] = value

    with pytest.raises(ProvenanceError, match=match):
        write_api_selection_receipt(
            repository_root=repository,
            output_path=output,
            selections=[_receipt_selection(repository, metadata)],
            **identity,
        )
    assert not output.exists()


def test_api_receipt_is_a_subset_for_current_aggregate_sidecars(
    repository: Path,
) -> None:
    selected = _metadata(repository)
    current = _metadata(
        repository,
        relative_path="artifacts/coverage/provenance/python.json",
        artifact="python-coverage-aggregate",
        run_attempt="2",
        report_path="artifacts/coverage/python/coverage.json",
        component="python",
        report_format="coverage-py-json",
    )
    contract = _contract(
        repository,
        "frontend/coverage/coverage-final.json",
        ("python", "coverage-py-json", "artifacts/coverage/python/coverage.json"),
    )
    receipt = repository / "api-selection-receipt.json"
    write_api_selection_receipt(
        repository_root=repository,
        output_path=receipt,
        selections=[_receipt_selection(repository, selected)],
        **_receipt_identity(repository),
    )
    # The current-job aggregate is intentionally omitted from the API receipt.
    # It remains protected by ordinary exact verification.
    merge_metadata(
        repository_root=repository,
        contract_path=contract,
        metadata_paths=[selected, current],
        output_path=repository / "aggregate.json",
        tool_versions={"quality-provenance": "2.0.0"},
        producer_expectations={
            selected: ("unit-tests", "frontend-coverage-attempt-1"),
            current: ("unit-tests", "python-coverage-aggregate"),
        },
        retry_selection_receipt=receipt,
        **_consumer(repository),
    )


def test_api_receipt_cli_writes_the_same_validated_contract(repository: Path) -> None:
    metadata = _metadata(repository)
    selection = _receipt_selection(repository, metadata)
    output = repository / "api-selection-receipt.json"
    identity = _receipt_identity(repository)
    arguments = [
        "write-api-receipt",
        "--repository-root",
        str(repository),
        "--output",
        str(output),
        "--selection",
        "|".join(
            [
                str(selection[0]),
                selection[1],
                str(selection[2]),
                str(selection[3]),
                selection[4],
                selection[5],
            ]
        ),
        "--expected-sha",
        identity["expected_sha"],
        "--repository",
        identity["repository"],
        "--workflow-ref",
        identity["workflow_ref"],
        "--workflow-sha",
        identity["workflow_sha"],
        "--run-id",
        identity["run_id"],
        "--run-attempt",
        identity["run_attempt"],
        "--event",
        identity["event"],
        "--job",
        identity["job"],
    ]
    assert main(arguments) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 2
