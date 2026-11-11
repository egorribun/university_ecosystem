from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
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


def test_current_zap_upload_requires_verified_public_projection() -> None:
    """The legacy collector is no longer evidence that an action produced SARIF."""
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github/workflows/dast.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["zap"]["steps"]
    assert not any(
        "zaproxy/action-full-scan@" in step.get("uses", "") for step in steps
    )
    assert steps[1]["env"] == {"DAST_SECRET_TARGET": "${{ secrets.DAST_TARGET_URL }}"}
    assert "scripts.quality.zap_workflow prepare" in steps[1]["run"]
    assert "scripts.quality.zap_workflow verify" in steps[2]["run"]
    assert steps[2]["id"] == "zap_verify"
    for step in steps[3:5]:
        assert "steps.zap_prepare.outcome == 'success'" in step["if"]
        assert "steps.zap_verify.outcome == 'success'" in step["if"]
    assert steps[3]["with"]["sarif_file"] == "zap-public/zap-results.sarif"
    assert steps[4]["with"]["path"].splitlines() == [
        "zap-public/zap-results.sarif",
        "zap-public/zap-evidence.txt",
        "zap-public/zap-sarif-provenance.json",
    ]
    assert "scripts.quality.zap_workflow gate" in steps[-1]["run"]
    assert steps[-1]["if"] == "${{ always() }}"
