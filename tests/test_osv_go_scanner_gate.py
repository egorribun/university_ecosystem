"""Contract tests for the pull-request OSV Go disposition gate (AUD-483).

Each result must be an exact, unexpired owner disposition. The tests build
synthetic osv-scanner SARIF documents and run the real validator, then check
that the pull-request workflow runs it fail-closed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.quality.validate_osv_go_results import OsvResultError, validate

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SBOM = REPOSITORY_ROOT / ".github" / "workflows" / "sbom.yml"
TODAY = date(2026, 11, 4)


def _result(
    message: str,
    uri: str = "file:///C:/repo/services/caddy/go.mod",
) -> dict[str, Any]:
    return {
        "ruleId": "CVE-2026-116587",
        "message": {"text": message},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
    }


def _report(*results: dict[str, Any]) -> dict[str, Any]:
    return {"version": "2.1.0", "runs": [{"results": list(results)}]}


CADDY_GOJOSE = (
    "Package 'github.com/go-jose/go-jose/v3@3.0.5' is vulnerable to "
    "'CVE-2026-116587' (also known as 'GHSA-mgcc-cww5-fp2q')."
)


def test_owner_excepted_go_jose_finding_is_accepted() -> None:
    accepted = validate(_report(_result(CADDY_GOJOSE)), 1, TODAY)

    assert accepted == ["GHSA-mgcc-cww5-fp2q services/caddy/go.mod"]


def test_finding_without_a_ghsa_alias_is_rejected() -> None:
    message = "Package 'golang.org/x/crypto@0.57.0' is vulnerable to 'GO-2026-5932'."
    with pytest.raises(OsvResultError, match="no GHSA alias"):
        validate(
            _report(_result(message, "file:///C:/repo/services/gateway/go.mod")),
            1,
            TODAY,
        )


def test_unrecorded_module_version_or_manifest_is_rejected() -> None:
    other_version = CADDY_GOJOSE.replace("3.0.5", "3.0.6")
    with pytest.raises(OsvResultError, match="unexcepted finding"):
        validate(_report(_result(other_version)), 1, TODAY)
    other_manifest = _result(CADDY_GOJOSE, "file:///C:/repo/services/gateway/go.mod")
    with pytest.raises(OsvResultError, match="unexcepted finding"):
        validate(_report(other_manifest), 1, TODAY)


def test_stdlib_result_is_rejected() -> None:
    message = (
        "Package 'stdlib@1.26.4' is vulnerable to 'CVE-2026-00001' "
        "(also known as 'GHSA-aaaa-bbbb-cccc')."
    )
    with pytest.raises(OsvResultError, match="unexcepted finding"):
        validate(
            _report(_result(message, "file:///C:/repo/services/gateway/go.mod")),
            1,
            TODAY,
        )


def test_expired_disposition_is_rejected() -> None:
    with pytest.raises(OsvResultError, match="expired"):
        validate(_report(_result(CADDY_GOJOSE)), 1, date(2027, 1, 11))


def test_disposition_expires_on_its_recorded_date() -> None:
    assert validate(_report(_result(CADDY_GOJOSE)), 1, date(2027, 1, 9))
    with pytest.raises(OsvResultError, match="expired"):
        validate(_report(_result(CADDY_GOJOSE)), 1, date(2027, 1, 10))


def test_scanner_operational_failure_is_rejected() -> None:
    with pytest.raises(OsvResultError, match="operationally"):
        validate(_report(_result(CADDY_GOJOSE)), 2, TODAY)


def test_exit_status_must_agree_with_the_findings() -> None:
    with pytest.raises(OsvResultError, match="exited 0"):
        validate(_report(_result(CADDY_GOJOSE)), 0, TODAY)
    with pytest.raises(OsvResultError, match="exited 1 without"):
        validate(_report(), 1, TODAY)


def test_clean_scan_is_accepted() -> None:
    assert validate(_report(), 0, TODAY) == []


def test_pull_request_inventory_runs_the_disposition_gate_fail_closed() -> None:
    job = yaml.safe_load(SBOM.read_text(encoding="utf-8"))["jobs"]["vuln-gate-pr"]
    steps = job["steps"]
    names = [step.get("name", "") for step in steps]
    gate = steps[names.index("Gate OSV Go results by exact disposition (pull request)")]

    assert "continue-on-error" not in gate
    assert gate["env"] == {
        "SCANNER_STATUS": "${{ steps.osv_scan.outputs.scanner_status }}"
    }
    assert "scripts.quality.validate_osv_go_results" in gate["run"]
    assert "--sarif go-vuln.sarif" in gate["run"]
    assert "set -euo pipefail" in gate["run"]
