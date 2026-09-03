import re
import subprocess
import sys

modules = [
    "services/gateway",
    "services/ws-hub",
    "services/file-processor",
    "services/cmd/uni-cli",
    "services/pkg/logging",
    "services/pkg/spiffe",
    "services/pkg/spicedb",
]

failures: list[str] = []

for m in modules:
    print(f"=== Testing module: {m} ===")
    res = subprocess.run(
        ["go", "test", "-cover", "./..."],  # noqa: S607
        cwd=m,
        capture_output=True,
        text=True,
    )
    print(res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)
    print(f"Exit code: {res.returncode}\n")
    if res.returncode != 0:
        failures.append(f"{m}: go test exited with {res.returncode}")
        continue
    coverage_values = [
        float(value)
        for value in re.findall(
            r"coverage:\s+(\d+(?:\.\d+)?)%\s+of\s+statements", res.stdout
        )
    ]
    if not coverage_values:
        failures.append(f"{m}: go test did not emit package coverage values")
        continue
    for value in coverage_values:
        if value < 100.0:
            failures.append(
                f"{m}: package coverage {value:.1f}% is below the 100% contract"
            )

if failures:
    print("Go quality verification failed:", file=sys.stderr)
    print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
    raise SystemExit(1)
