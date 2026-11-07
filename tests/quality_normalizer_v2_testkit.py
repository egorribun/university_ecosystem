from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path


def write_complete_evidence(root: Path) -> None:
    """Create a minimal, internally consistent copy of every canonical report."""
    python_source = root / "app/example.py"
    python_source.parent.mkdir(parents=True, exist_ok=True)
    python_source.write_text("value = 1\n", encoding="utf-8")
    frontend_source = root / "frontend/src/example.ts"
    frontend_source.parent.mkdir(parents=True, exist_ok=True)
    frontend_source.write_text("export const value = 1\n", encoding="utf-8")
    payloads = {
        "coverage.xml": """<?xml version="1.0" ?>
<coverage branches-covered="1" branches-valid="1" lines-covered="1" lines-valid="1" version="7.10">
  <packages><package name="app"><classes><class filename="app/example.py" name="example">
    <methods /><lines><line branch="true" condition-coverage="100% (1/1)" hits="1" number="1" /></lines>
  </class></classes></package></packages>
</coverage>
""",
        "artifacts/coverage/python/coverage.json": json.dumps(
            {
                "meta": {"version": "7.10.0"},
                "files": {
                    "app/example.py": {
                        "executed_lines": [1],
                        "missing_lines": [],
                        "executed_branches": [[1, 2]],
                        "missing_branches": [],
                        "summary": {
                            "covered_lines": 1,
                            "num_statements": 1,
                            "covered_branches": 1,
                            "num_branches": 1,
                        },
                    }
                },
                "totals": {
                    "covered_lines": 1,
                    "num_statements": 1,
                    "covered_branches": 1,
                    "num_branches": 1,
                },
            }
        ),
        "frontend/coverage/lcov.info": """TN:
SF:frontend/src/example.ts
FN:1,example
FNDA:1,example
FNF:1
FNH:1
DA:1,1
LF:1
LH:1
BRDA:1,0,0,1
BRF:1
BRH:1
end_of_record
""",
        "frontend/coverage/coverage-final.json": json.dumps(
            {
                "frontend/src/example.ts": {
                    "path": "frontend/src/example.ts",
                    "statementMap": {"0": {}},
                    "branchMap": {"0": {}},
                    "fnMap": {"0": {}},
                    "s": {"0": 1},
                    "b": {"0": [1]},
                    "f": {"0": 1},
                }
            }
        ),
    }
    node_records = {}
    node_lcov = []
    for basename in ("capture.cjs", "index.cjs"):
        source_path = f".github/actions/dependency-review-capture/{basename}"
        source = root / source_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "module.exports = function choose(value) { return value ? 1 : 0; };\n",
            encoding="utf-8",
        )
        node_records[source_path] = {
            "path": source_path,
            "statementMap": {"0": {}},
            "branchMap": {"0": {}},
            "fnMap": {"0": {}},
            "s": {"0": 1},
            "b": {"0": [1, 1]},
            "f": {"0": 1},
        }
        node_lcov.append(
            f"TN:\nSF:{source_path}\nFN:1,choose\nFNDA:1,choose\n"
            "FNF:1\nFNH:1\nDA:1,1\nLF:1\nLH:1\n"
            "BRDA:1,0,0,1\nBRDA:1,0,1,1\nBRF:2\nBRH:2\nend_of_record\n"
        )
    payloads["artifacts/coverage/node-actions/lcov.info"] = "".join(node_lcov)
    payloads["artifacts/coverage/node-actions/coverage-final.json"] = json.dumps(
        node_records
    )
    go_paths = {
        "artifacts/coverage/go/gateway/coverage.out": ("services/gateway/main.go",),
        "artifacts/coverage/go/ws-hub/coverage.out": ("services/ws-hub/main.go",),
        "artifacts/coverage/go/file-processor/coverage.out": (
            "services/file-processor/main.go",
        ),
        "artifacts/coverage/go/shared/coverage.out": (
            "services/pkg/logging/logging.go",
            "services/pkg/spicedb/client.go",
        ),
    }
    for report_path, source_paths in go_paths.items():
        payloads[report_path] = "mode: count\n" + "".join(
            f"{source_path}:1.1,1.10 1 1\n" for source_path in source_paths
        )
        for source_path in source_paths:
            source = root / source_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("package main\n", encoding="utf-8")

    rust_components = {
        "rust-native": "native/rust_ext",
        "rust-wasm-sanitizer": "frontend/wasm-sanitizer",
        "rust-crypto": "frontend/rust-crypto",
    }
    for component, source_root in rust_components.items():
        stable_path = f"artifacts/coverage/rust/{component}/llvm.json"
        branch_path = f"artifacts/coverage/rust/{component}/branch-llvm.json"
        source_path = f"{source_root}/src/lib.rs"
        source = root / source_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("pub fn covered() {}\n", encoding="utf-8")
        stable = {
            "data": [
                {
                    "files": [
                        {
                            "filename": source_path,
                            "summary": {
                                "lines": {"count": 1, "covered": 1},
                                "functions": {"count": 1, "covered": 1},
                            },
                            "segments": [[1, 1, 1, True, True, False]],
                        }
                    ],
                    "totals": {
                        "lines": {"count": 1, "covered": 1},
                        "functions": {"count": 1, "covered": 1},
                    },
                }
            ]
        }
        branch = json.loads(json.dumps(stable))
        branch["data"][0]["files"][0]["summary"]["branches"] = {
            "count": 1,
            "covered": 1,
        }
        branch["data"][0]["totals"]["branches"] = {"count": 1, "covered": 1}
        payloads[stable_path] = json.dumps(stable)
        payloads[branch_path] = json.dumps(branch)

    for path, payload in payloads.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")


