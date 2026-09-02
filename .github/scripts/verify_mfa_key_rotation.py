"""Fail-closed proof that all MFA key rings were safely rotated."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_GROUPS = ("otp", "delivery", "trusted")
_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_MAX_SECRET_JSON_BYTES = 1_048_576


def _fail(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("MFA rotation metadata is missing or invalid.")
    if not isinstance(value, dict):
        _fail("MFA rotation metadata is missing or invalid.")
    return value


def _decode_kubernetes_value(data: dict[str, Any], key: str) -> str:
    encoded = data.get(key)
    if not isinstance(encoded, str) or not encoded:
        _fail("The application Secret is missing required MFA rotation data.")
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeError):
        _fail("The application Secret contains invalid MFA rotation data.")
    if not decoded:
        _fail("The application Secret contains empty MFA rotation data.")
    return decoded


def _parse_ring(raw: str) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    seen_fingerprints: set[str] = set()
    for entry in raw.split(","):
        try:
            key_id, encoded_key = entry.strip().split(":", 1)
        except ValueError:
            _fail("An MFA key ring is malformed.")
        key_id = key_id.strip()
        encoded_key = encoded_key.strip()
        if not _KEY_ID.fullmatch(key_id) or not encoded_key or key_id in fingerprints:
            _fail("An MFA key ring is malformed.")
        padding = "=" * ((4 - len(encoded_key) % 4) % 4)
        try:
            material = base64.b64decode(
                encoded_key + padding,
                altchars=b"-_",
                validate=True,
            )
        except binascii.Error:
            _fail("An MFA key ring is malformed.")
        if len(material) < 32:
            _fail("An MFA key ring is malformed.")
        fingerprint = hashlib.sha256(material).hexdigest()
        if fingerprint in seen_fingerprints:
            _fail("An MFA key ring reuses cryptographic key material.")
        seen_fingerprints.add(fingerprint)
        fingerprints[key_id] = fingerprint
    if not fingerprints:
        _fail("An MFA key ring is empty.")
    return fingerprints


def _read_secret(expected_name: str, contract: dict[str, Any]) -> dict[str, Any]:
    payload = sys.stdin.buffer.read(_MAX_SECRET_JSON_BYTES + 1)
    if len(payload) > _MAX_SECRET_JSON_BYTES:
        _fail("The application Secret response is unexpectedly large.")
    try:
        secret = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError):
        _fail("The application Secret response is invalid.")
    if not isinstance(secret, dict):
        _fail("The application Secret response is invalid.")
    metadata = secret.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("name") != expected_name:
        _fail("The application Secret identity does not match the deployment contract.")
    data = secret.get("data")
    if not isinstance(data, dict):
        _fail("The application Secret response has no data.")

    result: dict[str, Any] = {}
    all_fingerprints: set[str] = set()
    if set(contract) != set(_GROUPS):
        _fail("The rendered MFA key contract is incomplete.")
    for group in _GROUPS:
        mapping = contract.get(group)
        if not isinstance(mapping, dict) or set(mapping) != {"ring", "active"}:
            _fail("The rendered MFA key contract is incomplete.")
        ring_key = mapping["ring"]
        active_key = mapping["active"]
        if not isinstance(ring_key, str) or not isinstance(active_key, str):
            _fail("The rendered MFA key contract is invalid.")
        fingerprints = _parse_ring(_decode_kubernetes_value(data, ring_key))
        if all_fingerprints.intersection(fingerprints.values()):
            _fail("MFA key rings reuse cryptographic key material.")
        all_fingerprints.update(fingerprints.values())
        active_id = _decode_kubernetes_value(data, active_key)
        if not _KEY_ID.fullmatch(active_id) or active_id not in fingerprints:
            _fail("An active MFA key ID is invalid or absent from its ring.")
        result[group] = {
            "active_id": active_id,
            "fingerprints": fingerprints,
        }
    return result


def _write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(metadata, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _resolve_paths(mode: str, state_raw: str, contract_raw: str) -> tuple[Path, Path]:
    runner_temp_raw = os.environ.get("RUNNER_TEMP", "")
    if not runner_temp_raw:
        _fail("RUNNER_TEMP is required for MFA rotation metadata.")
    try:
        runner_temp = Path(runner_temp_raw).resolve(strict=True)
        contract = Path(contract_raw).resolve(strict=True)
        state_candidate = Path(state_raw)
        state = (
            state_candidate
            if state_candidate.is_absolute()
            else runner_temp / state_candidate
        ).resolve(strict=mode == "verify-post")
        state.relative_to(runner_temp)
        contract.relative_to(runner_temp)
    except (OSError, ValueError):
        _fail("MFA rotation metadata paths must stay under RUNNER_TEMP.")
    if mode == "capture-pre":
        if state.exists():
            _fail("MFA rotation state already exists; refusing stale reuse.")
        state.mkdir(mode=0o700)
    elif not state.is_dir():
        _fail("Prepared MFA rotation state is unavailable.")
    state.chmod(0o700)
    return state, contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture-pre", "verify-post"))
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--contract-file", required=True)
    parser.add_argument("--expected-secret-name", required=True)
    args = parser.parse_args()

    state, contract_path = _resolve_paths(args.mode, args.state_dir, args.contract_file)
    contract = _load_json(contract_path)
    current = _read_secret(args.expected_secret_name, contract)
    if args.mode == "capture-pre":
        _write_metadata(state / "pre-key-metadata.json", current)
        return

    previous = _load_json(state / "pre-key-metadata.json")
    if set(previous) != set(_GROUPS):
        _fail("Pre-rotation MFA key metadata is incomplete.")
    validated_previous: dict[str, tuple[str, dict[str, str]]] = {}
    all_previous_fingerprints: set[str] = set()
    for group in _GROUPS:
        before = previous.get(group)
        if not isinstance(before, dict):
            _fail("Pre-rotation MFA key metadata is incomplete.")
        old_active = before.get("active_id")
        old_fingerprints = before.get("fingerprints")
        if (
            not isinstance(old_active, str)
            or not isinstance(old_fingerprints, dict)
            or old_active not in old_fingerprints
            or not all(
                isinstance(key_id, str)
                and _KEY_ID.fullmatch(key_id)
                and isinstance(fingerprint, str)
                and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                for key_id, fingerprint in old_fingerprints.items()
            )
        ):
            _fail("Pre-rotation MFA key metadata is incomplete.")
        normalized_fingerprints = {
            str(key_id): str(fingerprint)
            for key_id, fingerprint in old_fingerprints.items()
        }
        if all_previous_fingerprints.intersection(normalized_fingerprints.values()):
            _fail("Pre-rotation MFA key metadata is invalid.")
        all_previous_fingerprints.update(normalized_fingerprints.values())
        validated_previous[group] = (old_active, normalized_fingerprints)

    for group in _GROUPS:
        old_active, old_fingerprints = validated_previous[group]
        after = current[group]
        if old_active == after["active_id"]:
            _fail("An MFA active key ID did not rotate.")
        after_fingerprints = after["fingerprints"]
        if old_active not in after_fingerprints:
            _fail("A previous active MFA key is absent from the overlap ring.")
        if old_fingerprints[old_active] != after_fingerprints[old_active]:
            _fail("A previous active MFA key changed inside the overlap ring.")
        if after_fingerprints[after["active_id"]] in all_previous_fingerprints:
            _fail("A new active MFA key reuses pre-rotation key material.")
    _write_metadata(state / "post-key-metadata.json", current)


if __name__ == "__main__":
    main()
