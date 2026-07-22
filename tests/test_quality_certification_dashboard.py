from __future__ import annotations

import importlib.util
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