CANONICAL_REPORT_ARGUMENTS = (
    "--python-xml",
    "coverage.xml",
    "--python-json",
    "artifacts/coverage/python/coverage.json",
    "--frontend-lcov",
    "frontend/coverage/lcov.info",
    "--frontend-json",
    "frontend/coverage/coverage-final.json",
    "--node-actions-lcov",
    "artifacts/coverage/node-actions/lcov.info",
    "--node-actions-json",
    "artifacts/coverage/node-actions/coverage-final.json",
    "--go-report",
    "go-gateway=artifacts/coverage/go/gateway/coverage.out",
    "--go-report",
    "go-ws-hub=artifacts/coverage/go/ws-hub/coverage.out",
    "--go-report",
    "go-file-processor=artifacts/coverage/go/file-processor/coverage.out",
    "--go-report",
    "go-shared=artifacts/coverage/go/shared/coverage.out",
    "--rust-report",
    "rust-native=artifacts/coverage/rust/rust-native/llvm.json",
    "--rust-branch-report",
    "rust-native=artifacts/coverage/rust/rust-native/branch-llvm.json",
    "--rust-report",
    "rust-wasm-sanitizer=artifacts/coverage/rust/rust-wasm-sanitizer/llvm.json",
    "--rust-branch-report",
    "rust-wasm-sanitizer=artifacts/coverage/rust/rust-wasm-sanitizer/branch-llvm.json",
    "--rust-report",
    "rust-crypto=artifacts/coverage/rust/rust-crypto/llvm.json",
    "--rust-branch-report",
    "rust-crypto=artifacts/coverage/rust/rust-crypto/branch-llvm.json",
)

TOOL_VERSION_ARGUMENTS = (
    "--tool-version",
    "node-actions-node=24.11.0",
    "--tool-version",
    "ast-v8-to-istanbul=1.0.7",
    "--tool-version",
    "@babel/parser=8.0.8",
    "--tool-version",
    "@bcoe/v8-coverage=1.0.2",
    "--tool-version",
    "istanbul-lib-coverage=3.2.2",
    "--tool-version",
    "istanbul-lib-report=3.0.1",
    "--tool-version",
    "istanbul-reports=3.2.0",
    "--tool-version",
    "coverage.py=7.10.0",
    "--tool-version",
    "python=3.14.0",
    "--tool-version",
    "vitest=4.0.0",
    "--tool-version",
    "node=24.7.0",
    "--tool-version",
    "go=1.26.0",
    "--tool-version",
    "rustc=1.90.0",
    "--tool-version",
    "rustc-nightly=1.92.0-nightly",
    "--tool-version",
    "cargo-llvm-cov=0.9.1",
)


