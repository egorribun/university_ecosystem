#!/usr/bin/env python3
"""Run diff-based mutation testing using mutmut and diff-cover.

Only runs on non-Windows platforms (since mutmut is POSIX-only).
On Windows, it exits gracefully with code 0.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if sys.platform == "win32":
        print(
            "Mutation testing (mutmut) is not natively supported on Windows. Skipping run."
        )
        return 0

    print("Fetching modified files compared to origin/main...")
    # Get list of modified files compared to origin/main
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", "origin/main"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to run git diff: {e}")
        print(f"Stderr: {e.stderr}")
        return 1

    modified_files = [
        line.strip()
        for line in res.stdout.splitlines()
        if line.strip().startswith("app/") and line.strip().endswith(".py")
    ]

    if not modified_files:
        print(
            "No modified Python source files in 'app/' found relative to origin/main. Skipping mutation testing."
        )
        return 0

    print(
        f"Found {len(modified_files)} modified Python files: {', '.join(modified_files)}"
    )

    # 1. Run mutmut run on modified files
    paths_arg = ",".join(modified_files)
    cmd_mutmut = ["mutmut", "run", f"--paths-to-mutate={paths_arg}"]
    print(f"Executing: {' '.join(cmd_mutmut)}")

    try:
        # Note: mutmut run exits with code 0 even if there are surviving mutants.
        # We allow it to run and output stats.
        subprocess.run(cmd_mutmut, check=True)
    except subprocess.CalledProcessError as e:
        print(f"mutmut run failed: {e}")
        return e.returncode

    # 2. Export JUnit XML report from mutmut
    cmd_xml = ["mutmut", "xml"]
    print("Generating mutmut.xml report...")
    try:
        subprocess.run(cmd_xml, check=True)
    except subprocess.CalledProcessError as e:
        print(f"mutmut xml export failed: {e}")
        return e.returncode

    # 3. Use diff-cover to gate mutation score (fail if under 85%)
    cmd_diff_cover = [
        "diff-cover",
        "mutmut.xml",
        "--compare-branch=origin/main",
        "--fail-under=85",
    ]
    print(f"Executing: {' '.join(cmd_diff_cover)}")
    res_diff = subprocess.run(cmd_diff_cover)
    return res_diff.returncode


if __name__ == "__main__":
    sys.exit(main())
