import subprocess

modules = [
    "services/gateway",
    "services/ws-hub",
    "services/file-processor",
    "services/cmd/uni-cli",
    "services/pkg/spiffe",
    "services",
]

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
