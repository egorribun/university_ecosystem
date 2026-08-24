from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / "quality" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_certification_is_content_addressed_and_hmac_signed(tmp_path: Path) -> None:
    certification = _load_script("generate_certification")
    contract = tmp_path / "contract.json"
    report = tmp_path / "coverage.json"
    contract.write_text('{"exclusions": [], "quarantines": []}\n', encoding="utf-8")
    report.write_text('{"covered": 10}\n', encoding="utf-8")

    record = certification.build_record(
        commit_sha="a" * 40,
        contract_path=contract,
        report_paths=[report],
        check_results={"quality": "success"},
        known_limitations=["browser promotion is tracked separately"],
        signing_key=b"test-key",
        generated_at="2026-07-22T00:00:00Z",
    )

    assert (
        record["record_sha256"]
        == certification.hashlib.sha256(
            certification._canonical(
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"record_sha256", "hmac_sha256"}
                }
            )
        ).hexdigest()
    )
    assert len(record["hmac_sha256"]) == 64
    assert record["report_hashes"][report.as_posix()] == certification._sha256(report)


def test_dashboard_surfaces_missing_evidence_and_expiry(tmp_path: Path) -> None:
    dashboard = _load_script("generate_dashboard")
    snapshot = {
        "generated_at": "2026-07-22T00:00:00Z",
        "commit_sha": "b" * 40,
        "components": {
            "python": {"metrics": {"lines": {"percent": 99.0}}},
            "frontend": {"metrics": {"lines": {"percent": None}}},
            "go-gateway": {"metrics": {"statements": {"percent": 99.0}}},
            "go-ws-hub": {"metrics": {"statements": {"percent": None}}},
            "go-file-processor": {"metrics": {"statements": {"percent": 98.0}}},
            "go-shared": {"metrics": {"statements": {"percent": 100.0}}},
        },
    }
    output = dashboard.render_dashboard(
        [(Path("artifacts/quality/history/one.json"), snapshot)],
        {
            "policy": {"patch_coverage": 100, "viable_mutant_score": 100},
            "exclusions": [
                {"id": "ex-1", "owner": "@egorribun", "expires_on": "2026-07-21"}
            ],
            "quarantines": [],
        },
        today=dashboard.date(2026, 7, 22),
    )

    assert "99.00%" in output
    assert "—" in output
    assert "expired" in output
    assert "never interpreted as a passing score" in output


def test_certification_cli_hashes_every_file_in_report_directory(
    tmp_path: Path, monkeypatch
) -> None:
    certification = _load_script("generate_certification")
    contract = tmp_path / "contract.json"
    checks = tmp_path / "checks.json"
    reports = tmp_path / "reports"
    reports.mkdir()
    report = reports / "mutation.json"
    output = tmp_path / "certification.json"
    contract.write_text('{"exclusions": [], "quarantines": []}\n', encoding="utf-8")
    checks.write_text('{"ci-success": "success"}\n', encoding="utf-8")
    report.write_text('{"score": 1.0}\n', encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_certification.py",
            "--commit-sha",
            "c" * 40,
            "--contract",
            str(contract),
            "--checks",
            str(checks),
            "--report-dir",
            str(reports),
            "--output",
            str(output),
        ],
    )
    monkeypatch.delenv("QUALITY_CERTIFICATION_KEY", raising=False)

    assert certification.main() == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert report.as_posix() in record["report_hashes"]


def test_stabilization_window_requires_every_calendar_day() -> None:
    stabilization = _load_script("check_stabilization_window")
    as_of = date(2026, 8, 8)
    runs = [
        {
            "conclusion": "success",
            "head_branch": "main",
            "completed_at": f"{as_of - timedelta(days=offset):%Y-%m-%d}T01:30:00Z",
        }
        for offset in range(30)
    ]

    result = stabilization.evaluate_window(runs, days=30, as_of=as_of, branch="main")

    assert result["eligible"] is True
    assert result["missing_dates"] == []


def test_stabilization_window_rejects_failed_or_stale_runs() -> None:
    stabilization = _load_script("check_stabilization_window")
    as_of = date(2026, 8, 8)
    runs = [
        {
            "conclusion": "success",
            "head_branch": "main",
            "completed_at": f"{as_of - timedelta(days=offset):%Y-%m-%d}T01:30:00Z",
        }
        for offset in range(1, 30)
    ]
    runs.append(
        {
            "conclusion": "failure",
            "head_branch": "main",
            "completed_at": f"{as_of:%Y-%m-%d}T01:30:00Z",
        }
    )

    result = stabilization.evaluate_window(runs, days=30, as_of=as_of, branch="main")

    assert result["eligible"] is False
    assert result["missing_dates"] == [as_of.isoformat()]
    assert "latest successful run" in result["reason"]
