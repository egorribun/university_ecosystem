"""Fail-closed tests for the Nuclei findings gate (AUD-381)."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.quality import nuclei_findings_gate as gate

_SEVERITIES = ("info", "low", "medium", "high", "critical", "unknown")


def _finding(severity: str) -> dict[str, object]:
    """Synthetic native finding; no host or URL is needed to exercise the gate."""

    return {
        "template-id": "synthetic-contract-fixture",
        "info": {
            "name": "Synthetic contract finding",
            "author": ["contract"],
            "tags": ["contract"],
            "severity": severity,
        },
        "type": "http",
        "matcher-status": True,
    }


def _array(*severities: str) -> str:
    """Native -json-export form: one JSON array, ``[]`` when nothing matched."""

    return json.dumps([_finding(severity) for severity in severities], indent=2)


def _jsonl(*severities: str) -> str:
    """JSON Lines form: one compact object per line, as ``-jsonl-export`` writes."""

    return "\n".join(json.dumps(_finding(severity)) for severity in severities)


def _run(tmp_path: Path, export: str | None, summary: bool = False) -> tuple[int, str]:
    export_path = tmp_path / "nuclei-results.json"
    if export is not None:
        export_path.write_text(export, encoding="utf-8", newline="\n")
    summary_path = tmp_path / "summary.md" if summary else None
    code = gate.run_gate(export_path, summary_path)
    return code, summary_path.read_text(encoding="utf-8") if summary_path else ""


def test_array_export_without_findings_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(tmp_path, "[]")

    assert code == 0
    assert "Nuclei reported no medium, high or critical findings." in (
        capsys.readouterr().out
    )


def test_array_export_file_is_parsed(tmp_path: Path) -> None:
    code, _ = _run(tmp_path, _array("info", "low"))

    assert code == 0


@pytest.mark.parametrize("severity", _SEVERITIES)
def test_each_severity_is_recognised_in_the_array_form(
    tmp_path: Path, severity: str
) -> None:
    code, _ = _run(tmp_path, _array(severity))

    expected = 1 if severity in gate.BLOCKING_SEVERITIES else 0
    assert code == expected


@pytest.mark.parametrize("severity", ["medium", "high", "critical"])
def test_medium_high_and_critical_findings_fail(tmp_path: Path, severity: str) -> None:
    code, _ = _run(tmp_path, _array(severity))

    assert code == 1


@pytest.mark.parametrize("severity", ["info", "low", "unknown"])
def test_info_low_and_unknown_findings_are_reported_without_failing(
    tmp_path: Path, severity: str
) -> None:
    code, summary = _run(tmp_path, _array(severity), summary=True)

    assert code == 0
    assert f"| {severity} | 1 | " in summary


def test_summary_marks_which_severities_block_the_job(tmp_path: Path) -> None:
    _, summary = _run(tmp_path, _array("medium", "low"), summary=True)

    assert "### Nuclei DAST findings" in summary
    assert "| medium | 1 | yes |" in summary
    assert "| low | 1 | no |" in summary


def test_missing_export_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(tmp_path, None)

    assert code == 1
    assert "Nuclei produced no JSON export; the scan result is unknown." in (
        capsys.readouterr().err
    )


def test_clean_export_does_not_require_a_sarif_file(tmp_path: Path) -> None:
    export = tmp_path / "nuclei-results.json"
    export.write_text("[]", encoding="utf-8")

    assert (
        gate.main([str(export), "--check-sarif", str(tmp_path / "missing.sarif")]) == 0
    )


@pytest.mark.parametrize("severity", ["info", "low", "medium", "high", "critical"])
def test_findings_require_a_sarif_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], severity: str
) -> None:
    export = tmp_path / "nuclei-results.json"
    export.write_text(_array(severity), encoding="utf-8")

    assert (
        gate.main([str(export), "--check-sarif", str(tmp_path / "missing.sarif")]) == 1
    )
    assert "Nuclei produced findings but no SARIF report" in capsys.readouterr().err


@pytest.mark.parametrize("export_text", [None, "", "[{}]", _jsonl("info")])
def test_sarif_presence_check_requires_a_valid_native_export(
    tmp_path: Path, export_text: str | None
) -> None:
    export = tmp_path / "nuclei-results.json"
    if export_text is not None:
        export.write_text(export_text, encoding="utf-8")
    sarif = tmp_path / "nuclei-results.sarif"
    sarif.write_text("some report", encoding="utf-8")

    assert gate.main([str(export), "--check-sarif", str(sarif)]) == 1


def test_sarif_presence_check_accepts_findings_with_an_existing_report(
    tmp_path: Path,
) -> None:
    export = tmp_path / "nuclei-results.json"
    export.write_text(_array("medium"), encoding="utf-8")
    sarif = tmp_path / "nuclei-results.sarif"
    sarif.write_text("some report", encoding="utf-8")

    assert gate.main([str(export), "--check-sarif", str(sarif)]) == 0
    assert sarif.read_text(encoding="utf-8") == "some report"


@pytest.mark.parametrize(
    "export",
    [
        pytest.param(_jsonl("info"), id="single-object"),
        pytest.param(_jsonl("info", "low"), id="json-lines"),
        pytest.param(
            '[{"info":{"severity":"high","severity":"info"}}]',
            id="duplicate-severity",
        ),
        pytest.param(
            '[{"info":{"severity":"high","\\u0073everity":"info"}}]',
            id="duplicate-severity-escaped-key",
        ),
        pytest.param(
            '[{"info":{"severity":"high"},"info":{"severity":"info"}}]',
            id="duplicate-info",
        ),
        pytest.param(
            '[{"info":{"severity":"info"},"other":NaN}]', id="non-json-number"
        ),
        pytest.param(
            '[{"info":{"severity":"info"},"other":Infinity}]',
            id="non-json-infinity",
        ),
        pytest.param(
            '[{"info":{"severity":"info"},"other":-Infinity}]',
            id="non-json-negative-infinity",
        ),
    ],
)
def test_unexpected_or_ambiguous_json_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], export: str
) -> None:
    code, _ = _run(tmp_path, export)

    assert code == 1
    assert "Could not validate Nuclei JSON export" in capsys.readouterr().err


@pytest.mark.parametrize(
    "export",
    [
        pytest.param("", id="zero-byte-export"),
        pytest.param(" \n\t", id="whitespace-only"),
        pytest.param("[", id="truncated-array"),
        pytest.param("[]\n[]", id="two-array-documents"),
        pytest.param("[] trailing", id="trailing-garbage"),
        pytest.param("{}\n{}", id="object-without-info"),
        pytest.param("null", id="null-root"),
        pytest.param("true", id="boolean-root"),
        pytest.param("1", id="number-root"),
        pytest.param('"finding"', id="string-root"),
        pytest.param('{"findings":[]}', id="object-root-without-info"),
        pytest.param('{"info":{"severity":"medium"}}\n[]', id="array-after-jsonl"),
        pytest.param("[null]", id="null-member"),
        pytest.param("[[]]", id="array-member"),
        pytest.param("[1]", id="number-member"),
        pytest.param("[true]", id="boolean-member"),
        pytest.param('["finding"]', id="string-member"),
        pytest.param("[{}]", id="missing-info"),
        pytest.param('[{"info":null}]', id="null-info"),
        pytest.param('[{"info":[]}]', id="array-info"),
        pytest.param('[{"info":{}}]', id="missing-severity"),
        pytest.param('[{"info":{"severity":null}}]', id="null-severity"),
        pytest.param('[{"info":{"severity":1}}]', id="numeric-severity"),
        pytest.param('[{"info":{"severity":true}}]', id="boolean-severity"),
        pytest.param('[{"info":{"severity":[]}}]', id="array-severity"),
        pytest.param('[{"info":{"severity":{}}}]', id="object-severity"),
        pytest.param('[{"info":{"severity":""}}]', id="empty-severity"),
        pytest.param('[{"info":{"severity":"HIGH"}}]', id="uppercase-severity"),
        pytest.param('[{"info":{"severity":" high "}}]', id="padded-severity"),
        pytest.param('[{"info":{"severity":"severe"}}]', id="unsupported-severity"),
        pytest.param('{"info":{"severity":"high"}}\n\n{}', id="blank-jsonl-line"),
        pytest.param('{"info":{"severity":"high"}}\n[]', id="jsonl-then-array"),
        pytest.param('{"info":{"severity":"high"}}\n"x"', id="jsonl-string-line"),
        pytest.param('{"info":{"severity":"high"}', id="truncated-jsonl-line"),
        pytest.param("\x00\x01", id="binary-garbage"),
    ],
)
def test_malformed_or_unrecognised_exports_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    export: str,
) -> None:
    code, _ = _run(tmp_path, export)

    assert code == 1
    assert "Could not validate Nuclei JSON export; the scan result is unknown." in (
        capsys.readouterr().err
    )


def test_invalid_utf8_export_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "nuclei-results.json").write_bytes(b"[\xff]")

    code = gate.run_gate(tmp_path / "nuclei-results.json", None)

    assert code == 1
    assert "Could not validate Nuclei JSON export" in capsys.readouterr().err


def test_one_malformed_member_blocks_the_whole_array(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A valid high finding must not be counted before a later member is checked."""

    export = json.dumps([_finding("high"), {}])
    code, _ = _run(tmp_path, export)

    assert code == 1
    assert "high or critical finding(s)" not in capsys.readouterr().err


