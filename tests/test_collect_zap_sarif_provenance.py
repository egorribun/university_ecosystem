from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".github/workflows/dast.yml").is_file():
            return candidate
    raise AssertionError("Could not locate the projected DAST workflow")


REPOSITORY_ROOT = _repository_root()
COLLECTOR_PATH = Path(__file__).with_name("collect_zap_sarif_provenance.py")
if not COLLECTOR_PATH.is_file():
    COLLECTOR_PATH = REPOSITORY_ROOT / Path("scripts/quality/zap_sarif_provenance.py")
SPEC = importlib.util.spec_from_file_location(
    "collect_zap_sarif_provenance", COLLECTOR_PATH
)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def _event_sha() -> str:
    return hashlib.sha256(b"zaproxy-test-source").hexdigest()[:40]


def _sarif_document(*, level: str = "warning") -> dict[str, Any]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "OWASP ZAP",
                        "rules": [{"id": "example-rule"}],
                    }
                },
                "results": [
                    {
                        "ruleId": "example-rule",
                        "level": level,
                    }
                ],
            }
        ],
    }


def _checkout(root: Path, *, sarif: dict[str, Any] | None = None) -> Path:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "dast.yml").write_text(
        "name: DAST\n", encoding="utf-8"
    )
    (root / ".zap").mkdir()
    (root / ".zap" / "rules.tsv").write_text("rule\tstate\n", encoding="utf-8")
    report = root / "zap-results.sarif"
    report.write_text(
        json.dumps(sarif or _sarif_document()), encoding="utf-8", newline="\n"
    )
    return report


def _mock_checkout_sources(
    root: Path, monkeypatch: pytest.MonkeyPatch, source_sha: str
) -> None:
    monkeypatch.setattr(collector, "_source_sha", lambda repo: source_sha)
    monkeypatch.setattr(
        collector,
        "_source_bytes_at_commit",
        lambda repo, commit, relative_path: (repo / relative_path).read_bytes(),
    )


def _command(
    root: Path,
    report: Path,
    receipt: Path,
    *,
    source_sha: str,
    scan_outcome: str = "success",
    run_id: str = "42",
    run_attempt: str = "2",
    artifact_name: str | None = None,
) -> list[str]:
    if artifact_name is None:
        artifact_name = f"zap-results-{run_id}-attempt-{run_attempt}"
    return [
        "--repo-root",
        str(root),
        "--expected-sha",
        source_sha,
        "--run-id",
        run_id,
        "--run-attempt",
        run_attempt,
        "--artifact-name",
        artifact_name,
        "--scan-outcome",
        scan_outcome,
        "--sarif",
        str(report),
        "--output",
        str(receipt),
    ]


def test_collector_binds_actual_report_bytes_to_source_and_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = _event_sha()
    report = _checkout(tmp_path)
    receipt_path = tmp_path / "provenance.json"
    _mock_checkout_sources(tmp_path, monkeypatch, source_sha)

    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                receipt_path,
                source_sha=source_sha,
            )
        )
        == 0
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    workflow_bytes = (tmp_path / ".github/workflows/dast.yml").read_bytes()
    rules_bytes = (tmp_path / ".zap/rules.tsv").read_bytes()
    report_bytes = report.read_bytes()
    assert receipt["workflow_run"] == {
        "id": "42",
        "attempt": "2",
        "artifact_name": "zap-results-42-attempt-2",
        "event_sha": source_sha,
        "checkout_sha": source_sha,
    }
    assert receipt["source"]["workflow_path"] == ".github/workflows/dast.yml"
    assert (
        receipt["source"]["workflow_sha256"]
        == hashlib.sha256(workflow_bytes).hexdigest()
    )
    assert receipt["source"]["zap_rules_path"] == ".zap/rules.tsv"
    assert (
        receipt["source"]["zap_rules_sha256"] == hashlib.sha256(rules_bytes).hexdigest()
    )
    assert receipt["report"]["path"] == "zap-results.sarif"
    assert receipt["report"]["sha256"] == hashlib.sha256(report_bytes).hexdigest()
    assert receipt["report"]["size_bytes"] == len(report_bytes)
    assert receipt["report"]["tool_name"] == "OWASP ZAP"
    assert receipt["report"]["version"] == "2.1.0"
    assert receipt["report"]["result_count"] == 1
    assert receipt["report"]["levels"]["warning"] == 1
    assert receipt["finding_threshold"] == "not_evaluated"
    assert "example-rule" not in receipt["report"]


