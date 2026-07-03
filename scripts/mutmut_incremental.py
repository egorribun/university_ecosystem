import subprocess
import sys
from collections.abc import Sequence
from shutil import which

from defusedxml import ElementTree as ET


def resolve_executable(name: str) -> str:
    executable = which(name)
    if executable is None:
        print(f"Required executable not found on PATH: {name}")
        sys.exit(1)
    return executable


GIT = resolve_executable("git")
MUTMUT = resolve_executable("mutmut")


def run_command(
    args: Sequence[str], **kwargs: object
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, **kwargs)  # noqa: S603 - args use resolved allowlisted executables, shell=False.


def get_changed_files():
    # Try to compare with origin/main, then main, then HEAD~1 as fallback
    for target in ["origin/main", "main", "HEAD~1"]:
        try:
            res = run_command(
                [GIT, "diff", "--name-only", target],
                capture_output=True,
                text=True,
                check=True,
            )
            files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
            # If we succeed and get files (even empty list if no changes), return them
            return files
        except subprocess.CalledProcessError:
            continue
    # Fallback to local git diff against HEAD
    try:
        res = run_command(
            [GIT, "diff", "--name-only"], capture_output=True, text=True, check=True
        )
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return []


def main():
    changed_files = get_changed_files()
    py_files = [
        f
        for f in changed_files
        if f.startswith("app/") and f.endswith(".py") and "tests/" not in f
    ]

    if not py_files:
        print("No changed Python files found in app/. Skipping mutation testing.")
        sys.exit(0)

    paths_arg = ",".join(py_files)
    print(f"Running mutmut for modified files: {paths_arg}")

    # Run mutmut
    run_command([MUTMUT, "run", f"--paths-to-mutate={paths_arg}"], check=False)

    # Generate and parse junit report
    print("Generating mutation report...")
    junit_res = run_command(
        [MUTMUT, "junit"], capture_output=True, text=True, check=False
    )

    if junit_res.returncode != 0:
        print("Failed to run 'mutmut junit'. Output:")
        print(junit_res.stderr)
        sys.exit(1)

    try:
        root = ET.fromstring(junit_res.stdout)
        tests = int(root.get("tests", 0))
        failures = int(root.get("failures", 0))
        errors = int(root.get("errors", 0))

        if tests == 0:
            print("No mutations were generated.")
            sys.exit(0)

        killed = tests - failures - errors
        score = killed / tests

        print("\n=== Mutation Testing Summary ===")
        print(f"Total Mutants: {tests}")
        print(f"Killed:        {killed}")
        print(f"Survived:      {failures}")
        print(f"Errors:        {errors}")
        print(f"Mutation Score: {score:.2%}")
        print("================================\n")

        if score < 0.80:
            print("ERROR: Mutation score is below the required 80% threshold!")
            sys.exit(1)
        else:
            print("SUCCESS: Mutation score meets the 80% threshold.")
            sys.exit(0)
    except Exception as e:
        print(f"Error parsing junit XML: {e}")
        print("Raw XML output:")
        print(junit_res.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
