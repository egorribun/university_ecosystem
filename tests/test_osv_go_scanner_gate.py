"""Contract tests for the pull-request OSV Go disposition gate (AUD-483).

Each result must be an exact, unexpired owner disposition. The tests build
synthetic osv-scanner SARIF documents and run the real validator, then check
that the pull-request workflow runs it fail-closed.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.quality import validate_osv_go_results as gate_module
from scripts.quality.validate_osv_go_results import OsvResultError, validate

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SBOM = REPOSITORY_ROOT / ".github" / "workflows" / "sbom.yml"
TODAY = date(2026, 11, 4)


def _result(
    message: str,
    uri: str = "file:///C:/repo/services/caddy/go.mod",
) -> dict[str, Any]:
    return {
        "ruleId": message.split(" is vulnerable to '", 1)[1].split("'", 1)[0],
        "message": {"text": message},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
    }


def _report(*results: dict[str, Any]) -> dict[str, Any]:
    rules = {}
    for result in results:
        ids = re.findall(r"'([^']+)'", result["message"]["text"])[1:]
        rules[result["ruleId"]] = {"id": result["ruleId"], "deprecatedIds": ids}
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "osv-scanner",
                        "version": "2.6.0",
                        "rules": list(rules.values()),
                    }
                },
                "results": list(results),
            }
        ],
    }


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


# Exact emitted message from google/osv-scanner v2.6.0's checked-in snapshot:
# internal/output/__snapshots__/sarif_test.snap, TestPrintSARIFReport/#00.
# This is upstream evidence, not a captured report from the failed hosted run.
UPSTREAM_MULTI_ALIAS = (
    "Package 'github.com/gogo/protobuf@1.3.1' is vulnerable to "
    "'CVE-2021-3121' (also known as 'GO-2021-0053', 'GHSA-c3h9-896r-86jm')."
)


def test_actual_upstream_multi_alias_message_is_parsed_but_not_excepted() -> None:
    with pytest.raises(OsvResultError, match="unexcepted finding GHSA-c3h9-896r-86jm"):
        validate(_report(_result(UPSTREAM_MULTI_ALIAS)), 1, TODAY)


def test_independent_upstream_result_and_rule_preserve_identity() -> None:
    # The fixture projects fields from the upstream snapshot cited above,
    # preserving its original message, rule ordering, ruleIndex and aliases.
    report = json.loads(
        (REPOSITORY_ROOT / "tests/fixtures/osv-v2.6.0-multi-alias.json").read_text(
            encoding="utf-8"
        )
    )
    run = report["runs"][0]
    result = run["results"][0]
    match = gate_module.MESSAGE.fullmatch(result["message"]["text"])
    assert match is not None
    assert gate_module._ghsa_alias(run, result, match) == "GHSA-c3h9-896r-86jm"
    with pytest.raises(OsvResultError, match="outside services"):
        validate(report, 1, TODAY)
    # Changing only the fixture location exercises the exact disposition gate.
    # It does not turn this unapproved upstream identity into an approved one.
    result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] = (
        "file:///repo/services/caddy/go.mod"
    )
    with pytest.raises(OsvResultError, match="unexcepted finding GHSA-c3h9-896r-86jm"):
        validate(report, 1, TODAY)


@pytest.mark.parametrize(
    "advisory",
    [
        "'CVE-2026-116587' (also known as 'GO-2026-0001', 'GHSA-mgcc-cww5-fp2q')",
        "'CVE-2026-116587' (also known as 'GHSA-mgcc-cww5-fp2q', 'GO-2026-0001')",
        "'GHSA-mgcc-cww5-fp2q' (also known as 'GO-2026-0001')",
        "'GHSA-mgcc-cww5-fp2q'",
    ],
)
def test_official_alias_grammar_preserves_exact_owner_scope(advisory: str) -> None:
    message = (
        "Package 'github.com/go-jose/go-jose/v3@3.0.5' is vulnerable to "
        + advisory
        + "."
    )
    assert validate(_report(_result(message)), 1, TODAY) == [
        "GHSA-mgcc-cww5-fp2q services/caddy/go.mod"
    ]


@pytest.mark.parametrize(
    "suffix",
    [
        "'GHSA-mgcc-cww5-fp2q', 'GHSA-4w3g-jfj2-cw2q'",
        "'GHSA-mgcc-cww5-fp2q', 'GHSA-aaaa-bbbb-cccc'",
        "'GHSA-mgcc-cww5-fp2q', 'GHSA-mgcc-cww5-fp2q'",
        "'GHSA-mgcc-cww5-fp2q', 'CVE-2026-116587'",
        "'GHSA-mgcc-cww5-fp2q', 'bogus'",
        "'GHSA-mgcc-cww5-fp2q', ''",
        "'GHSA-mgcc-cww5-fp2q', 'GO-2026-0001' trailing",
    ],
)
def test_ambiguous_duplicate_or_malformed_aliases_cannot_borrow_approval(
    suffix: str,
) -> None:
    message = (
        "Package 'github.com/go-jose/go-jose/v3@3.0.5' is vulnerable to 'CVE-2026-116587' (also known as "
        + suffix
        + ")."
    )
    with pytest.raises(OsvResultError):
        validate(_report(_result(message)), 1, TODAY)


@pytest.mark.parametrize(
    "tail",
    ["\n", "\r", " ignored", "\nPackage 'other@1' is vulnerable to 'GO-2026-0001'."],
)
def test_message_must_be_consumed_completely(tail: str) -> None:
    with pytest.raises(OsvResultError):
        validate(_report(_result(CADDY_GOJOSE + tail)), 1, TODAY)


@pytest.mark.parametrize(
    "mutation",
    [
        "rule_id",
        "rule_missing",
        "duplicate_rule",
        "alias_missing",
        "alias_extra",
        "alias_string",
        "rule_index",
        "rule_index_boolean",
        "missing_tool",
    ],
)
def test_message_must_match_exact_structured_rule(mutation: str) -> None:
    report = _report(_result(CADDY_GOJOSE))
    run = report["runs"][0]
    rule = run["tool"]["driver"]["rules"][0]
    if mutation == "rule_id":
        run["results"][0]["ruleId"] = "CVE-2026-00001"
    elif mutation == "rule_missing":
        run["tool"]["driver"]["rules"] = []
    elif mutation == "duplicate_rule":
        run["tool"]["driver"]["rules"].append(dict(rule))
    elif mutation == "alias_missing":
        rule["deprecatedIds"] = [rule["id"]]
    elif mutation == "alias_extra":
        rule["deprecatedIds"].append("GO-2026-0001")
    elif mutation == "alias_string":
        rule["deprecatedIds"] = "GHSA-mgcc-cww5-fp2q"
    elif mutation == "rule_index":
        run["results"][0]["ruleIndex"] = 1
    elif mutation == "rule_index_boolean":
        run["results"][0]["ruleIndex"] = False
    else:
        del run["tool"]
    with pytest.raises(OsvResultError):
        validate(report, 1, TODAY)


@pytest.mark.parametrize(
    "uri",
    [
        "file:///repo/not-services/caddy/go.mod",
        "file:///repo/services/caddy/go.mod/../go.mod",
        "file:///repo/services/gateway/go.mod",
        "file:///repo/services/caddy/go.mod?other",
    ],
)
def test_alias_parsing_cannot_expand_manifest_scope(uri: str) -> None:
    with pytest.raises(OsvResultError):
        validate(_report(_result(CADDY_GOJOSE, uri)), 1, TODAY)


def test_later_unapproved_finding_still_blocks() -> None:
    with pytest.raises(OsvResultError):
        validate(
            _report(_result(CADDY_GOJOSE), _result(UPSTREAM_MULTI_ALIAS)), 1, TODAY
        )


@pytest.mark.parametrize(
    "message, status, expected",
    [
        (
            CADDY_GOJOSE.replace(
                "'GHSA-mgcc-cww5-fp2q'", "'GO-2026-0001', 'GHSA-mgcc-cww5-fp2q'"
            ),
            1,
            0,
        ),
        (UPSTREAM_MULTI_ALIAS, 1, 1),
        ("Package 'golang.org/x/crypto@0.57.0' is vulnerable to 'GO-2026-5932'.", 1, 1),
        (CADDY_GOJOSE, 0, 1),
        (CADDY_GOJOSE, 2, 1),
    ],
)
def test_main_gate_preserves_fail_closed_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    status: int,
    expected: int,
) -> None:
    path = tmp_path / "report.sarif"
    path.write_text(json.dumps(_report(_result(message))), encoding="utf-8")
    monkeypatch.setattr(gate_module, "_today", lambda: TODAY)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scripts.quality.validate_osv_go_results",
            "--sarif",
            str(path),
            "--scanner-status",
            str(status),
        ],
    )
    assert gate_module.main() == expected


def test_actual_rule_index_is_accepted() -> None:
    report = _report(_result(CADDY_GOJOSE))
    report["runs"][0]["results"][0]["ruleIndex"] = 0
    assert validate(report, 1, TODAY) == ["GHSA-mgcc-cww5-fp2q services/caddy/go.mod"]


@pytest.mark.parametrize("mutation", ["version", "runs", "locations", "outside"])
def test_malformed_report_or_scope_remains_blocking(mutation: str) -> None:
    report = _report(_result(CADDY_GOJOSE))
    if mutation == "version":
        report["version"] = "2.0.0"
    elif mutation == "runs":
        report["runs"] = []
    elif mutation == "locations":
        report["runs"][0]["results"][0]["locations"] = []
    else:
        report["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"] = "file:///repo/go.mod"
    with pytest.raises(OsvResultError):
        validate(report, 1, TODAY)


@pytest.mark.parametrize("raw", [b"", b"not-json"])
def test_main_rejects_empty_or_invalid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    path = tmp_path / "bad.sarif"
    path.write_bytes(raw)
    monkeypatch.setattr(
        sys, "argv", ["gate", "--sarif", str(path), "--scanner-status", "1"]
    )
    assert gate_module.main() == 1
