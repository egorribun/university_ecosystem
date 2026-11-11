"""Real producer-to-gate checks against substituted DAST evidence."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from scripts.quality import zap_sarif_producer as producer


def _produce(tmp_path: Path, risk: str = "2") -> tuple[Path, Path]:
    source, sarif = tmp_path / "raw.json", tmp_path / "zap-results.sarif"
    source.write_text(
        json.dumps(
            {
                "@version": "2.16.1",
                "site": [{"alerts": [{"pluginid": "10055", "riskcode": risk}]}],
            }
        )
    )
    producer.produce(source, sarif, "success")
    return source, sarif


def _verify(
    source: Path, sarif: Path, enforce: bool = False, outcome: str = "success"
) -> int:
    spec = importlib.util.find_spec("scripts.quality.zap_report_binding")
    assert spec is not None, "missing JSON/SARIF binding gate"
    binding = importlib.import_module("scripts.quality.zap_report_binding")
    arguments = [
        "--json-in",
        str(source),
        "--sarif-in",
        str(sarif),
        "--scan-outcome",
        outcome,
    ]
    if enforce:
        arguments.append("--enforce-threshold")
    return binding.main(arguments)


@pytest.mark.parametrize(("risk", "expected"), [("0", 0), ("1", 0), ("2", 1), ("3", 1)])
def test_binding_succeeds_before_publication_but_threshold_remains(
    risk: str, expected: int, tmp_path: Path
) -> None:
    source, sarif = _produce(tmp_path, risk)
    assert _verify(source, sarif) == 0
    assert _verify(source, sarif, enforce=True) == expected


@pytest.mark.parametrize(
    "mutation",
    [
        "json-risk",
        "json-plugin",
        "json-byte",
        "sarif-clean",
        "sarif-risk",
        "sarif-type",
        "sarif-digest",
        "sarif-text",
        "evidence",
        "duplicate-key",
    ],
)
def test_modified_raw_or_public_evidence_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    source, sarif = _produce(tmp_path)
    raw = json.loads(source.read_text())
    public = json.loads(sarif.read_text())
    if mutation == "json-risk":
        raw["site"][0]["alerts"][0]["riskcode"] = "1"
        source.write_text(json.dumps(raw))
    elif mutation == "json-plugin":
        raw["site"][0]["alerts"][0]["pluginid"] = "10000"
        source.write_text(json.dumps(raw))
    elif mutation == "json-byte":
        source.write_text(source.read_text() + "\n")
    elif mutation == "evidence":
        sarif.with_name("zap-evidence.txt").write_text("private-marker")
    elif mutation == "duplicate-key":
        sarif.write_text(
            sarif.read_text().replace(
                '"version": "2.1.0"', '"version": "1.0", "version": "2.1.0"'
            )
        )
    else:
        run = public["runs"][0]
        if mutation == "sarif-clean":
            run["results"] = []
        elif mutation == "sarif-risk":
            run["results"][0]["level"] = "note"
        elif mutation == "sarif-type":
            run["results"][0]["ruleIndex"] = False
        elif mutation == "sarif-digest":
            run["properties"]["sourceReportSha256"] = "0" * 64
        else:
            run["results"][0]["message"]["text"] = "private-marker"
        sarif.write_text(json.dumps(public))
    assert _verify(source, sarif) == 1
    assert _verify(source, sarif, enforce=True) == 1


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
def test_valid_evidence_cannot_override_failed_scan(
    tmp_path: Path, outcome: str
) -> None:
    source, sarif = _produce(tmp_path, "0")
    assert _verify(source, sarif, outcome=outcome) == 1


def test_threshold_uses_the_payload_already_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = importlib.import_module("scripts.quality.zap_report_binding")
    source, sarif = _produce(tmp_path, "2")
    original = binding.read_payload

    def mutate_after_read(path: Path) -> bytes:
        data = original(path)
        if path == source:
            replacement = json.loads(data)
            replacement["site"][0]["alerts"][0]["riskcode"] = "0"
            source.write_text(json.dumps(replacement))
        return data

    monkeypatch.setattr(binding, "read_payload", mutate_after_read)
    # If gating rereads source independently, it incorrectly passes this scan.
    assert _verify(source, sarif, enforce=True) == 1


def test_binding_module_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import runpy
    import sys

    source, sarif = _produce(tmp_path, "2")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "zap_report_binding",
            "--json-in",
            str(source),
            "--sarif-in",
            str(sarif),
            "--scan-outcome",
            "success",
            "--enforce-threshold",
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/quality/zap_report_binding.py"
            ),
            run_name="__main__",
        )
    assert exit_info.value.code == 1
