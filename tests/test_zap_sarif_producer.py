"""Exercise the producer CLI, including its publication boundary."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality import zap_sarif_producer

ROOT = Path(__file__).resolve().parents[1]
MARKER = "private-zap-marker"


def _report(risks: tuple[str, ...] = ("0", "1", "2", "3")) -> dict:
    return {
        "@version": "2.16.1",
        "site": [
            {
                "@name": f"https://{MARKER}.invalid",
                "alerts": [
                    {
                        "pluginid": str(10000 + index),
                        "riskcode": risk,
                        "name": MARKER,
                        "desc": MARKER,
                        "instances": [{"uri": MARKER, "evidence": MARKER}],
                    }
                    for index, risk in enumerate(risks)
                ],
            }
        ],
    }


def _run(tmp_path: Path, payload: str, outcome: str = "success"):
    source = tmp_path / "raw.json"
    output = tmp_path / "zap-results.sarif"
    source.write_text(payload)
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = zap_sarif_producer.main(
            [
                "--json-in",
                str(source),
                "--sarif-out",
                str(output),
                "--scan-outcome",
                outcome,
            ]
        )
    result = SimpleNamespace(
        returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue()
    )
    return result, output


def test_produces_safe_sarif_with_all_risks(tmp_path: Path) -> None:
    result, output = _run(tmp_path, json.dumps(_report()))
    assert result.returncode == 0, result.stderr
    document = json.loads(output.read_text())
    run = document["runs"][0]
    assert document["version"] == "2.1.0"
    assert run["tool"]["driver"]["name"] == "OWASP ZAP"
    assert [item["level"] for item in run["results"]] == [
        "note",
        "note",
        "warning",
        "error",
    ]
    assert [item["ruleId"] for item in run["results"]] == [
        "10000-risk-0",
        "10001-risk-1",
        "10002-risk-2",
        "10003-risk-3",
    ]
    assert MARKER not in output.read_text() + result.stdout + result.stderr
    assert "invocations" not in run  # Conversion is not execution/coverage proof.


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        "[]",
        "{",
        '{"site": [], "@version":"2.16.1"}',
        '{"site":[],"site":[]}',
        '{"site":NaN}',
        json.dumps({**_report(), "@version": MARKER}),
        json.dumps(
            {
                "@version": "2.16.1",
                "site": [{"alerts": [{"pluginid": MARKER, "riskcode": "2"}]}],
            }
        ),
        json.dumps(
            {
                "@version": "2.16.1",
                "site": [{"alerts": [{"pluginid": "10000", "riskcode": "4"}]}],
            }
        ),
    ],
)
def test_invalid_reports_do_not_create_publication(
    tmp_path: Path, payload: str
) -> None:
    result, output = _run(tmp_path, payload)
    assert result.returncode != 0
    assert not output.exists()
    assert MARKER not in result.stdout + result.stderr


@pytest.mark.parametrize("outcome", ["failure", "skipped", "cancelled", ""])
def test_unsuccessful_scans_do_not_create_publication(
    tmp_path: Path, outcome: str
) -> None:
    result, output = _run(tmp_path, json.dumps(_report()), outcome)
    assert result.returncode != 0
    assert not output.exists()


def test_valid_site_without_alerts_is_not_execution_claim(tmp_path: Path) -> None:
    result, output = _run(tmp_path, json.dumps(_report(())))
    assert result.returncode == 0
    run = json.loads(output.read_text())["runs"][0]
    assert run["results"] == []
    assert "invocations" not in run


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "zap-results.sarif"
    output.write_text("original")
    result, _ = _run(tmp_path, json.dumps(_report()))
    assert result.returncode != 0
    assert output.read_text() == "original"


def test_symlink_input_is_rejected(tmp_path: Path) -> None:
    original = tmp_path / "original.json"
    original.write_text(json.dumps(_report()))
    (tmp_path / "raw.json").symlink_to(original)
    result, output = _run(tmp_path, json.dumps(_report()))
    assert result.returncode != 0
    assert not output.exists()


def test_mixed_risks_for_one_plugin_are_preserved(tmp_path: Path) -> None:
    report = _report(("1", "2"))
    for alert in report["site"][0]["alerts"]:
        alert["pluginid"] = "10055"
    result, output = _run(tmp_path, json.dumps(report))
    assert result.returncode == 0
    run = json.loads(output.read_text())["runs"][0]
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == [
        "10055-risk-1",
        "10055-risk-2",
    ]
    assert [
        rule["properties"]["security-severity"]
        for rule in run["tool"]["driver"]["rules"]
    ] == ["2.0", "5.0"]
    assert [item["level"] for item in run["results"]] == ["note", "warning"]


def test_locations_reference_real_sanitized_evidence(tmp_path: Path) -> None:
    result, output = _run(tmp_path, json.dumps(_report()))
    assert result.returncode == 0
    run = json.loads(output.read_text())["runs"][0]
    evidence = tmp_path / "zap-evidence.txt"
    assert evidence.is_file()
    lines = evidence.read_text().splitlines()
    assert MARKER not in evidence.read_text()
    for item in run["results"]:
        location = item["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == "zap-evidence.txt"
        line = lines[location["region"]["startLine"] - 1]
        assert line == location["region"]["snippet"]["text"]
        assert item["ruleId"] in line
    assert run["artifacts"][0]["contents"]["text"] == evidence.read_text()


def test_existing_evidence_is_not_overwritten(tmp_path: Path) -> None:
    evidence = tmp_path / "zap-evidence.txt"
    evidence.write_text("original")
    result, output = _run(tmp_path, json.dumps(_report()))
    assert result.returncode != 0
    assert not output.exists()
    assert evidence.read_text() == "original"


def test_relative_locations_have_an_explicit_artifact_root(tmp_path: Path) -> None:
    result, output = _run(tmp_path, json.dumps(_report()))
    assert result.returncode == 0
    run = json.loads(output.read_text())["runs"][0]
    assert "uri" not in run["originalUriBaseIds"]["ZAP_OUTPUT"]
    assert "description" in run["originalUriBaseIds"]["ZAP_OUTPUT"]
    for item in run["results"]:
        assert (
            item["locations"][0]["physicalLocation"]["artifactLocation"]["uriBaseId"]
            == "ZAP_OUTPUT"
        )


@pytest.mark.parametrize("use_symlink", [False, True])
def test_output_parent_names_are_never_published(
    tmp_path: Path, use_symlink: bool
) -> None:
    private_parent = tmp_path / "private-user-name-marker"
    private_parent.mkdir()
    output_parent = private_parent
    if use_symlink:
        output_parent = tmp_path / "private-alias-marker"
        output_parent.symlink_to(private_parent, target_is_directory=True)
    result, output = _run(output_parent, json.dumps(_report()))
    assert result.returncode == 0
    published = (
        output.read_text()
        + (output_parent / "zap-evidence.txt").read_text()
        + result.stdout
        + result.stderr
    )
    assert "private-user-name-marker" not in published
    assert "private-alias-marker" not in published
    assert str(tmp_path) not in published
    assert tmp_path.as_uri() not in published


def test_identical_reports_are_location_independent(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    result_a, output_a = _run(first, json.dumps(_report()))
    result_b, output_b = _run(second, json.dumps(_report()))
    assert result_a.returncode == result_b.returncode == 0
    assert output_a.read_bytes() == output_b.read_bytes()


def test_nonregular_input_fails_without_waiting(tmp_path: Path) -> None:
    import os

    source, output = tmp_path / "pipe", tmp_path / "zap-results.sarif"
    os.mkfifo(source)
    assert (
        zap_sarif_producer.main(
            [
                "--json-in",
                str(source),
                "--sarif-out",
                str(output),
                "--scan-outcome",
                "success",
            ]
        )
        == 1
    )
    assert not output.exists()


def test_bounded_reader_rejects_oversized_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(zap_sarif_producer, "MAX_REPORT_BYTES", 1)
    result, output = _run(tmp_path, json.dumps(_report()))
    assert result.returncode == 1
    assert not output.exists()


def test_producer_module_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import runpy
    import sys

    source, output = tmp_path / "raw.json", tmp_path / "zap-results.sarif"
    source.write_text(json.dumps(_report()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "zap_sarif_producer",
            "--json-in",
            str(source),
            "--sarif-out",
            str(output),
            "--scan-outcome",
            "success",
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(
            str(ROOT / "scripts/quality/zap_sarif_producer.py"), run_name="__main__"
        )
    assert exit_info.value.code == 0
    assert len(json.loads(output.read_text())["runs"][0]["results"]) == 4


def test_projection_is_stable_across_process_hash_seeds() -> None:
    import asyncio
    import os
    import sys

    script = (
        "import json;from scripts.quality.zap_sarif_producer import build_report;"
        "payload=json.dumps({'@version':'2.16.1','site':[{'alerts':["
        "{'pluginid':'1','riskcode':'2'},{'pluginid':'01','riskcode':'2'}]}]}).encode();"
        "print(json.dumps(build_report(payload)[0],sort_keys=True))"
    )

    async def output(seed: str) -> bytes:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr
        return stdout

    assert asyncio.run(output("0")) == asyncio.run(output("1"))