def _restore_public_integrity_digest(
    record: dict[str, object], field: str, width: int
) -> None:
    """Decode one explicitly named public Git or artifact digest, never arbitrary data."""
    if not isinstance(record, dict) or field in record:
        raise ValueError("historical fixture has an unexpected digest field")
    encoded = record.pop(f"{field}_bytes", None)
    if (
        not isinstance(encoded, list)
        or len(encoded) != width
        or any(type(value) is not int or not 0 <= value <= 255 for value in encoded)
    ):
        raise ValueError("historical public digest requires fixed-width byte integers")
    record[field] = bytes(encoded).hex()


def restore_historical_legacy_migration_policy(
    fixture: dict[str, object],
) -> dict[str, object]:
    """Reconstruct exactly the retired object from transparent public digest bytes."""
    policy = deepcopy(fixture)
    _restore_public_integrity_digest(policy, "base_sha", 20)
    evidence = policy["evidence"]
    _restore_public_integrity_digest(evidence, "tested_commit_sha", 20)
    _restore_public_integrity_digest(evidence, "source_head_sha", 20)
    shards = evidence["unit_shards"]
    if not isinstance(shards, list) or len(shards) != 4:
        raise ValueError("historical fixture requires exactly four evidence shards")
    for shard in shards:
        _restore_public_integrity_digest(shard, "coverage_sha256", 32)
        _restore_public_integrity_digest(shard, "provenance_sha256", 32)
    _restore_public_integrity_digest(evidence["migration"], "coverage_sha256", 32)
    _restore_public_integrity_digest(evidence["migration"], "provenance_sha256", 32)
    reports = evidence["reconstructed_reports"]
    _restore_public_integrity_digest(reports, "json_sha256", 32)
    _restore_public_integrity_digest(reports, "xml_sha256", 32)
    serialized = json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    # Original canonical policy SHA-256, represented as its 32 public digest bytes.
    # This is an independent immutable pin, not a scanner filter or an exception.
    expected_digest = bytes(
        (
            182,
            107,
            72,
            131,
            83,
            101,
            186,
            200,
            207,
            82,
            223,
            140,
            121,
            37,
            99,
            62,
            18,
            0,
            154,
            15,
            183,
            235,
            163,
            63,
            60,
            106,
            200,
            254,
            221,
            96,
            211,
            254,
        )
    )
    if hashlib.sha256(serialized.encode("utf-8")).digest() != expected_digest:
        raise ValueError("historical fixture differs from the immutable policy digest")
    return policy


def with_historical_legacy_migration_policy(
    contract: dict[str, object],
) -> dict[str, object]:
    """Attach the immutable retired policy only to an isolated test contract."""
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "quality"
        / "legacy-migration-baselines-ac74e915.json"
    )
    policy = restore_historical_legacy_migration_policy(
        json.loads(fixture.read_text(encoding="utf-8"))
    )
    historical = deepcopy(contract)
    historical["tier0"]["legacy_migration_baselines"] = policy
    return historical


def make_all_strict_synthetic_contract(
    contract: dict[str, object],
) -> dict[str, object]:
    """Copy a contract without any historical repository-bound migration waiver."""
    synthetic = deepcopy(contract)
    tier0 = synthetic.get("tier0")
    if isinstance(tier0, dict):
        tier0.pop("legacy_migration_baselines", None)
    return synthetic


def write_all_strict_synthetic_contract(source: Path, target: Path) -> None:
    """Write an isolated-repository contract with only strict coverage policy."""
    contract = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise ValueError("synthetic quality contract must be a JSON object")
    synthetic = make_all_strict_synthetic_contract(contract)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(synthetic), encoding="utf-8")