def test_collector_rejects_checkout_from_another_event_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = _event_sha()
    report = _checkout(tmp_path)
    receipt_path = tmp_path / "provenance.json"
    other_sha = hashlib.sha256(b"other-zaproxy-test-source").hexdigest()[:40]
    monkeypatch.setattr(collector, "_source_sha", lambda root: other_sha)

    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                receipt_path,
                source_sha=source_sha,
            )
        )
        == 1
    )
    assert not receipt_path.exists()

    for mismatched_path in (collector.WORKFLOW_PATH, collector.RULES_PATH):
        monkeypatch.setattr(collector, "_source_sha", lambda root: source_sha)
        monkeypatch.setattr(
            collector,
            "_source_bytes_at_commit",
            lambda root, commit, relative_path, expected_path=mismatched_path: (
                b"modified source"
                if relative_path == expected_path
                else (root / relative_path).read_bytes()
            ),
        )
        modified_source_receipt = tmp_path / f"modified-{mismatched_path.name}.json"
        assert (
            collector.main(
                _command(
                    tmp_path,
                    report,
                    modified_source_receipt,
                    source_sha=source_sha,
                )
            )
            == 1
        )
        assert not modified_source_receipt.exists()


def test_collector_rejects_an_invalid_event_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _checkout(tmp_path)
    receipt_path = tmp_path / "provenance.json"

    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                receipt_path,
                source_sha="not-a-full-event-sha",
            )
        )
        == 1
    )
    assert not receipt_path.exists()


@pytest.mark.parametrize(
    ("run_id", "run_attempt"),
    [("0", "2"), ("42", "0"), ("+42", "2"), ("42", "02")],
)
def test_collector_rejects_invalid_workflow_run_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_id: str,
    run_attempt: str,
) -> None:
    source_sha = _event_sha()
    report = _checkout(tmp_path)
    receipt_path = tmp_path / "provenance.json"
    _mock_checkout_sources(tmp_path, monkeypatch, source_sha)

    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                receipt_path,
                source_sha=source_sha,
                run_id=run_id,
                run_attempt=run_attempt,
            )
        )
        == 1
    )
    assert not receipt_path.exists()


def test_collector_rejects_a_failed_scan_even_if_a_report_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = _event_sha()
    report = _checkout(tmp_path)
    receipt_path = tmp_path / "provenance.json"
    monkeypatch.setattr(collector, "_source_sha", lambda root: source_sha)

    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                receipt_path,
                source_sha=source_sha,
                scan_outcome="failure",
            )
        )
        == 1
    )
    assert not receipt_path.exists()


def test_collector_rejects_invalid_sarif_without_disclosing_report_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_sha = _event_sha()
    report = _checkout(tmp_path, sarif={"version": "1.0", "runs": []})
    receipt_path = tmp_path / "provenance.json"
    _mock_checkout_sources(tmp_path, monkeypatch, source_sha)

    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                receipt_path,
                source_sha=source_sha,
            )
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "SARIF" in captured.err
    assert "example-rule" not in captured.err
    assert not receipt_path.exists()


def test_collector_rejects_report_and_workflow_artifact_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = _event_sha()
    report = _checkout(tmp_path)
    mismatched_artifact_receipt = tmp_path / "wrong-artifact.json"
    _mock_checkout_sources(tmp_path, monkeypatch, source_sha)
    assert (
        collector.main(
            _command(
                tmp_path,
                report,
                mismatched_artifact_receipt,
                source_sha=source_sha,
                artifact_name="zap-results-41-attempt-2",
            )
        )
        == 1
    )
    assert not mismatched_artifact_receipt.exists()

    mismatched_report = report.with_name("unexpected.sarif")
    report.rename(mismatched_report)
    report_receipt = tmp_path / "wrong-report.json"

    assert (
        collector.main(
            _command(
                tmp_path,
                mismatched_report,
                report_receipt,
                source_sha=source_sha,
            )
        )
        == 1
    )
    assert not report_receipt.exists()

    external_directory = tmp_path / "external"
    external_directory.mkdir()
    external_report = external_directory / "zap-results.sarif"
    external_report.write_bytes(mismatched_report.read_bytes())
    external_receipt = tmp_path / "external-report.json"
    assert (
        collector.main(
            _command(
                tmp_path,
                external_report,
                external_receipt,
                source_sha=source_sha,
            )
        )
        == 1
    )
    assert not external_receipt.exists()


