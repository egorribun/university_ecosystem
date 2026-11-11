"""Trusted ZAP workflow orchestration; private execution, public projections only."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.quality.dast_privacy import prepare_target
from scripts.quality.zap_evidence_pipeline import prepare_publication
from scripts.quality.zap_findings_gate import evaluate_alerts
from scripts.quality.zap_report_binding import verify_payload
from scripts.quality.zap_run_provenance import _identity, _object, verify_run
from scripts.quality.zap_runner import run_scan
from scripts.quality.zap_sarif_producer import read_payload

MODULES = (
    "dast_privacy",
    "nuclei_findings_gate",
    "zap_findings_gate",
    "zap_evidence_pipeline",
    "zap_origin_evidence",
    "zap_report_binding",
    "zap_run_provenance",
    "zap_runner",
    "zap_sarif_producer",
    "zap_workflow",
)
SOURCE_FILES = (
    ".github/workflows/dast.yml",
    ".zap/rules.tsv",
    ".zap/image.txt",
    *(f"scripts/quality/{name}.py" for name in MODULES),
)
PUBLIC_FILES = ("zap-results.sarif", "zap-evidence.txt")
RECEIPT = "zap-sarif-provenance.json"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def _write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _git(root: Path, *args: str) -> bytes:
    binary = shutil.which("git")
    if binary is None:
        raise ValueError("Git unavailable")

    async def read() -> bytes:
        process = await asyncio.create_subprocess_exec(
            binary,
            *args,
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise ValueError("Could not verify committed ZAP source")
        return stdout

    return asyncio.run(read())


def verify_source(root: Path, env: dict[str, str]) -> dict[str, Any]:
    """Reject untrusted events and changed source before accessing the target."""
    if env.get("GITHUB_REF") != "refs/heads/main" or env.get(
        "GITHUB_EVENT_NAME"
    ) not in {"schedule", "workflow_dispatch"}:
        raise ValueError("ZAP requires a trusted main schedule or manual event")
    repository = env.get("GITHUB_REPOSITORY", "")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("Invalid ZAP repository identity")
    sha = env.get("GITHUB_SHA", "")
    if (
        re.fullmatch(r"[0-9a-f]{40}", sha) is None
        or _git(root, "rev-parse", "HEAD").decode().strip() != sha
    ):
        raise ValueError("ZAP event source mismatch")
    root = root.resolve(strict=True)
    hashes = {}
    contents = {}
    initializers = ("scripts/__init__.py", "scripts/quality/__init__.py")
    tracked = (
        _git(root, "ls-tree", "-r", "--name-only", sha, "--", *initializers)
        .decode()
        .splitlines()
    )
    optional = tuple(
        name
        for name in initializers
        if name in tracked or (root / name).exists() or (root / name).is_symlink()
    )
    for relative in (*SOURCE_FILES, *optional):
        path = root / relative
        if path.resolve(strict=True) != path or path.is_symlink():
            raise ValueError("ZAP source must not contain symlinks")
        payload = read_payload(path)
        if payload != _git(root, "show", f"{sha}:{relative}"):
            raise ValueError("ZAP source differs from event commit")
        hashes[relative] = _digest(payload)
        contents[relative] = payload
    image = contents[".zap/image.txt"].decode().strip()
    identity = _identity(
        {
            "source_sha": sha,
            "run_id": env.get("GITHUB_RUN_ID", ""),
            "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
            "image": image,
            "rules_sha256": hashes[".zap/rules.tsv"],
            "hook_sha256": hashes["scripts/quality/zap_origin_evidence.py"],
        }
    )
    return {"repository": repository, "identity": identity, "files": hashes}


def _paths(work: Path, public: Path) -> None:
    a, b = work.resolve(), public.resolve()
    if a.is_relative_to(b) or b.is_relative_to(a):
        raise ValueError("Public and private ZAP directories must be separate")
    if work.is_symlink() or public.is_symlink():
        raise ValueError("Invalid ZAP directory")


def _public_receipt(manifest: dict[str, Any], manifest_bytes: bytes) -> dict[str, Any]:
    return {
        "schema_version": 1,
        **manifest["source"],
        "raw_report_sha256": manifest["raw_report_sha256"],
        "private_receipt_sha256": manifest["private_receipt_sha256"],
        "publication_sha256": _digest(manifest_bytes),
        "outputs": manifest["outputs"],
        "origin_response_verified": True,
        "coverage_complete": False,
    }


def prepare(root: Path, env: dict[str, str], work: Path, public: Path) -> None:
    """Execute the private runner and seal a fresh cross-process publication."""
    source = verify_source(root, env)
    _paths(work, public)
    if work.exists() or public.exists():
        raise ValueError("ZAP output directories must be fresh")
    target_file = work.with_name(work.name + "-target.txt")
    if prepare_target(target_file, env) != 0:
        raise ValueError("Invalid ZAP target")
    try:
        target = read_payload(target_file).decode("utf-8")
        receipt = asyncio.run(
            run_scan(
                target_file, root / ".zap/rules.tsv", work, source["identity"], 2700
            )
        )
    finally:
        target_file.unlink(missing_ok=True)
    public.mkdir(mode=0o700)
    prepare_publication(
        work,
        source["identity"],
        receipt["run_nonce"],
        target,
        public / "zap-results.sarif",
    )
    manifest = {
        "schema_version": 1,
        "source": source,
        "target": target,
        "nonce": receipt["run_nonce"],
        "raw_report_sha256": receipt["raw_report_sha256"],
        "private_receipt_sha256": _digest(read_payload(work / "receipt.json")),
        "outputs": {
            name: _digest(read_payload(public / name)) for name in PUBLIC_FILES
        },
    }
    encoded = _encoded(manifest)
    _write(work / "publication.json", encoded)
    _write(public / RECEIPT, _encoded(_public_receipt(manifest, encoded)))
    verify_publication(root, env, work, public)


def verify_publication(
    root: Path, env: dict[str, str], work: Path, public: Path
) -> list[tuple[int, str]]:
    """Revalidate the same private run and exact uploaded bytes in a new process."""
    source = verify_source(root, env)
    _paths(work, public)
    manifest_bytes = read_payload(work / "publication.json")
    manifest = _object(manifest_bytes)
    if (
        set(manifest)
        != {
            "schema_version",
            "source",
            "target",
            "nonce",
            "raw_report_sha256",
            "private_receipt_sha256",
            "outputs",
        }
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["source"] != source
        or manifest_bytes != _encoded(manifest)
    ):
        raise ValueError("Invalid ZAP publication identity")
    if (
        _digest(read_payload(work / "receipt.json"))
        != manifest["private_receipt_sha256"]
    ):
        raise ValueError("ZAP private receipt changed")
    payload = verify_run(
        work, source["identity"], manifest["nonce"], manifest["target"]
    )
    if _digest(payload) != manifest["raw_report_sha256"]:
        raise ValueError("ZAP raw report changed")
    outputs = {name: _digest(read_payload(public / name)) for name in PUBLIC_FILES}
    if outputs != manifest["outputs"]:
        raise ValueError("ZAP public files changed")
    if read_payload(public / RECEIPT) != _encoded(
        _public_receipt(manifest, manifest_bytes)
    ):
        raise ValueError("ZAP public provenance changed")
    return verify_payload(payload, public / "zap-results.sarif")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "gate"))
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--public", required=True, type=Path)
    parser.add_argument("--summary-file", type=Path)
    args = parser.parse_args(argv)
    try:
        env = dict(os.environ)
        if args.command == "prepare":
            prepare(args.repo_root, env, args.work, args.public)
        else:
            alerts = verify_publication(args.repo_root, env, args.work, args.public)
            if args.command == "gate":
                return evaluate_alerts(alerts, args.summary_file)
    except (
        OSError,
        ValueError,
        UnicodeError,
        RecursionError,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
    ):
        print(
            "::error::ZAP evidence validation failed; scan result is unknown.",
            file=sys.stderr,
        )
        return 1
    print("ZAP evidence verified; full scan coverage is not asserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
