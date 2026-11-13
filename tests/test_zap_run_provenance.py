"""Offline current-run receipt contracts; these do not exercise ZAP or Docker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality import zap_run_provenance

IDENTITY = {
    "source_sha": "a" * 40,
    "run_id": "123",
    "run_attempt": "2",
    "image": "ghcr.io/zaproxy/zaproxy@sha256:" + "b" * 64,
    "rules_sha256": "c" * 64,
    "hook_sha256": "d" * 64,
}


TARGET = "https://stage.example.test"


def _start(tmp_path: Path):
    module = zap_run_provenance
    work = tmp_path / "run"
    nonce = module.start_run(work, IDENTITY)
    report = work / "scan" / "report_json.json"
    report.write_text(
        json.dumps(
            {
                "@version": "2.16.1",
                "site": [
                    {
                        "@name": TARGET,
                        "alerts": [{"pluginid": "10055", "riskcode": "2"}],
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
    return module, work, nonce, report


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_fresh_scan_receipt_accepts_documented_completed_exit_codes(
    tmp_path: Path, exit_code: int
) -> None:
    module, work, nonce, report = _start(tmp_path)
    receipt = module.finish_run(work, IDENTITY, nonce, exit_code, TARGET)
    payload = module.verify_run(work, IDENTITY, nonce, TARGET)
    assert payload == report.read_bytes()
    assert receipt["scanner_exit_code"] == exit_code
    assert receipt["run_nonce"] == nonce
    assert len(nonce) == 32
    assert not receipt.get("coverage_complete", False)


@pytest.mark.parametrize("exit_code", [3, 4, 124, -9, True])
def test_scanner_errors_do_not_create_success_receipt(
    tmp_path: Path, exit_code: int
) -> None:
    module, work, nonce, _ = _start(tmp_path)
    with pytest.raises(module.ScannerExitError) as raised:
        module.finish_run(work, IDENTITY, nonce, exit_code, TARGET)
    assert isinstance(raised.value, ValueError)
    # Only a plain bounded integer is kept; a bool is not an exit code.
    assert raised.value.exit_code == (None if exit_code is True else exit_code)
    assert raised.value.error_class is None
    assert not (work / "receipt.json").exists()


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        (b"Total of 3 URLs\nERROR <class 'ValueError'>\n", "ValueError"),
        (
            b"ERROR <class 'KeyError'>\r\n"
            b"ERROR <class 'requests.exceptions.ReadTimeout'>\r\n",
            "requests.exceptions.ReadTimeout",
        ),
        (b"ERROR http://127.0.0.1:8080/private-path failed\n", None),
        (b"ERROR <class 'x y'>\n", None),
        (b"WARN <class 'ValueError'>\n", None),
        (b"", None),
    ],
)
def test_scanner_exit_reads_only_the_upstream_exception_class(
    tmp_path: Path, log: bytes, expected: str | None
) -> None:
    module, work, nonce, _ = _start(tmp_path)
    (work / "stdout.log").write_bytes(log)
    with pytest.raises(module.ScannerExitError) as raised:
        module.finish_run(work, IDENTITY, nonce, 3, TARGET)
    assert raised.value.exit_code == 3
    assert raised.value.error_class == expected


@pytest.mark.parametrize("exit_code", [256, -256, "3", None, 3.0])
def test_scanner_exit_error_keeps_only_bounded_values(exit_code: object) -> None:
    error = zap_run_provenance.ScannerExitError(exit_code, "not a class name!")
    assert str(error) == "ZAP scanner did not complete"
    assert error.exit_code is None
    assert error.error_class is None


def test_existing_workdir_is_never_reused(tmp_path: Path) -> None:
    module, work, _, _ = _start(tmp_path)
    with pytest.raises((ValueError, FileExistsError)):
        module.start_run(work, IDENTITY)


@pytest.mark.parametrize(
    "field", ["source_sha", "run_id", "run_attempt", "image", "rules_sha256", "nonce"]
)
def test_receipt_cannot_be_replayed_into_different_run(
    tmp_path: Path, field: str
) -> None:
    module, work, nonce, _ = _start(tmp_path)
    module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    expected = dict(IDENTITY)
    if field == "nonce":
        nonce = "d" * 32
    elif field == "source_sha":
        expected[field] = "d" * 40
    elif field == "image":
        expected[field] = "ghcr.io/zaproxy/zaproxy@sha256:" + "d" * 64
    elif field == "rules_sha256":
        expected[field] = "d" * 64
    else:
        expected[field] = "999"
    with pytest.raises(ValueError):
        module.verify_run(work, expected, nonce, TARGET)


def test_changed_report_cannot_reuse_receipt(tmp_path: Path) -> None:
    module, work, nonce, report = _start(tmp_path)
    module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    report.write_text(report.read_text() + "\n")
    with pytest.raises(ValueError):
        module.verify_run(work, IDENTITY, nonce, TARGET)


@pytest.mark.parametrize("target", ["context.json", "report_json.json", "receipt.json"])
def test_symlinked_evidence_is_rejected(tmp_path: Path, target: str) -> None:
    module, work, nonce, _ = _start(tmp_path)
    module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    path = work / "scan" / target if target == "report_json.json" else work / target
    saved = tmp_path / "other"
    path.rename(saved)
    path.symlink_to(saved)
    with pytest.raises((ValueError, OSError)):
        module.verify_run(work, IDENTITY, nonce, TARGET)


@pytest.mark.parametrize(
    "field,value",
    [
        ("image", "ghcr.io/zaproxy/zaproxy:stable"),
        ("image", "attacker.invalid/zap@sha256:" + "b" * 64),
        ("source_sha", "main"),
        ("run_id", "0"),
        ("run_attempt", "-1"),
        ("rules_sha256", "bad"),
    ],
)
def test_invalid_identity_cannot_start(tmp_path: Path, field: str, value: str) -> None:
    module = zap_run_provenance
    identity = {**IDENTITY, field: value}
    with pytest.raises(ValueError):
        module.start_run(tmp_path / "run", identity)
    assert not (tmp_path / "run").exists()


def test_scan_directory_symlink_cannot_redirect_report(tmp_path: Path) -> None:
    module, work, nonce, _ = _start(tmp_path)
    scan = work / "scan"
    saved = tmp_path / "saved"
    scan.rename(saved)
    scan.symlink_to(saved, target_is_directory=True)
    with pytest.raises(ValueError):
        module.finish_run(work, IDENTITY, nonce, 0, TARGET)


def test_context_must_be_an_object(tmp_path: Path) -> None:
    module, work, nonce, _ = _start(tmp_path)
    (work / "context.json").write_text("[]")
    with pytest.raises(ValueError):
        module.finish_run(work, IDENTITY, nonce, 0, TARGET)


def test_work_directory_symlink_is_rejected(tmp_path: Path) -> None:
    module, work, nonce, _ = _start(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(work, target_is_directory=True)
    with pytest.raises(ValueError):
        module.finish_run(alias, IDENTITY, nonce, 0, TARGET)


def test_invalid_nonce_is_rejected(tmp_path: Path) -> None:
    module, work, _, _ = _start(tmp_path)
    with pytest.raises(ValueError):
        module.finish_run(work, IDENTITY, "invalid", 0, TARGET)


def test_backwards_clock_does_not_complete_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, work, nonce, _ = _start(tmp_path)
    started = json.loads((work / "context.json").read_text())["started_ns"]
    monkeypatch.setattr(module.time, "time_ns", lambda: started - 1)
    with pytest.raises(ValueError):
        module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    assert not (work / "receipt.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("scanner_exit_code", 3),
        ("coverage_complete", True),
        ("finished_ns", 0),
        ("started_ns", True),
        ("schema_version", True),
    ],
)
def test_invalid_receipt_does_not_verify(
    tmp_path: Path, field: str, value: object
) -> None:
    module, work, nonce, _ = _start(tmp_path)
    receipt = module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    receipt[field] = value
    (work / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        module.verify_run(work, IDENTITY, nonce, TARGET)


@pytest.mark.parametrize(
    "site",
    [
        {},
        {"@name": "https://other.test"},
        {"@name": "invalid"},
        {"@name": "http://stage.example.test"},
        {"@name": "https://stage.example.test:444"},
    ],
)
def test_receipt_rejects_report_without_target_site(tmp_path, site):
    module, work, nonce, _ = _start(tmp_path)
    source = work / "scan" / "report_json.json"
    value = json.loads(source.read_text())
    value["site"] = [{**site, "alerts": []}]
    source.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="target site"):
        module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    assert not (work / "receipt.json").exists()


@pytest.mark.parametrize(
    "name", [TARGET, "https://STAGE.example.test:443", "https://stage.example.test/"]
)
def test_clean_report_target_site_is_sufficient(tmp_path, name):
    module, work, nonce, report = _start(tmp_path)
    report.write_text(
        json.dumps(
            {
                "@version": "2.16.1",
                "site": [
                    {"@name": "https://other.test", "alerts": []},
                    {
                        "@name": name,
                        "@host": "stage.example.test",
                        "@port": "443",
                        "@ssl": "true",
                        "alerts": [],
                    },
                ],
            }
        )
    )
    module.finish_run(work, IDENTITY, nonce, 0, TARGET)
    assert module.verify_run(work, IDENTITY, nonce, TARGET) == report.read_bytes()