def test_escaped_severity_is_decoded_as_its_json_value(tmp_path: Path) -> None:
    export = _array("high").replace('"high"', '"\\u0068igh"')

    code, _ = _run(tmp_path, export)

    assert code == 1


def test_array_findings_are_counted_per_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(tmp_path, _array("medium", "high", "critical", "low"))

    assert code == 1
    assert "Nuclei reported 3 medium, high or critical finding(s)." in (
        capsys.readouterr().err
    )


def test_minified_mixed_severity_array_has_the_same_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    findings = [_finding(severity) for severity in ("info", "medium", "high", "low")]
    export = json.dumps(findings, separators=(",", ":"))

    code, _ = _run(tmp_path, export)

    assert code == 1
    assert "Nuclei reported 2 medium, high or critical finding(s)." in (
        capsys.readouterr().err
    )


def test_export_path_that_is_a_directory_is_reported_as_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "nuclei-results.json"
    directory.mkdir()

    code = gate.run_gate(directory, None)

    assert code == 1
    assert "Nuclei produced no JSON export" in capsys.readouterr().err


def test_main_reads_the_export_and_appends_the_summary(tmp_path: Path) -> None:
    export = tmp_path / "nuclei-results.json"
    export.write_text(_array("info"), encoding="utf-8", newline="\n")
    summary = tmp_path / "step-summary.md"

    code = gate.main([str(export), "--summary-file", str(summary)])

    assert code == 0
    assert "| info | 1 | no |" in summary.read_text(encoding="utf-8")


def test_main_rejects_missing_arguments() -> None:
    with pytest.raises(SystemExit):
        gate.main([])


def test_script_entry_point_exits_with_the_gate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the file as a script reaches the same exit status as main()."""

    export = tmp_path / "nuclei-results.json"
    export.write_text(_array("info"), encoding="utf-8", newline="\n")
    script = Path(gate.__file__).resolve()
    monkeypatch.setattr(sys, "argv", [str(script), str(export)])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(script), run_name="__main__")

    assert raised.value.code == 0
