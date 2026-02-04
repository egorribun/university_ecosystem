"""Dagger CI/CD Pipeline Definition (2026 Modernization Proposal).

This script uses the Dagger Python SDK to define a repeatable, containerized
CI/CD pipeline that runs identically on local dev machines and in GitHub Actions.
"""

import sys

import anyio
import dagger


async def pipeline():
    async with dagger.Connection(dagger.Config(log_output=sys.stdout)) as client:
        # 1. Pipeline context: project Root
        src = client.host().directory(".")

        # 2. Python Build & Test Stage
        python_container = (
            client.container()
            .from_("ghcr.io/astral-sh/uv:python3.13-bookworm-slim")
            .with_directory("/src", src)
            .with_workdir("/src")
            .with_exec(["uv", "lock", "--check"])
            .with_exec(["uv", "sync", "--frozen"])
        )

        # Run Python Tests
        test_results = await python_container.with_exec(
            ["uv", "run", "pytest", "tests"]
        ).stdout()
        print(f"Python Test Results:\n{test_results}")

        # 3. Go Build Stage (Gateway)
        go_container = (
            client.container()
            .from_("golang:1.24-alpine")  # Using latest Go (2026)
            .with_directory("/src", src)
            .with_workdir("/src/services/gateway")
            .with_exec(["go", "build", "-o", "gateway", "./cmd/gateway"])
        )

        # Verify Go Build
        await go_container.with_exec(["./gateway", "--help"]).stdout()
        print("Go Gateway Build Verified")

        # 4. Security Scan Stage (TruffleHog)
        trufflehog = (
            client.container()
            .from_("trufflesecurity/trufflehog:latest")
            .with_directory("/src", src)
            .with_exec(["trufflehog", "filesystem", "/src", "--fail"])
        )
        await trufflehog.exit_code()
        print("Security Scan Passed")


if __name__ == "__main__":
    anyio.run(pipeline)
