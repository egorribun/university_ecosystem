import subprocess
import sys

# Budget configuration: since we've reached 100% type safety,
# the budget for total errors is now 0.
ERROR_BUDGET = 0


def main():
    print(f"Checking Mypy error budget (Budget: {ERROR_BUDGET})...")

    import shutil

    uv_path = shutil.which("uv") or "uv"
    # Run mypy on the app directory
    result = subprocess.run(  # noqa: S603  # trusted static args, no shell=True
        [uv_path, "run", "mypy", "app", "--no-error-summary", "--hide-error-context"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    # Mypy output lines represent errors (one per line usually)
    # Filter for lines that actually look like errors
    errors = [line for line in result.stdout.splitlines() if ": error:" in line]
    error_count = len(errors)

    if error_count > ERROR_BUDGET:
        print("[FAIL] Mypy budget exceeded!")
        print(f"Current errors: {error_count}")
        print(f"Budget: {ERROR_BUDGET}")
        print("\nErrors found:")
        for error in errors:
            print(f"  {error}")
        sys.exit(1)

    print(
        f"[PASS] Mypy budget check passed (Current: {error_count}, Budget: {ERROR_BUDGET})"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
