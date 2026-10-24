"""Bounded, source-free metadata projection for failed Trivy image scans."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from scripts.quality import report_trivy_metadata


def test_trivy_diagnostic_emits_only_bounded_vulnerability_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vulnerability = {
        "ruleId": "CVE-2099-0001",
        "message": {
            "text": (
                "Package: libexample\nInstalled Version: 1.0.0\n"
                "Severity: HIGH\nFixed Version: 1.0.1\n"
                "Unlabeled metadata line\nMatch: never-emit-source-match"
            )
        },
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": (
                            "usr/bin/caddy\n::error::not-a-workflow-command" + "x" * 300
                        )
                    },
                    "region": {"snippet": {"text": "never-emit-source-snippet"}},
                }
            }
        ],
    }
    report = {
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [
                            {
                                "id": "CVE-2099-0001",
                                "name": "LanguageSpecificPackageVulnerability",
                                "help": {"text": "never-emit-rule-help"},
                            },
                            {"id": "secret-fixture", "name": "Secret"},
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": "secret-fixture",
                        "message": {"text": "Match: never-emit-secret-match"},
                    },
                    *[vulnerability for _ in range(105)],
                ],
            }
        ]
    }
    path = tmp_path / "trivy-fixture.sarif"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert report_trivy_metadata.main([str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 101
    assert "never-emit-" not in captured.out
    assert not any(line.startswith("::") for line in lines)
    metadata = json.loads(lines[0].removeprefix("TRIVY_VULNERABILITY "))
    assert metadata == {
        "rule_id": "CVE-2099-0001",
        "package": "libexample",
        "installed_version": "1.0.0",
        "severity": "HIGH",
        "fixed_version": "1.0.1",
        "location": vulnerability["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"][:256],
    }
    assert json.loads(lines[-1].removeprefix("TRIVY_SUMMARY ")) == {
        "results": 106,
        "vulnerabilities": 105,
        "printed": 100,
        "omitted_non_vulnerability": 1,
    }


def test_missing_optional_metadata_is_safe() -> None:
    lines = report_trivy_metadata.summarize_report(
        {
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "rules": [
                                {
                                    "id": "CVE-2099-0002",
                                    "name": "OsPackageVulnerability",
                                }
                            ]
                        }
                    },
                    "results": [{"ruleId": "CVE-2099-0002"}],
                }
            ]
        }
    )
    assert json.loads(lines[0].removeprefix("TRIVY_VULNERABILITY ")) == {
        "rule_id": "CVE-2099-0002"
    }


def test_unknown_rule_is_counted_but_never_printed() -> None:
    lines = report_trivy_metadata.summarize_report(
        {"runs": [{"results": [{"message": {"text": "never-print-unknown"}}]}]}
    )
    assert len(lines) == 1
    assert json.loads(lines[0].removeprefix("TRIVY_SUMMARY ")) == {
        "results": 1,
        "vulnerabilities": 0,
        "printed": 0,
        "omitted_non_vulnerability": 1,
    }


def test_every_emitted_field_is_bounded_and_non_string_values_are_empty() -> None:
    oversized = "x" * (report_trivy_metadata.MAX_FIELD + 1)
    labels = ("Package", "Installed Version", "Severity", "Fixed Version")
    lines = report_trivy_metadata.summarize_report(
        {
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "rules": [
                                {
                                    "id": oversized,
                                    "name": "OsPackageVulnerability",
                                },
                                {"id": 123, "name": "OsPackageVulnerability"},
                            ]
                        }
                    },
                    "results": [
                        {
                            "ruleId": oversized,
                            "message": {
                                "text": "\n".join(
                                    f"{label}: {oversized}" for label in labels
                                )
                            },
                        },
                        {
                            "ruleId": 123,
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": 123}
                                    }
                                }
                            ],
                        },
                    ],
                }
            ]
        }
    )
    first = json.loads(lines[0].removeprefix("TRIVY_VULNERABILITY "))
    assert set(first) == {
        "rule_id",
        "package",
        "installed_version",
        "severity",
        "fixed_version",
    }
    assert set(first.values()) == {"x" * report_trivy_metadata.MAX_FIELD}
    assert json.loads(lines[1].removeprefix("TRIVY_VULNERABILITY ")) == {
        "rule_id": "",
        "location": "",
    }


@pytest.mark.parametrize("raw", [b"{invalid-sarif", b"\xff", b"[]", b"null"])
def test_invalid_reports_fail_without_printing_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], raw: bytes
) -> None:
    path = tmp_path / "invalid.sarif"
    path.write_bytes(raw)
    with pytest.raises(SystemExit, match="^Invalid SARIF report$"):
        report_trivy_metadata.main([str(path)])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_oversized_reports_fail_without_printing_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "oversized.sarif"
    path.write_bytes(b" " * (report_trivy_metadata.MAX_BYTES + 1))
    with pytest.raises(
        SystemExit, match="^SARIF report exceeds diagnostic size limit$"
    ):
        report_trivy_metadata.main([str(path)])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_exact_size_limit_is_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "maximum.sarif"
    path.write_bytes(b"{}" + b" " * (report_trivy_metadata.MAX_BYTES - 2))
    assert report_trivy_metadata.main([str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out.removeprefix("TRIVY_SUMMARY ")) == {
        "results": 0,
        "vulnerabilities": 0,
        "printed": 0,
        "omitted_non_vulnerability": 0,
    }


def test_unreadable_report_fails_without_exposing_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="^Unable to read SARIF report$"):
        report_trivy_metadata.main([str(tmp_path / "missing.sarif")])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_cli_requires_a_report_path(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        report_trivy_metadata.main([])
    assert error.value.code == 2
    assert "sarif_path" in capsys.readouterr().err


def test_script_entrypoint_uses_cli_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "empty.sarif"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["report_trivy_metadata.py", str(path)])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(report_trivy_metadata.__file__, run_name="__main__")
    assert error.value.code == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("TRIVY_SUMMARY ")
