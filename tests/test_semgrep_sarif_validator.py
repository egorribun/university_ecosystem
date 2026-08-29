"""Fail-closed tests for the Semgrep SARIF suppression ledger."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.quality import validate_semgrep_sarif as validator

_POLICY = {
    "version": 1,
    "entries": [
        {
            "rule_id": "rule.dynamic",
            "path": "scripts/example.py",
            "start_line": 10,
            "end_line": 10,
            "owner": "security@university.example",
            "expires": "2099-12-31",
            "reason": "The URL is constructed from a fixed host and allowlisted path.",
        }
    ],
}


def _result(
    *,
    rule_id: str = "rule.dynamic",
    path: str = "scripts/example.py",
    start_line: int = 10,
    end_line: int = 10,
    suppressed: bool = True,
) -> dict[str, object]:
    result: dict[str, object] = {
        "ruleId": rule_id,
        "level": "warning",
        "message": {"text": "finding"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": path, "uriBaseId": "%SRCROOT%"},
                    "region": {"startLine": start_line, "endLine": end_line},
                }
            }
        ],
    }
    if suppressed:
        result["suppressions"] = [{"kind": "inSource"}]
    return result


def _report(*results: dict[str, object], successful: bool = True) -> dict[str, object]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "invocations": [{"executionSuccessful": successful}],
                "results": list(results),
            }
        ],
    }


def _write_inputs(
    tmp_path: Path, report: dict[str, object], policy: object = _POLICY
) -> tuple[Path, Path]:
    report_path = tmp_path / "semgrep.sarif"
    policy_path = tmp_path / "semgrep-policy.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return report_path, policy_path


def test_approved_suppression_is_valid_even_when_semgrep_returns_findings(
    tmp_path: Path,
) -> None:
    report, policy = _write_inputs(tmp_path, _report(_result()))

    validator.validate_report(report, policy, scanner_status=1)


def test_unapproved_result_is_rejected(tmp_path: Path) -> None:
    report, policy = _write_inputs(
        tmp_path, _report(_result(path="scripts/other.py", suppressed=False))
    )

    with pytest.raises(validator.ValidationError, match="not covered"):
        validator.validate_report(report, policy, scanner_status=0)


def test_unapproved_in_source_suppression_is_rejected(tmp_path: Path) -> None:
    report, policy = _write_inputs(
        tmp_path, _report(_result(rule_id="rule.other", suppressed=True))
    )

    with pytest.raises(validator.ValidationError, match="not covered"):
        validator.validate_report(report, policy, scanner_status=0)


def test_stale_policy_entry_is_rejected(tmp_path: Path) -> None:
    report, policy = _write_inputs(tmp_path, _report(), _POLICY)

    with pytest.raises(validator.ValidationError, match="not observed"):
        validator.validate_report(report, policy, scanner_status=0)


@pytest.mark.parametrize(
    ("report", "status", "message"),
    [
        ({}, 0, "version"),
        ({"version": "2.1.0", "runs": []}, 0, "runs"),
        (_report(_result(), successful=False), 0, "execution"),
        (_report(_result()), 2, "scanner exit"),
    ],
)
def test_malformed_or_failed_scans_are_rejected(
    tmp_path: Path, report: dict[str, object], status: int, message: str
) -> None:
    report_path, policy_path = _write_inputs(tmp_path, report)

    with pytest.raises(validator.ValidationError, match=message):
        validator.validate_report(report_path, policy_path, scanner_status=status)


def test_policy_schema_rejects_duplicate_entries_and_expired_entries(
    tmp_path: Path,
) -> None:
    duplicate = {**_POLICY, "entries": [*_POLICY["entries"], _POLICY["entries"][0]]}
    report, policy = _write_inputs(tmp_path, _report(_result()), duplicate)

    with pytest.raises(validator.ValidationError, match="duplicate"):
        validator.validate_report(report, policy, scanner_status=0)

    expired = {
        **_POLICY,
        "entries": [{**_POLICY["entries"][0], "expires": "2000-01-01"}],
    }
    report, policy = _write_inputs(tmp_path, _report(_result()), expired)

    with pytest.raises(validator.ValidationError, match="expired"):
        validator.validate_report(report, policy, scanner_status=0)


def test_cli_main_reports_success_and_validation_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report, policy = _write_inputs(tmp_path, _report(_result()))

    assert (
        validator.main(
            ["--report", str(report), "--policy", str(policy), "--scanner-status", "0"]
        )
        == 0
    )
    assert "ledger are valid" in capsys.readouterr().out

    broken_report, broken_policy = _write_inputs(
        tmp_path, _report(_result(suppressed=False))
    )
    assert (
        validator.main(
            [
                "--report",
                str(broken_report),
                "--policy",
                str(broken_policy),
                "--scanner-status",
                "0",
            ]
        )
        == 1
    )
    assert "not covered" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        ({"version": 2, "entries": []}, "version"),
        ({"version": 1, "entries": []}, "non-empty"),
        ({"version": 1, "entries": ["bad"]}, "object"),
        ({"version": 1, "entries": [{"rule_id": ""}]}, "rule_id"),
        (
            {
                "version": 1,
                "entries": [{**_POLICY["entries"][0], "start_line": 0}],
            },
            "start_line",
        ),
        (
            {
                "version": 1,
                "entries": [{**_POLICY["entries"][0], "end_line": 1}],
            },
            "end_line",
        ),
        (
            {
                "version": 1,
                "entries": [{**_POLICY["entries"][0], "owner": ""}],
            },
            "owner",
        ),
        (
            {
                "version": 1,
                "entries": [{**_POLICY["entries"][0], "reason": ""}],
            },
            "reason",
        ),
        (
            {
                "version": 1,
                "entries": [{**_POLICY["entries"][0], "expires": "not-a-date"}],
            },
            "ISO date",
        ),
    ],
)
def test_policy_schema_rejects_invalid_entries(
    tmp_path: Path, policy: object, message: str
) -> None:
    report, policy_path = _write_inputs(tmp_path, _report(_result()), policy)

    with pytest.raises(validator.ValidationError, match=message):
        validator.validate_report(report, policy_path, scanner_status=0)


@pytest.mark.parametrize(
    "result",
    [
        {"ruleId": "rule.dynamic", "locations": []},
        {"ruleId": "rule.dynamic", "locations": ["bad"]},
        {"ruleId": "rule.dynamic", "locations": [{}]},
        {"ruleId": "rule.dynamic", "locations": [{"physicalLocation": {}}]},
        {
            "ruleId": "rule.dynamic",
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "scripts/example.py"},
                        "region": {"startLine": 0},
                    }
                }
            ],
        },
        {
            "ruleId": "rule.dynamic",
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "scripts/example.py"},
                        "region": {"startLine": 10, "endLine": 9},
                    }
                }
            ],
        },
    ],
)
def test_invalid_result_locations_are_rejected(
    tmp_path: Path, result: dict[str, object]
) -> None:
    report, policy = _write_inputs(tmp_path, _report(result))

    with pytest.raises(validator.ValidationError):
        validator.validate_report(report, policy, scanner_status=0)


def test_non_line_bound_or_malformed_suppressions_are_rejected(tmp_path: Path) -> None:
    result = _result()
    result["suppressions"] = [{"kind": "external"}]
    report, policy = _write_inputs(tmp_path, _report(result))

    with pytest.raises(validator.ValidationError, match="not covered"):
        validator.validate_report(report, policy, scanner_status=0)


@pytest.mark.parametrize(
    ("report", "message"),
    [
        (_report({"locations": []}), "no ruleId"),
        (
            _report(
                {
                    "ruleId": "rule.dynamic",
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": ""},
                                "region": {"startLine": 1},
                            }
                        }
                    ],
                }
            ),
            "no source path",
        ),
        (
            _report(
                {
                    "ruleId": "rule.dynamic",
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": "scripts/example.py"},
                                "region": {"startLine": 1},
                            }
                        }
                    ],
                }
            ),
            "not covered",
        ),
    ],
)
def test_missing_result_identity_is_rejected(
    tmp_path: Path, report: dict[str, object], message: str
) -> None:
    report_path, policy_path = _write_inputs(tmp_path, report)

    with pytest.raises(validator.ValidationError, match=message):
        validator.validate_report(report_path, policy_path, scanner_status=0)


def test_sarif_shape_errors_are_rejected(tmp_path: Path) -> None:
    report, policy = _write_inputs(tmp_path, _report(_result()))
    malformed_reports = [
        {"version": "2.1.0", "runs": ["bad"]},
        {"version": "2.1.0", "runs": [{"invocations": []}]},
        {
            "version": "2.1.0",
            "runs": [
                {"invocations": [{"executionSuccessful": True}], "results": "bad"}
            ],
        },
        {
            "version": "2.1.0",
            "runs": [
                {"invocations": [{"executionSuccessful": True}], "results": ["bad"]}
            ],
        },
    ]
    messages = ("run must be", "no invocation", "results must", "result must")
    for malformed, message in zip(malformed_reports, messages, strict=True):
        report.write_text(json.dumps(malformed), encoding="utf-8")
        with pytest.raises(validator.ValidationError, match=message):
            validator.validate_report(report, policy, scanner_status=0)


def test_json_input_errors_and_non_objects_are_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_POLICY), encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="unable to read"):
        validator.validate_report(missing, policy, scanner_status=0)

    report = tmp_path / "report.json"
    report.write_text("not-json", encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="unable to read"):
        validator.validate_report(report, policy, scanner_status=0)

    report.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="JSON object"):
        validator.validate_report(report, policy, scanner_status=0)
    report.write_text(json.dumps(_report(_result())), encoding="utf-8")
    policy.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(validator.ValidationError, match="JSON object"):
        validator.validate_report(report, policy, scanner_status=0)


def test_normalization_accepts_relative_uri_and_implicit_end_line(
    tmp_path: Path,
) -> None:
    result = _result()
    location = result["locations"][0]
    assert isinstance(location, dict)
    physical = location["physicalLocation"]
    assert isinstance(physical, dict)
    artifact = physical["artifactLocation"]
    assert isinstance(artifact, dict)
    artifact["uri"] = "./scripts/example.py"
    region = physical["region"]
    assert isinstance(region, dict)
    region.pop("endLine")
    policy = {**_POLICY, "entries": [{**_POLICY["entries"][0], "end_line": 10}]}
    report_path, policy_path = _write_inputs(tmp_path, _report(result), policy)

    validator.validate_report(report_path, policy_path, scanner_status=0)

    result["suppressions"] = "inSource"
    report, policy = _write_inputs(tmp_path, _report(result))
    with pytest.raises(validator.ValidationError, match="not covered"):
        validator.validate_report(report, policy, scanner_status=0)


def test_module_entrypoint_returns_success_for_valid_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, policy = _write_inputs(tmp_path, _report(_result()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_semgrep_sarif.py",
            "--report",
            str(report),
            "--policy",
            str(policy),
            "--scanner-status",
            "0",
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(Path(validator.__file__)), run_name="__main__")

    assert exit_info.value.code == 0
