"""Offline contract for a trusted runner's fresh, current-run ZAP evidence.

This is NOT scanner attestation. A trusted wrapper must create the directory
before Docker starts and call finish_run only with the real completed exit
status. Do not upload context, reports or logs. The helper binds a report to
that wrapper's nonce and workflow identity; it does not prove scan coverage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from scripts.quality.zap_findings_gate import (
    _reject_duplicate_keys,
    _reject_nonfinite_constant,
)
from scripts.quality.zap_origin_evidence import origin, validate_proof
from scripts.quality.zap_sarif_producer import build_report, read_payload

_PATTERNS = {
    "source_sha": r"[0-9a-f]{40}",
    "run_id": r"[1-9][0-9]*",
    "run_attempt": r"[1-9][0-9]*",
    "image": r"ghcr\.io/zaproxy/zaproxy@sha256:[0-9a-f]{64}",
    "rules_sha256": r"[0-9a-f]{64}",
    "hook_sha256": r"[0-9a-f]{64}",
}


def _identity(identity: dict[str, str]) -> dict[str, str]:
    if set(identity) != set(_PATTERNS) or any(
        not isinstance(identity[key], str)
        or re.fullmatch(pattern, identity[key]) is None
        for key, pattern in _PATTERNS.items()
    ):
        raise ValueError("Invalid ZAP run identity")
    return dict(identity)


def _object(payload: bytes) -> dict[str, Any]:
    value = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Invalid ZAP receipt object")
    return value


def _load(path: Path) -> dict[str, Any]:
    return _object(read_payload(path))


def _write_new(path: Path, value: dict[str, Any]) -> None:
    # Parent directory is private; exclusive creation refuses stale evidence.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def start_run(work: Path, identity: dict[str, str]) -> str:
    """Reserve a never-reused directory and unpredictable current-run nonce."""
    identity = _identity(identity)
    nonce = secrets.token_hex(16)
    work.mkdir(mode=0o700, parents=False, exist_ok=False)
    (work / "scan").mkdir(mode=0o700)
    _write_new(
        work / "context.json",
        {
            "schema_version": 1,
            "identity": identity,
            "run_nonce": nonce,
            "started_ns": time.time_ns(),
        },
    )
    return nonce


def _context(work: Path, identity: dict[str, str], nonce: str) -> dict[str, Any]:
    if (
        work.is_symlink()
        or not work.is_dir()
        or (work / "scan").is_symlink()
        or not (work / "scan").is_dir()
    ):
        raise ValueError("Invalid ZAP run directory")
    identity = _identity(identity)
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise ValueError("Invalid ZAP run nonce")
    context = _load(work / "context.json")
    if (
        set(context) != {"schema_version", "identity", "run_nonce", "started_ns"}
        or type(context["schema_version"]) is not int
        or context["schema_version"] != 1
        or context["identity"] != identity
        or context["run_nonce"] != nonce
        or type(context["started_ns"]) is not int
        or context["started_ns"] <= 0
    ):
        raise ValueError("ZAP run identity mismatch")
    return context


def _validate_report_site(payload: bytes, target: str) -> None:
    # Traditional JSON enumerates the site tree even when alerts is empty.
    # @name is authoritative: upstream @host derivation is not IPv6-safe.
    expected = origin(target)
    for site in _object(payload)["site"]:
        try:
            actual = origin(site.get("@name"))
        except ValueError:
            continue
        if actual == expected:
            return
    raise ValueError("ZAP report has no matching target site")


def finish_run(
    work: Path, identity: dict[str, str], nonce: str, exit_code: int, target: str
) -> dict[str, Any]:
    """Bind a valid report to a completed scanner exit, not a successful gate."""
    context = _context(work, identity, nonce)
    # Official zap-full-scan.py: 0=success, 1=FAIL findings, 2=WARN, 3=error.
    if type(exit_code) is not int or exit_code not in (0, 1, 2):
        raise ValueError("ZAP scanner did not complete")
    payload = read_payload(work / "scan" / "report_json.json")
    build_report(payload)
    _validate_report_site(payload, target)
    proof_payload = read_payload(work / "scan" / "origin-proof.json")
    validate_proof(_object(proof_payload), target)
    finished_ns = time.time_ns()
    if finished_ns < context["started_ns"]:
        raise ValueError("ZAP run clock moved backwards")
    receipt = {
        **context,
        "finished_ns": finished_ns,
        "scanner_exit_code": exit_code,
        "raw_report_sha256": hashlib.sha256(payload).hexdigest(),
        "coverage_complete": False,
        "origin_proof_sha256": hashlib.sha256(proof_payload).hexdigest(),
        "origin_response_verified": True,
    }
    _write_new(work / "receipt.json", receipt)
    return receipt


def verify_run(work: Path, identity: dict[str, str], nonce: str, target: str) -> bytes:
    """Return exact report bytes only when context, receipt and digest agree."""
    context = _context(work, identity, nonce)
    receipt = _load(work / "receipt.json")
    if (
        set(receipt)
        != set(context)
        | {
            "finished_ns",
            "scanner_exit_code",
            "raw_report_sha256",
            "coverage_complete",
            "origin_proof_sha256",
            "origin_response_verified",
        }
        or any(receipt[key] != value for key, value in context.items())
        or type(receipt["schema_version"]) is not int
        or type(receipt["started_ns"]) is not int
        or type(receipt["finished_ns"]) is not int
        or receipt["finished_ns"] < context["started_ns"]
        or type(receipt["scanner_exit_code"]) is not int
        or receipt["scanner_exit_code"] not in (0, 1, 2)
        or receipt["coverage_complete"] is not False
        or receipt["origin_response_verified"] is not True
    ):
        raise ValueError("ZAP receipt does not match this run")
    payload = read_payload(work / "scan" / "report_json.json")
    if receipt["raw_report_sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError("ZAP report changed after scan completion")
    proof_payload = read_payload(work / "scan" / "origin-proof.json")
    if receipt["origin_proof_sha256"] != hashlib.sha256(proof_payload).hexdigest():
        raise ValueError("ZAP response evidence changed after scan completion")
    validate_proof(_object(proof_payload), target)
    build_report(payload)
    _validate_report_site(payload, target)
    return payload
