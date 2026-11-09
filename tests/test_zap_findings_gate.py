"""Fail-closed tests for the ZAP findings gate (AUD-381)."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

import pytest

from scripts.quality import zap_findings_gate as gate

MARKER = "zapmarker-7c41d9"


def _alert(riskcode: str, plugin: str = "10020") -> dict[str, object]:
    """Synthetic ZAP alert; every free-text field carries the marker."""

    return {
        "pluginid": plugin,
        "alertRef": f"{plugin}-1",
        "alert": f"Synthetic alert {MARKER}",
        "name": f"Synthetic alert {MARKER}",
        "riskcode": riskcode,
        "riskdesc": "Synthetic",
        "confidence": "2",
        "desc": f"<p>{MARKER}</p>",
        "solution": MARKER,
        "instances": [
            {
                "uri": f"https://{MARKER}.invalid/path",
                "method": "GET",
                "param": MARKER,
                "attack": MARKER,
                "evidence": MARKER,
            }
        ],
        "count": "1",
    }


def _report(*alerts: dict[str, object], sites: object | None = None) -> str:
    """Native ZAP JSON shape: a ``site`` list whose sites hold ``alerts``."""

    if sites is None:
        sites = [{"@name": f"https://{MARKER}.invalid", "alerts": list(alerts)}]
    return json.dumps({"@programName": "ZAP", "site": sites}, indent=2)


def _run(tmp_path: Path, report: str | None, summary: bool = False) -> tuple[int, str]:
    report_path = tmp_path / "report_json.json"
    if report is not None:
        report_path.write_text(report, encoding="utf-8", newline="\n")
    summary_path = tmp_path / "summary.md" if summary else None
    code = gate.run_gate(report_path, summary_path)
    return code, summary_path.read_text(encoding="utf-8") if summary_path else ""


@pytest.mark.parametrize(
    ("riskcode", "expected"),
    [("0", 0), ("1", 0), ("2", 1), ("3", 1)],
)
def test_each_risk_level_gates_at_medium_and_above(
    tmp_path: Path, riskcode: str, expected: int
) -> None:
    code, _ = _run(tmp_path, _report(_alert(riskcode)))

    assert code == expected


def test_medium_alert_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _run(tmp_path, _report(_alert("2", plugin="40012")))

    assert code == 1
    assert "ZAP reported 1 medium or high alert(s); rule ids: 40012." in (
        capsys.readouterr().err
    )


def test_high_alert_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _run(tmp_path, _report(_alert("3", plugin="40018")))

    assert code == 1
    assert "rule ids: 40018." in capsys.readouterr().err


@pytest.mark.parametrize("riskcode", ["0", "1"])
def test_informational_and_low_alerts_pass_and_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], riskcode: str
) -> None:
    code, summary = _run(tmp_path, _report(_alert(riskcode)), summary=True)

    assert code == 0
    assert "ZAP reported no medium or high alerts." in capsys.readouterr().out
    assert f"| {gate.RISK_NAMES[int(riskcode)]} | 1 | no |" in summary


def test_summary_marks_which_risks_block_the_job(tmp_path: Path) -> None:
    _, summary = _run(
        tmp_path, _report(_alert("3"), _alert("2"), _alert("1")), summary=True
    )

    assert "### ZAP DAST findings" in summary
    assert "| high | 1 | yes |" in summary
    assert "| medium | 1 | yes |" in summary
    assert "| low | 1 | no |" in summary
    assert "| informational | 0 | no |" in summary


def test_counts_are_per_alert_across_all_sites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sites = [
        {"alerts": [_alert("2"), _alert("1")]},
        {"alerts": [_alert("3", plugin="40018"), _alert("0")]},
    ]
    code, summary = _run(tmp_path, _report(sites=sites), summary=True)

    assert code == 1
    assert "ZAP reported 2 medium or high alert(s)" in capsys.readouterr().err
    assert "| high | 1 | yes |" in summary
    assert "| medium | 1 | yes |" in summary


def test_empty_site_list_with_valid_shape_passes(tmp_path: Path) -> None:
    code, _ = _run(tmp_path, _report(sites=[]))

    assert code == 0


def test_site_with_empty_alert_list_passes(tmp_path: Path) -> None:
    code, _ = _run(tmp_path, _report(sites=[{"alerts": []}]))

    assert code == 0


@pytest.mark.parametrize(
    "report",
    [
        pytest.param("", id="zero-byte"),
        pytest.param(" \n\t", id="whitespace-only"),
        pytest.param("{", id="truncated-object"),
        pytest.param('{"site": []}\n{"site": []}', id="two-documents"),
        pytest.param("[]", id="array-root"),
        pytest.param("null", id="null-root"),
        pytest.param("true", id="boolean-root"),
        pytest.param('"site"', id="string-root"),
        pytest.param("{}", id="missing-site-list"),
        pytest.param('{"site": null}', id="null-site-list"),
        pytest.param('{"site": {}}', id="object-site-list"),
        pytest.param('{"site": "https://x"}', id="string-site-list"),
        pytest.param('{"site": [null]}', id="null-site"),
        pytest.param('{"site": ["x"]}', id="string-site"),
        pytest.param('{"site": [{}]}', id="site-without-alerts-list"),
        pytest.param('{"site": [{"alerts": null}]}', id="null-alert-list"),
        pytest.param('{"site": [{"alerts": {}}]}', id="object-alert-list"),
        pytest.param('{"site": [{"alerts": [null]}]}', id="null-alert"),
        pytest.param('{"site": [{"alerts": ["x"]}]}', id="string-alert"),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "10020"}]}]}',
            id="alert-missing-riskcode",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"riskcode": "2"}]}]}',
            id="alert-missing-pluginid",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "10020", "riskcode": "4"}]}]}',
            id="unsupported-riskcode",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "10020", "riskcode": 2}]}]}',
            id="numeric-riskcode",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "10020", "riskcode": true}]}]}',
            id="boolean-riskcode",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "10020", "riskcode": "high"}]}]}',
            id="named-riskcode",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "abc", "riskcode": "0"}]}]}',
            id="non-numeric-pluginid",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": "12345678901", "riskcode": "0"}]}]}',
            id="overlong-pluginid",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"pluginid": 10020, "riskcode": "0"}]}]}',
            id="numeric-pluginid",
        ),
        pytest.param(
            '{"site": [], "site": []}',
            id="duplicate-site-key",
        ),
        pytest.param(
            '{"site": [{"alerts": [{"riskcode": "0", "riskcode": "3", "pluginid": "1"}]}]}',
            id="duplicate-riskcode-key",
        ),
        pytest.param('{"site": [], "x": NaN}', id="non-json-nan"),
        pytest.param('{"site": [], "x": Infinity}', id="non-json-infinity"),
        pytest.param("\x00\x01", id="binary-garbage"),
        pytest.param("[" * 100000, id="deeply-nested"),
    ],
)
def test_malformed_or_unexpected_reports_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], report: str
) -> None:
    code, _ = _run(tmp_path, report)

    assert code == 1
    assert "Could not validate ZAP JSON report; the scan result is unknown." in (
        capsys.readouterr().err
    )


def test_invalid_utf8_report_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "report_json.json").write_bytes(b'{"site": [\xff]}')

    code = gate.run_gate(tmp_path / "report_json.json", None)

    assert code == 1
    assert "Could not validate ZAP JSON report" in capsys.readouterr().err


def test_missing_report_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(tmp_path, None)

    assert code == 1
    assert "ZAP produced no JSON report; the scan result is unknown." in (
        capsys.readouterr().err
    )


def test_directory_at_report_path_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "report_json.json").mkdir()

    code = gate.run_gate(tmp_path / "report_json.json", None)

    assert code == 1
    assert "ZAP JSON report is not a regular file" in capsys.readouterr().err


def test_symlinked_report_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "real-report.json"
    target.write_text(_report(), encoding="utf-8")
    link = tmp_path / "report_json.json"
    os.symlink(target, link)

    code = gate.run_gate(link, None)

    assert code == 1
    assert "ZAP JSON report is not a regular file" in capsys.readouterr().err


def test_dangling_symlink_report_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    link = tmp_path / "report_json.json"
    os.symlink(tmp_path / "absent.json", link)

    code = gate.run_gate(link, None)

    assert code == 1
    assert "ZAP JSON report is not a regular file" in capsys.readouterr().err


def test_oversized_report_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "MAX_REPORT_BYTES", 64)

    code, _ = _run(tmp_path, _report(_alert("0")))

    assert code == 1
    assert "ZAP JSON report exceeds the size bound" in capsys.readouterr().err


def test_report_at_the_size_bound_is_still_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(sites=[])
    monkeypatch.setattr(gate, "MAX_REPORT_BYTES", len(report.encode("utf-8")))

    code, _ = _run(tmp_path, report)

    assert code == 0


def test_no_report_value_is_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """URLs, parameters, evidence and free text never reach stdout or stderr."""

    failing_report = _report(_alert("2", plugin="40012"), _alert("0"))
    summary_path = tmp_path / "summary.md"

    code = gate.run_gate(_write(tmp_path, failing_report), summary_path)
    captured = capsys.readouterr()

    assert code == 1
    assert MARKER not in captured.out
    assert MARKER not in captured.err
    assert MARKER not in summary_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "report",
    [
        pytest.param(_report(_alert("0")), id="clean"),
        pytest.param(_report(_alert("1")), id="low"),
        pytest.param(_report(_alert("3")), id="high"),
        pytest.param(
            '{"site": [{"alerts": [{"riskcode": "9"}], "x": "' + MARKER + '"}]}',
            id="malformed",
        ),
        pytest.param('{"site": "' + MARKER + '"', id="truncated"),
        pytest.param("[" + json.dumps(MARKER) + "]", id="array-root"),
    ],
)
def test_marker_never_reaches_stdout_or_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], report: str
) -> None:
    gate.run_gate(_write(tmp_path, report), None)
    captured = capsys.readouterr()

    assert MARKER not in captured.out
    assert MARKER not in captured.err


def test_oversized_report_does_not_print_its_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "MAX_REPORT_BYTES", 64)

    gate.run_gate(_write(tmp_path, _report(_alert("3"))), None)
    captured = capsys.readouterr()

    assert MARKER not in captured.out + captured.err


def _write(tmp_path: Path, report: str) -> Path:
    path = tmp_path / "report_json.json"
    path.write_text(report, encoding="utf-8", newline="\n")
    return path


def test_main_reads_the_report_and_appends_the_summary(tmp_path: Path) -> None:
    report = tmp_path / "report_json.json"
    report.write_text(_report(_alert("1")), encoding="utf-8", newline="\n")
    summary = tmp_path / "step-summary.md"

    code = gate.main([str(report), "--summary-file", str(summary)])

    assert code == 0
    assert "| low | 1 | no |" in summary.read_text(encoding="utf-8")


def test_main_rejects_missing_arguments() -> None:
    with pytest.raises(SystemExit):
        gate.main([])


def test_script_entry_point_exits_with_the_gate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the file as a script reaches the same exit status as main()."""

    report = tmp_path / "report_json.json"
    report.write_text(_report(_alert("2")), encoding="utf-8", newline="\n")
    script = Path(gate.__file__).resolve()
    monkeypatch.setattr(sys, "argv", [str(script), str(report)])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(script), run_name="__main__")

    assert raised.value.code == 1
