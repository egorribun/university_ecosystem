from __future__ import annotations

import json
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
    go_paths = {
        "artifacts/coverage/go/gateway/coverage.out": "services/gateway/main.go",
        "artifacts/coverage/go/ws-hub/coverage.out": "services/ws-hub/main.go",
        "artifacts/coverage/go/file-processor/coverage.out": (
            "services/file-processor/main.go"
        ),
        "artifacts/coverage/go/shared/coverage.out": ("services/pkg/spicedb/client.go"),
    }
    for report_path, source_path in go_paths.items():
        payloads[report_path] = f"mode: count\n{source_path}:1.1,1.10 1 1\n"
        source = root / source_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("package main\n", encoding="utf-8")

    rust_components = {
        "rust-native": "native/rust_ext",
        "rust-pyo3-sanitizer": "crates/pyo3-sanitizer",
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
    "rust-pyo3-sanitizer=artifacts/coverage/rust/rust-pyo3-sanitizer/llvm.json",
    "--rust-branch-report",
    "rust-pyo3-sanitizer=artifacts/coverage/rust/rust-pyo3-sanitizer/branch-llvm.json",
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
    "cargo-llvm-cov=0.6.19",
)