def test_current_zap_upload_requires_a_validated_report_producer() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github/workflows/dast.yml").read_text(encoding="utf-8")
    )
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    steps = workflow["jobs"]["zap"]["steps"]
    zap_job = workflow["jobs"]["zap"]
    assert zap_job["needs"] == "verify-trusted-ref"
    assert zap_job["permissions"] == {
        "contents": "read",
        "security-events": "write",
    }
    checkout = next(
        step for step in steps if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["sparse-checkout"].splitlines() == [
        ".github/workflows/dast.yml",
        ".zap",
        "scripts/quality",
    ]
    target_validation = next(
        step for step in steps if step.get("name") == "Validate ZAP target URL"
    )
    assert target_validation["env"]["TARGET_URL"] == (
        "${{ inputs.target_url || secrets.DAST_TARGET_URL }}"
    )
    assert (
        "python3 -m scripts.quality.dast_privacy validate-target"
        in target_validation["run"]
    )
    assert 'echo "::add-mask::$TARGET_URL"' in target_validation["run"]
    scan_index, scan = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "ZAP Full Scan"
    )
    check_index, check = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "Validate ZAP SARIF provenance"
    )
    upload_index, upload = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "Upload ZAP SARIF to GitHub Security"
    )

    assert scan["id"] == "zap_scan"
    assert scan["uses"] == (
        "zaproxy/action-full-scan@3c58388149901b9a03b7718852c5ba889646c27c"
    )
    assert scan["with"]["rules_file_name"] == ".zap/rules.tsv"
    assert scan["with"]["cmd_options"] == "-a -j -T 60"
    assert scan["with"]["allow_issue_writing"] is False
    assert check["id"] == "zap_sarif_provenance"
    assert check["if"] == "${{ always() }}"
    assert check["env"]["EVENT_SHA"] == "${{ github.sha }}"
    assert check["env"]["SCAN_OUTCOME"] == "${{ steps.zap_scan.outcome }}"
    assert check["env"]["RUN_ID"] == "${{ github.run_id }}"
    assert check["env"]["RUN_ATTEMPT"] == "${{ github.run_attempt }}"
    assert check["env"]["ARTIFACT_NAME"] == (
        "zap-results-${{ github.run_id }}-attempt-${{ github.run_attempt }}"
    )
    assert scan["with"]["artifact_name"] == check["env"]["ARTIFACT_NAME"]
    assert "python3 -m scripts.quality.zap_sarif_provenance" in check["run"]
    assert '--artifact-name "$ARTIFACT_NAME"' in check["run"]
    assert '--scan-outcome "$SCAN_OUTCOME"' in check["run"]
    assert scan_index < check_index < upload_index
    assert "steps.zap_sarif_provenance.outcome == 'success'" in upload["if"]
    assert "hashFiles('zap-results.sarif') != ''" in upload["if"]

    receipt_index, receipt_upload = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "Upload ZAP provenance receipt"
    )
    assert check_index < upload_index < receipt_index
    assert "steps.zap_sarif_provenance.outcome == 'success'" in receipt_upload["if"]
    assert "hashFiles('zap-sarif-provenance.json') != ''" in receipt_upload["if"]
    assert receipt_upload["with"]["path"] == "zap-sarif-provenance.json"
    assert receipt_upload["with"]["retention-days"] == 90

    nuclei_steps = workflow["jobs"]["nuclei"]["steps"]
    nuclei_gate = next(
        step
        for step in nuclei_steps
        if step.get("name") == "Fail on medium, high or critical Nuclei findings"
    )
    assert nuclei_gate["if"] == "${{ always() }}"
    assert "nuclei_findings_gate.py" in nuclei_gate["run"]
