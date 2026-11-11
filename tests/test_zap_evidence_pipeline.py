"""Integration of real provenance, production and gating over one snapshot."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from scripts.quality import zap_run_provenance

TARGET = "https://stage.example.test"
IDENTITY = {
    "source_sha": "a" * 40,
    "run_id": "123",
    "run_attempt": "2",
    "image": "ghcr.io/zaproxy/zaproxy@sha256:" + "b" * 64,
    "rules_sha256": "c" * 64,
    "hook_sha256": "d" * 64,
}


def _run(tmp_path: Path, risk: str = "2"):
    work = tmp_path / "private"
    nonce = zap_run_provenance.start_run(work, IDENTITY)
    source = work / "scan" / "report_json.json"
    source.write_text(
        json.dumps(
            {
                "@version": "2.16.1",
                "site": [
                    {
                        "@name": TARGET,
                        "alerts": [{"pluginid": "10055", "riskcode": risk}],
                    }
                ],
            }
        )
    )
    (work / "scan" / "origin-proof.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "message_id": "1",
                "request_header": "GET https://stage.example.test/ HTTP/1.1\r\nHost: stage.example.test\r\n\r\n",
                "response_header": "HTTP/1.1 200 OK\r\n\r\n",
            }
        )
    )
    zap_run_provenance.finish_run(work, IDENTITY, nonce, 2, TARGET)
    public = tmp_path / "public"
    public.mkdir()
    return work, nonce, source, public / "zap-results.sarif"


def _module():
    spec = importlib.util.find_spec("scripts.quality.zap_evidence_pipeline")
    assert spec is not None, "missing verified payload pipeline"
    return importlib.import_module("scripts.quality.zap_evidence_pipeline")


@pytest.mark.parametrize(("risk", "expected"), [("0", 0), ("1", 0), ("2", 1), ("3", 1)])
def test_verified_payload_publishes_before_unchanged_threshold(
    tmp_path: Path, risk: str, expected: int
) -> None:
    work, nonce, _, sarif = _run(tmp_path, risk)
    publication = _module().prepare_publication(work, IDENTITY, nonce, TARGET, sarif)
    assert sarif.is_file()
    assert publication.enforce_threshold(None) == expected


def test_publication_never_rereads_raw_after_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    work, nonce, source, sarif = _run(tmp_path)
    original = module.verify_run

    def capture_then_mutate(*args):
        payload = original(*args)
        changed = json.loads(payload)
        changed["site"][0]["alerts"][0]["riskcode"] = "0"
        source.write_text(json.dumps(changed))
        return payload

    monkeypatch.setattr(module, "verify_run", capture_then_mutate)
    publication = module.prepare_publication(work, IDENTITY, nonce, TARGET, sarif)
    assert json.loads(sarif.read_text())["runs"][0]["results"][0]["level"] == "warning"
    assert publication.enforce_threshold(None) == 1


def test_tampered_publication_does_not_pass_gate(tmp_path: Path) -> None:
    work, nonce, _, sarif = _run(tmp_path)
    publication = _module().prepare_publication(work, IDENTITY, nonce, TARGET, sarif)
    changed = json.loads(sarif.read_text())
    changed["runs"][0]["results"] = []
    sarif.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        publication.enforce_threshold(None)


@pytest.mark.parametrize("change", ["nonce", "origin", "raw", "proof"])
def test_unverified_run_never_creates_public_output(
    tmp_path: Path, change: str
) -> None:
    work, nonce, source, sarif = _run(tmp_path)
    target = TARGET
    if change == "nonce":
        nonce = "0" * 32
    elif change == "origin":
        target = "https://attacker.invalid"
    elif change == "raw":
        source.write_text(source.read_text() + "\n")
    else:
        proof = work / "scan" / "origin-proof.json"
        proof.write_text(proof.read_text() + "\n")
    with pytest.raises(ValueError):
        _module().prepare_publication(work, IDENTITY, nonce, target, sarif)
    assert not sarif.exists()


def test_public_output_cannot_share_private_run_directory(tmp_path: Path) -> None:
    work, nonce, _, _ = _run(tmp_path)
    with pytest.raises(ValueError):
        _module().prepare_publication(
            work, IDENTITY, nonce, TARGET, work / "zap-results.sarif"
        )
    assert not (work / "zap-results.sarif").exists()
