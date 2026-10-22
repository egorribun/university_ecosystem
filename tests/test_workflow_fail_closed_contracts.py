"""Fail-closed contracts for active GitHub Actions workflows."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import tomllib
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from shutil import which
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
PRE_COMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
LOCKED_PRE_COMMIT_VERSION = "4.6.2"
HELM_4_2_4_LINUX_AMD64_SHA256 = "c306b46f719b0a4da32d0f78ee21bf90ce8d602f15b22ab753f0674d1670a7f3"  # public Helm release checksum
DEPLOY_SMOKE_REQUIREMENTS = {
    "requests==2.34.2": "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
    "certifi==2026.7.22": "62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775",
    "charset-normalizer==3.5.2": "34276fd796040bf0993ab33a369aa572e6979c7aab225a88893667ad8eac8f7a",
    "idna==3.20": "ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c",
    "urllib3==2.8.0": "0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3",
}

EXPECTED_EXTERNAL_IMAGES = {
    "pgvector/pgvector:pg17": (
        "pgvector/pgvector:pg17@sha256:"
        "ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
    ),
    "redis:7-alpine": (
        "redis:7-alpine@sha256:"
        "e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"  # pragma: allowlist secret
    ),
    "nats:2.15.0-alpine": (
        "nats:2.15.0-alpine@sha256:"
        "ac8f88a6494bffc2c2a5289a0ca61cb28a9145c11ba5677cf24265d07f46d8d4"
    ),
    "ghcr.io/chrislusf/seaweedfs:4.48": (
        "ghcr.io/chrislusf/seaweedfs:4.48@sha256:"
        "4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d"
    ),
    "ghcr.io/shopify/toxiproxy:2.12.0": (
        "ghcr.io/shopify/toxiproxy:2.12.0@sha256:"
        "9378ed52a28bc50edc1350f936f518f31fa95f0d15917d6eb40b8e376d1a214e"
    ),
    "stoplight/spectral:6.17.0": (
        "stoplight/spectral:6.17.0@sha256:"
        "c8ffae6ee561b70e80402f1ea669e8b37c74fee48a3dbe2147b71359ed987239"
    ),
    "alpine/socat:1.8.0.3": (
        "alpine/socat:1.8.0.3@sha256:"
        "beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e"  # pragma: allowlist secret
    ),
    "postgres:15-alpine": (
        "postgres:15-alpine@sha256:"
        "fe0737ba566a2c5b2a28f34433c0a423261900ec17b9bf7ad115e1aae7e57f1b"  # pragma: allowlist secret
    ),
}

PRECOMMIT_SEMGREP_IMAGE = (
    "semgrep/semgrep:1.179.0@sha256:"
    "93963d9295a366f59e4850127b1550400ee7b388f04fe144e4a1f6325d96e01b"
)

_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_SHELL_ASSIGNMENT = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\n]*)$"
)
_SHELL_VARIABLE_REFERENCE = re.compile(
    r"^\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$"
)
_POWERSHELL_ASSIGNMENT_START = re.compile(
    r"(?im)^[ \t]*\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*(?P<operator>\+=|-=|\*=|/=|%=|=)"
)
_POWERSHELL_LITERAL_ARRAY = re.compile(
    r"(?ims)^[ \t]*\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*@\([ \t]*"
    r"(?P<items>.*?)^[ \t]*\)[ \t]*$"
)
_POWERSHELL_FOREACH = re.compile(
    r"(?im)^[ \t]*foreach[ \t]*\([ \t]*\$(?P<item>[A-Za-z_][A-Za-z0-9_]*)"
    r"[ \t]+in[ \t]+\$(?P<array>[A-Za-z_][A-Za-z0-9_]*)[ \t]*\)[ \t]*\{"
)
_POWERSHELL_DOCKER_PULL = re.compile(
    r"(?im)^[ \t]*docker[ \t]+pull[ \t]+\$(?P<item>[A-Za-z_][A-Za-z0-9_]*)"
)
_DOCKER_RUN_OPTIONS_WITH_VALUE = {
    "--add-host",
    "--cidfile",
    "--cpus",
    "--entrypoint",
    "--env",
    "--env-file",
    "--hostname",
    "--label",
    "--memory",
    "--mount",
    "--name",
    "--network",
    "--pids-limit",
    "--platform",
    "--publish",
    "--tmpfs",
    "--user",
    "--volume",
    "--workdir",
    "-e",
    "-h",
    "-l",
    "-p",
    "-u",
    "-v",
    "-w",
}


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _scalars(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _scalars(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _scalars(nested)


def _image_values(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"image", "container"} and isinstance(nested, str):
                yield nested
            yield from _image_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _image_values(nested)


def _docker_cli_images(script: str) -> Iterator[str]:
    """Extract Docker image arguments, resolving simple earlier assignments.

    Dynamic shell expressions remain unresolved; this parser is deliberately
    limited to the command forms used by workflow run scalars.
    """

    flattened = script.replace("\\\n", " ")
    assignments = iter(_SHELL_ASSIGNMENT.finditer(flattened))
    next_assignment = next(assignments, None)
    bindings: dict[str, str] = {}

    for match in re.finditer(r"\bdocker\s+(run|create|pull)\s+([^\n]+)", flattened):
        while next_assignment is not None and next_assignment.start() < match.start():
            name = next_assignment.group("name")
            try:
                value_tokens = shlex.split(
                    next_assignment.group("value"), comments=True, posix=True
                )
            except ValueError:
                value_tokens = []

            if len(value_tokens) == 1 and not any(
                char in value_tokens[0] for char in ("$", "`", "\\")
            ):
                bindings[name] = value_tokens[0]
            else:
                # A dynamic or malformed reassignment must clear an older
                # literal binding rather than make that old value look live.
                bindings.pop(name, None)
            next_assignment = next(assignments, None)

        command, remainder = match.groups()
        tokens = shlex.split(remainder, comments=True, posix=True)
        if command == "pull":
            index = 0
            while index < len(tokens) and tokens[index].startswith("-"):
                option = tokens[index].split("=", 1)[0]
                if "=" not in tokens[index] and option == "--platform":
                    index += 2
                else:
                    index += 1
            if index < len(tokens):
                yield _resolve_shell_image_reference(tokens[index], bindings)
            continue

        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.startswith("-"):
                option = token.split("=", 1)[0]
                if "=" not in token and option in _DOCKER_RUN_OPTIONS_WITH_VALUE:
                    index += 2
                else:
                    index += 1
                continue
            yield _resolve_shell_image_reference(token, bindings)
            break


def _resolve_shell_image_reference(token: str, bindings: dict[str, str]) -> str:
    variable_match = _SHELL_VARIABLE_REFERENCE.fullmatch(token)
    if variable_match is None:
        return token
    name = variable_match.group("braced") or variable_match.group("plain")
    return bindings.get(name, token)


def _powershell_block_end(script: str, opening_brace: int) -> int | None:
    depth = 0
    quote: str | None = None
    index = opening_brace
    while index < len(script):
        character = script[index]
        if quote == "'":
            if character == "'":
                if index + 1 < len(script) and script[index + 1] == "'":
                    index += 2
                    continue
                quote = None
        elif quote == '"':
            if character == "`":
                index += 2
                continue
            if character == '"':
                quote = None
        elif character == "#":
            newline = script.find("\n", index)
            if newline < 0:
                return None
            index = newline + 1
            continue
        elif character == "`":
            index += 2
            continue
        elif character in {"'", '"'}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _powershell_literal_array_items(items: str) -> list[str] | None:
    result: list[str] = []
    for line in items.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.endswith(","):
            value = value[:-1].rstrip()
        if len(value) < 2 or value[0] not in {"'", '"'} or value[-1] != value[0]:
            return None
        content = value[1:-1]
        if value[0] == '"' and ("`" in content or '"' in content):
            return None
        if value[0] == "'" and "'" in content:
            return None
        result.append(content)
    return result


def _powershell_cli_images(script: str) -> Iterator[str]:
    """Resolve image literals from a simple PowerShell array consumed by pull."""
    assignments = list(_POWERSHELL_ASSIGNMENT_START.finditer(script))
    arrays = list(_POWERSHELL_LITERAL_ARRAY.finditer(script))
    for loop in _POWERSHELL_FOREACH.finditer(script):
        array_name = loop.group("array").casefold()
        item_name = loop.group("item").casefold()
        block_end = _powershell_block_end(script, loop.end() - 1)
        body = script[loop.end() : block_end if block_end is not None else len(script)]
        if not any(
            pull.group("item").casefold() == item_name
            for pull in _POWERSHELL_DOCKER_PULL.finditer(body)
        ):
            continue

        prior_assignments = [
            assignment
            for assignment in assignments
            if assignment.start() < loop.start()
            and assignment.group("name").casefold() == array_name
        ]
        if not prior_assignments:
            continue
        latest_assignment = prior_assignments[-1]
        literal_array = next(
            (
                array
                for array in arrays
                if array.start() == latest_assignment.start()
                and array.group("name").casefold() == array_name
            ),
            None,
        )
        if literal_array is None:
            earlier_literal_arrays = [
                array
                for array in arrays
                if array.start() < latest_assignment.start()
                and array.group("name").casefold() == array_name
            ]
            if earlier_literal_arrays and latest_assignment.group("operator") != "=":
                yield "<modified PowerShell image array>"
            continue
        parsed_items = _powershell_literal_array_items(literal_array.group("items"))
        if parsed_items is None:
            yield "<unparsed PowerShell image array>"
        else:
            yield from parsed_items


def _assert_pinned(ref: str, *, source: str) -> None:
    if "$" in ref:
        return
    assert _DIGEST.search(ref), f"unpinned static image {ref!r} in {source}"


def _configured_precommit_hook_ids() -> Counter[str]:
    """Return default-stage hook occurrences; identical ids may have variants."""

    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    hook_ids: Counter[str] = Counter()
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            stages = hook.get("stages")
            if stages == ["manual"]:
                continue
            hook_ids[hook["id"]] += 1
    return hook_ids


def _locked_pre_commit_version() -> str:
    """Read the exact runner version from the authoritative project lock."""

    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    versions = [
        package["version"]
        for package in lock["package"]
        if package["name"] == "pre-commit"
    ]
    assert versions == [LOCKED_PRE_COMMIT_VERSION]
    return versions[0]


def _workflow_precommit_hook_ids(job: dict[str, Any]) -> list[str]:
    """Extract explicit hook ids from the CI split without accepting all-files."""

    hook_ids: list[str] = []
    for step in job["steps"]:
        if "with" in step and "extra_args" in step["with"]:
            args = shlex.split(step["with"]["extra_args"])
            assert args and args[0] != "--all-files"
            hook_ids.append(args[0])
        if "run" in step:
            hook_ids.extend(
                re.findall(
                    r"(?:^|\n)\s*pre-commit run ([a-z0-9][a-z0-9-]*) --all-files",
                    step["run"],
                )
            )
    return hook_ids


def test_precommit_split_preserves_every_nonmanual_hook_and_fails_closed() -> None:
    workflow = _workflow(CI)
    jobs = workflow["jobs"]
    assert "pre-commit-autofix" not in jobs

    fast_job = jobs["pre-commit-check"]
    security_types_job = jobs["pre-commit-security-and-types"]
    for job in (fast_job, security_types_job):
        assert job["permissions"] == {"contents": "read"}
        assert "outputs" not in job
        assert "continue-on-error" not in job
        assert job["timeout-minutes"] == 15

    checkout = next(
        step
        for step in fast_job["steps"]
        if "actions/checkout@" in step.get("uses", "")
    )
    assert checkout["with"]["persist-credentials"] is False
    security_checkout = next(
        step
        for step in security_types_job["steps"]
        if "actions/checkout@" in step.get("uses", "")
    )
    assert security_checkout["with"]["persist-credentials"] is False

    assert "needs" not in security_types_job
    assert "if" not in security_types_job

    # The pinned Docker-backed Semgrep hook remains a local pre-commit hook.
    # CI must not duplicate it as a blocking workflow job. All other
    # default-stage hooks must be run exactly once by the split, preventing an
    # accidental all-files fallback or a quiet drop of detect-secrets / mypy.
    configured_hook_ids = _configured_precommit_hook_ids()
    expected_hook_ids = set(configured_hook_ids) - {"semgrep-docker"}
    actual_hook_ids = _workflow_precommit_hook_ids(fast_job) + (
        _workflow_precommit_hook_ids(security_types_job)
    )
    assert Counter(actual_hook_ids) == Counter(
        {hook_id: 1 for hook_id in expected_hook_ids}
    )

    # `pre-commit run ruff` selects every default-stage configuration with the
    # matching id. The config deliberately has two active Ruff variants, so
    # one selector is required and sufficient; adding a second selector would
    # run both variants twice.
    assert configured_hook_ids["ruff"] == 2
    assert actual_hook_ids.count("ruff") == 1

    # The pre-commit runner is an isolated, exact-pinned dependency group.  It
    # avoids synchronizing the complete application dev environment in each
    # lightweight job while still exporting every locked transitive wheel with
    # hashes.  Runtime verification makes a substituted executable fail closed
    # before any PR-controlled hook can execute.
    locked_pre_commit_version = _locked_pre_commit_version()
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert pyproject["dependency-groups"]["ci-precommit-runner"] == [
        f"pre-commit=={locked_pre_commit_version}"
    ]
    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    project_package = next(
        package
        for package in lock["package"]
        if package["name"] == "university-ecosystem"
    )
    assert project_package["dev-dependencies"]["ci-precommit-runner"] == [
        {"name": "pre-commit"}
    ]
    assert project_package["metadata"]["requires-dev"]["ci-precommit-runner"] == [
        {"name": "pre-commit", "specifier": f"=={locked_pre_commit_version}"}
    ]
    for job in (fast_job, security_types_job):
        assert any(
            step.get("uses", "").startswith("astral-sh/setup-uv@")
            for step in job["steps"]
        )
        installer = _step(job, "Install hash-verified pre-commit runner")
        install = installer["run"]
        assert "uv export --frozen" in install
        assert "--only-group ci-precommit-runner" in install
        assert "--no-emit-project" in install
        assert "--no-emit-workspace" in install
        assert "--format requirements-txt" in install
        assert '"$RUNNER_TEMP/ci-precommit.requirements.txt"' in install
        assert "--require-hashes" in install
        assert "--only-binary=:all:" in install
        assert "--no-deps" in install
        assert "--force-reinstall" in install
        assert '-r "$requirements_file"' in install
        assert "--no-hashes" not in install
        assert "tomllib.load" not in install
        assert '"pre-commit==$LOCKED_PRE_COMMIT_VERSION"' not in install
        assert (
            'test "$(pre-commit --version)" = '
            f'"pre-commit {locked_pre_commit_version}"' in install
        )

    security_hook = _step(security_types_job, "Run security and type pre-commit hooks")
    assert "detect-secrets" in security_hook["run"]
    assert "mypy" in security_hook["run"]
    assert "set -euo pipefail" in security_hook["run"]
    assert 'exit "$failed"' in security_hook["run"]
    # The two hooks are read-only with respect to the checkout (detect-secrets
    # only canonicalizes its baseline, while mypy writes an isolated cache),
    # so run them concurrently.  Keep explicit PID/wait handling so a failure
    # from either hook remains blocking instead of being lost in a background
    # shell process.
    assert (
        "pre-commit run detect-secrets --all-files --show-diff-on-failure &\n"
        in (security_hook["run"])
    )
    assert (
        "pre-commit run mypy --all-files --show-diff-on-failure &\n"
        in (security_hook["run"])
    )
    assert "detect_secrets_pid=$!" in security_hook["run"]
    assert "mypy_pid=$!" in security_hook["run"]
    assert 'wait "$detect_secrets_pid" || failed=1' in security_hook["run"]
    assert 'wait "$mypy_pid" || failed=1' in security_hook["run"]
    assert "continue-on-error" not in security_hook

    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    detect_secrets = next(
        hook
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook["id"] == "detect-secrets"
    )
    assert detect_secrets["entry"] == "python -X utf8 scripts/run_detect_secrets.py"
    assert detect_secrets["args"] == ["--baseline", ".secrets.baseline"]
    mypy_hook = next(
        hook
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook["id"] == "mypy"
    )
    # The local hook must cover the same deployable application tree as CI;
    # narrowing it to selected packages leaves models, schemas, utils and
    # application entrypoints unchecked until a remote run.
    assert mypy_hook["files"] == r"^app/"

    ci_success = jobs["ci-success"]
    assert "pre-commit-security-and-types" in ci_success["needs"]
    result_gate = _step(ci_success, "Check all jobs passed")["run"]
    assert (
        '"pre-commit-security-and-types|${{ needs.pre-commit-security-and-types.result }}"'
        in result_gate
    )


def test_semgrep_security_audit_starts_independently() -> None:
    workflow = _workflow(CI)
    jobs = workflow["jobs"]
    job = jobs["security-audit"]

    # The reusable security workflow remains an independent required gate
    # for its remaining scanners. It must not depend on the pre-commit job,
    # and ci-success must continue to fail closed on security-audit's result.
    assert "needs" not in job
    assert job["uses"] == "./.github/workflows/reusable-security-audit.yml"
    assert "security-audit" in jobs["ci-success"]["needs"]
    gate = jobs["ci-success"]["steps"][0]["run"]
    assert '"security-audit|${{ needs.security-audit.result }}"' in gate


def test_mutation_matrix_publishes_bounded_capacity_telemetry() -> None:
    """Mutation capacity remains scheduled/manual and keeps its exact shards."""

    ci_jobs = _workflow(CI)["jobs"]
    nightly_jobs = _workflow(WORKFLOWS / "nightly-full-gate.yml")["jobs"]
    manual_jobs = _workflow(WORKFLOWS / "manual-mutation-evidence.yml")["jobs"]
    backend_jobs = _workflow(WORKFLOWS / "reusable-full-backend-mutation.yml")["jobs"]

    assert not any("mutation" in job_id or "stryker" in job_id for job_id in ci_jobs)
    assert (
        "mutation"
        not in _step(ci_jobs["ci-success"], "Check all jobs passed")["run"].lower()
    )
    assert nightly_jobs["mutation-tests-full"]["uses"] == (
        "./.github/workflows/reusable-full-backend-mutation.yml"
    )
    assert backend_jobs["mutation-tests-full"]["strategy"]["matrix"]["shard"] == list(
        range(1, 129)
    )
    assert backend_jobs["mutation-tests-full"]["strategy"]["max-parallel"] == 8
    assert manual_jobs["manual-mutation-stats"]["strategy"]["matrix"][
        "stats_shard"
    ] == list(range(8))
    assert manual_jobs["manual-mutation-tests"]["strategy"]["matrix"]["shard"] == list(
        range(1, 129)
    )
    assert manual_jobs["manual-mutation-tests"]["strategy"]["max-parallel"] == 20
    nightly_stryker = nightly_jobs["frontend-mutation-shards"]
    assert nightly_stryker["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert nightly_stryker["strategy"]["max-parallel"] == 8


def test_incremental_mutmut_planner_uses_validator_budget_contract() -> None:
    jobs = _workflow(WORKFLOWS / "manual-mutation-evidence.yml")["jobs"]
    plan_step = _step(
        jobs["manual-mutation-tests"],
        "Run manual incremental mutmut (blocking, stats-derived budget)",
    )
    script = plan_step["run"]

    assert "scripts/plan_mutmut_shards.py" in script
    assert "--num-shards 128" in script
    assert "--max-children 3" in script
    assert "--control-cycle-reserve-seconds 5" in script
    assert "--metadata-startup-reserve-seconds 120" in script
    assert "--max-timeout-seconds 20970" in script
    assert "--output /tmp/mutmut-shard.txt" in script


def test_mutation_scope_diff_failures_cannot_look_like_empty_changes() -> None:
    workflows = (
        _workflow(CI),
        _workflow(WORKFLOWS / "manual-mutation-evidence.yml"),
    )
    scope_scripts = [
        step["run"]
        for workflow in workflows
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name")
        in {
            "Detect changed Python source",
            "Resolve changed Python scope",
            "Resolve manual mutation comparison base",
        }
    ]

    assert len(scope_scripts) == 2
    assert not any("mutation-scope" in job_id for job_id in workflows[0]["jobs"])
    for script in scope_scripts:
        assert "git diff --name-only" in script
        assert 'git diff --name-only "$COMPARE_BASE...HEAD" | grep' not in script
        assert "grep -E '^app/.*\\.py$'" in script


def test_k6_job_does_not_fake_connectivity_to_an_absent_target() -> None:
    job = _workflow(CI)["jobs"]["ws-stress-test"]
    scripts = "\n".join(step.get("run", "") for step in job["steps"])

    assert job["name"] == "WebSocket 10k Scenario Validation (advisory)"
    assert "k6 inspect" in scripts
    assert "k6 run" not in scripts
    assert not any(step.get("continue-on-error") for step in job["steps"])


def test_ci_success_only_allows_skips_for_explicit_event_guards() -> None:
    job = _workflow(CI)["jobs"]["ci-success"]
    check_step = _step(job, "Check all jobs passed")
    gate = check_step["run"]

    assert check_step["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "EVENT_REF": "${{ github.ref }}",
        "PRE_COMMIT_RESULT": "${{ needs.pre-commit-check.result }}",
        "PRE_COMMIT_SECURITY_RESULT": "${{ needs.pre-commit-security-and-types.result }}",
        "FRONTEND_TESTS_RESULT": "${{ needs.frontend-tests.result }}",
        "BACKEND_TESTS_RESULT": "${{ needs.backend-tests.result }}",
        "GO_TESTS_RESULT": "${{ needs.go-tests.result }}",
        "RUST_TESTS_RESULT": "${{ needs.rust-tests.result }}",
        "BACKEND_TYPE_CHECK_RESULT": "${{ needs.backend-type-check.result }}",
        "COVERAGE_RESULT": "${{ needs.coverage-policy-gate.result }}",
    }
    assert "required_results=(" in gate
    assert 'if [[ "$result" != "$expected_result" ]]' in gate
    assert 'if [[ "$job" == "coverage-policy-gate" ]]; then' in gate
    assert 'expected_result="$coverage_expected_result"' in gate
    assert '"coverage-policy-gate|$COVERAGE_RESULT"' in gate
    assert 'assert_event_result "codecov-upload"' in gate
    assert '"sbom-generate|${{ needs.sbom-generate.result }}"' in gate
    assert '"db-migration-integrity|${{ needs.db-migration-integrity.result }}"' in gate
    assert '"security-audit|${{ needs.security-audit.result }}"' in gate
    assert not any(
        token in gate.lower()
        for token in ("mutation", "stryker", "schemathesis", "chaos", "cross-browser")
    )
    assert all(
        deferred not in job["needs"]
        for deferred in (
            "mutation-scope",
            "mutation-tests-stats",
            "mutation-tests-universe",
            "mutation-tests-incremental",
            "stryker-preflight",
            "stryker-shards",
            "e2e-tests-cross-browser",
            "schemathesis-api-tests",
            "chaos-tests",
        )
    )


def test_ci_success_allows_coverage_skip_only_after_producer_failure() -> None:
    """A dependency skip is expected only for a failed coverage producer.

    The aggregate coverage job is dependency-gated, so a backend/frontend/Go/
    Rust failure naturally makes it ``skipped``.  The finalizer must model that
    narrow, known state while rejecting a skipped gate when all producers are
    green (or when a producer was cancelled unexpectedly).
    """

    job = _workflow(CI)["jobs"]["ci-success"]
    gate = _step(job, "Check all jobs passed")["run"]

    assert "coverage_expected_result=success" in gate
    assert "for prerequisite in" in gate
    for prerequisite in (
        '"$BACKEND_TESTS_RESULT"',
        '"$FRONTEND_TESTS_RESULT"',
        '"$GO_TESTS_RESULT"',
        '"$RUST_TESTS_RESULT"',
    ):
        assert prerequisite in gate
    assert '"$RUST_TESTS_RESULT"; do' in gate
    assert (
        'if [[ "$prerequisite" == "failure" || "$prerequisite" == "skipped" ]]; then'
        in gate
    )
    assert "coverage_expected_result=skipped" in gate
    assert 'expected_result="$coverage_expected_result"' in gate
    assert '"coverage-policy-gate|$COVERAGE_RESULT"' in gate

    # The special case must not turn an arbitrary skipped result into success:
    # only the explicit producer states above may select ``skipped``.
    assert 'if [[ "$prerequisite" == "cancelled"' not in gate


def test_ci_success_models_dependency_gated_chaos_results_fail_closed() -> None:
    """Deferred chaos evidence stays fail-closed without blocking PR CI."""

    ci_jobs = _workflow(CI)["jobs"]
    ci_gate = _step(ci_jobs["ci-success"], "Check all jobs passed")["run"]
    nightly = _workflow(WORKFLOWS / "nightly-full-gate.yml")
    nightly_jobs = nightly["jobs"]

    assert "chaos-tests" not in ci_jobs
    assert "chaos-loadtest-orchestrator" not in ci_jobs
    assert "chaos" not in ci_gate.lower()
    for job_name in ("chaos-tests", "chaos-loadtest-orchestrator", "load-and-chaos"):
        assert nightly_jobs[job_name]["if"] == "${{ github.ref == 'refs/heads/main' }}"
        assert job_name in nightly_jobs["notify-failure"]["needs"]


def test_stryker_preflight_candidates_are_retry_safe_and_fail_closed() -> None:
    nightly = _workflow(WORKFLOWS / "nightly-full-gate.yml")
    jobs = nightly["jobs"]
    preflight = jobs["frontend-mutation-preflight"]
    shards = jobs["frontend-mutation-shards"]
    aggregate = jobs["frontend-mutation-tests-full"]
    roundtrip = jobs["frontend-mutation-roundtrip"]

    assert preflight["if"] == "${{ github.ref == 'refs/heads/main' }}"
    upload = _step(preflight, "Upload immutable Stryker preflight")
    assert upload["with"]["name"] == (
        "frontend-mutation-preflight-${{ github.run_id }}-"
        "${{ github.run_attempt }}-${{ github.sha }}"
    )
    assert upload["with"]["retention-days"] == 30
    assert shards["needs"] == "frontend-mutation-preflight"
    assert shards["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert shards["strategy"]["max-parallel"] == 8
    assert aggregate["needs"] == [
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
    ]
    download = _step(
        aggregate, "Download all nightly frontend mutation shards from same run"
    )
    assert download["with"] == {
        "pattern": "nightly-frontend-mutation-shard-${{ github.run_id }}-*",
        "path": "frontend/reports/mutation/external",
        "merge-multiple": False,
    }
    verify = _step(aggregate, "Aggregate and verify nightly frontend mutation evidence")
    assert "npm run test:mutation:verify" in verify["run"]
    assert roundtrip["needs"] == "frontend-mutation-tests-full"
    assert any(
        step.get("name") == "Re-verify downloaded nightly frontend mutation evidence"
        for step in roundtrip["steps"]
    )

    manual = _workflow(WORKFLOWS / "manual-mutation-evidence.yml")["jobs"]
    assert manual["manual-frontend-mutation-aggregate"]["needs"] == [
        "manual-frontend-mutation-preflight",
        "manual-frontend-mutation-shards",
    ]


def test_download_artifact_uses_only_supported_fail_closed_inputs() -> None:
    """The v8 action has no ``if-no-artifact-found`` input.

    Missing-artifact handling belongs to an explicit selector or shell guard;
    passing an unknown action input merely emits a warning and silently weakens
    the transport contract.  Keep this invariant repository-wide so a new
    workflow cannot reintroduce the typo.
    """

    for workflow_path in sorted(WORKFLOWS.glob("*.*ml")):
        workflow = _workflow(workflow_path)
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if not isinstance(uses, str) or not uses.startswith(
                    "actions/download-artifact@"
                ):
                    continue
                with_values = step.get("with", {})
                assert "if-no-artifact-found" not in with_values, (
                    f"{workflow_path.name}:{job_name}:{step.get('name', '<unnamed>')}"
                )


def test_critical_pattern_downloads_have_explicit_payload_guards() -> None:
    """Nightly mutation cohorts verify same-run artifacts before aggregation."""

    workflow = _workflow(WORKFLOWS / "nightly-full-gate.yml")
    aggregate = workflow["jobs"]["frontend-mutation-tests-full"]
    download = _step(
        aggregate, "Download all nightly frontend mutation shards from same run"
    )
    assert (
        download["with"]["pattern"]
        == "nightly-frontend-mutation-shard-${{ github.run_id }}-*"
    )
    following_runs = "\n".join(
        step.get("run", "")
        for step in aggregate["steps"][aggregate["steps"].index(download) + 1 :]
        if isinstance(step, dict)
    )
    assert "-ge 1" in following_runs
    assert "-type l" in following_runs
    assert "npm run test:mutation:verify" in following_runs


def test_ci_success_runs_while_dependencies_are_cancelled() -> None:
    """The finalizer must classify cancelled dependencies instead of skipping."""

    job = _workflow(CI)["jobs"]["ci-success"]
    assert job["if"] == "${{ always() }}"


def test_sonar_optionality_is_explicit_and_isolated() -> None:
    path = WORKFLOWS / "sonar.yml"
    text = path.read_text(encoding="utf-8")
    job = _workflow(path)["jobs"]["sonarcloud"]
    scan = _step(job, "SonarScan")

    assert "Advisory external analysis" in text
    assert "token off" in text
    assert "pull_request" not in text.split("on:", 1)[1].split("permissions:", 1)[0]
    assert (
        job["if"]
        == "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    )
    assert "pull-requests" not in job.get("permissions", {})
    assert scan["continue-on-error"] is True


def test_literal_continue_on_error_cases_are_exhaustively_classified() -> None:
    expected_steps = {
        ("admin-smoke-monitoring.yml", "admin-smoke", "Run admin smoke script"),
        (
            "ci.yml",
            "docker-security-scan",
            "Upload Trivy results to GitHub Security tab",
        ),
        ("contract-validation.yml", "spectral-lint", "Run Spectral lint"),
        (
            "contract-validation.yml",
            "spectral-lint",
            "Upload SARIF to GitHub Code Scanning",
        ),
        (
            "reusable-e2e-tests.yml",
            "e2e",
            "Upload E2E coverage artifact",
        ),
        (
            "reusable-e2e-tests.yml",
            "e2e",
            "Upload Playwright report",
        ),
        (
            "quality-promotion-check.yml",
            "stabilization-window",
            "Evaluate stabilization window",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy vulnerability scanner (filesystem)",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy configuration scanner (IaC)",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy revocation-store configuration scanner",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy university-ecosystem configuration scanner",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Run Trivy redis-compat configuration scanner",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy filesystem scan results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy config scan results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy revocation-store results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy university-ecosystem results",
        ),
        (
            "reusable-security-audit.yml",
            "docker-security",
            "Upload Trivy redis-compat results",
        ),
        (
            "checkov.yml",
            "checkov",
            "Run full-framework Checkov scan",
        ),
        (
            "checkov.yml",
            "checkov",
            "Run scoped Checkov Helm scan for university chart",
        ),
        (
            "checkov.yml",
            "checkov",
            "Run scoped Checkov Helm scan for revocation chart",
        ),
        (
            "checkov.yml",
            "checkov",
            "Run scoped Checkov Helm scan for Redis compatibility chart",
        ),
        (
            "checkov.yml",
            "checkov",
            "Verify university Helm JSON coverage",
        ),
        (
            "checkov.yml",
            "checkov",
            "Verify revocation Helm JSON coverage",
        ),
        (
            "checkov.yml",
            "checkov",
            "Verify Redis compatibility Helm JSON coverage",
        ),
        ("sonar.yml", "sonarcloud", "SonarScan"),
        ("visual-audit.yml", "visual-audit", "Run visual audit script"),
        (
            "unauthenticated-routes-smoke.yml",
            "unauthed-smoke",
            "Run unauthenticated routes smoke script",
        ),
    }
    observed_steps: set[tuple[str, str, str]] = set()
    observed_jobs: set[tuple[str, str, str]] = set()

    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job_name, job in _workflow(path)["jobs"].items():
            job_policy = job.get("continue-on-error")
            if job_policy:
                observed_jobs.add((path.name, job_name, str(job_policy)))
            for step in job.get("steps", []):
                if step.get("continue-on-error") is True:
                    observed_steps.add((path.name, job_name, step["name"]))

    assert observed_steps == expected_steps
    assert observed_jobs == {
        ("reusable-e2e-tests.yml", "e2e", "${{ inputs.advisory }}"),
    }


def test_checkov_aggregate_gate_rejects_non_success_outcomes() -> None:
    """The final gate must reject failed, skipped, or absent Checkov outcomes."""

    job = _workflow(WORKFLOWS / "checkov.yml")["jobs"]["checkov"]
    steps = job["steps"]
    scan_and_guard_ids = {
        "checkov_all",
        "checkov_helm_university",
        "checkov_helm_revocation",
        "checkov_helm_redis_compat",
        "verify_helm_university",
        "verify_helm_revocation",
        "verify_helm_redis_compat",
    }
    by_id = {step.get("id"): step for step in steps if step.get("id")}
    assert scan_and_guard_ids <= by_id.keys()

    aggregate = next(
        step
        for step in steps
        if step.get("name")
        == "Require all Checkov scans and Helm coverage guards to pass"
    )
    assert aggregate["if"] == "always()"
    assert aggregate["env"] == {
        "ALL_SCAN_OUTCOME": "${{ steps.checkov_all.outcome }}",
        "UNIVERSITY_SCAN_OUTCOME": "${{ steps.checkov_helm_university.outcome }}",
        "REVOCATION_SCAN_OUTCOME": "${{ steps.checkov_helm_revocation.outcome }}",
        "REDIS_SCAN_OUTCOME": "${{ steps.checkov_helm_redis_compat.outcome }}",
        "UNIVERSITY_GUARD_OUTCOME": "${{ steps.verify_helm_university.outcome }}",
        "REVOCATION_GUARD_OUTCOME": "${{ steps.verify_helm_revocation.outcome }}",
        "REDIS_GUARD_OUTCOME": "${{ steps.verify_helm_redis_compat.outcome }}",
    }
    run = aggregate["run"]
    assert 'if [[ "$outcome" != "success" ]]; then' in run
    assert 'if [[ "$failed" -ne 0 ]]; then' in run
    assert "exit 1" in run
    assert 'if [[ ! -s "$report" ]]; then' in run
    for report in (
        "results.sarif",
        "results-helm-university-ecosystem.sarif",
        "results-helm-revocation-store.sarif",
        "results-helm-redis-compat.sarif",
    ):
        assert report in run


def test_docker_cli_images_resolve_only_preceding_simple_image_assignments() -> None:
    pinned_image = EXPECTED_EXTERNAL_IMAGES["redis:7-alpine"]
    script = f"""harness="scripts/quality/check_prometheus_alert_rules.py"
image='{pinned_image}'
docker pull "$image"
image="{pinned_image}"
docker create --cidfile /tmp/container.cid \
  --mount type=bind,source=/tmp,target=/tmp \
  --entrypoint /bin/true "${{image}}"
"""

    assert list(_docker_cli_images(script)) == [pinned_image, pinned_image]


def test_docker_cli_image_parser_rejects_unpinned_and_path_shaped_refs() -> None:
    scripts = (
        'image="redis:7-alpine"\ndocker pull "$image"',
        'image="scripts/quality/check_prometheus_alert_rules.py"\ndocker pull "$image"',
        "docker pull scripts/quality/check_prometheus_alert_rules.py",
    )

    for script in scripts:
        images = list(_docker_cli_images(script))
        assert len(images) == 1
        with pytest.raises(AssertionError, match="unpinned static image"):
            _assert_pinned(images[0], source="parser-control")


def test_docker_cli_dynamic_reassignment_clears_prior_literal_binding() -> None:
    pinned_image = EXPECTED_EXTERNAL_IMAGES["redis:7-alpine"]
    script = f'''image="{pinned_image}"
docker pull "$image"
image="$(resolve_image)"
docker create --cidfile /tmp/container.cid \
  --mount type=bind,source=/tmp,target=/tmp "$image"
'''

    assert list(_docker_cli_images(script)) == [pinned_image, "$image"]


def test_powershell_docker_pull_resolves_its_literal_array_and_loop_variable() -> None:
    script = f'''$images = @(
  "{EXPECTED_EXTERNAL_IMAGES["nats:2.15.0-alpine"]}",
  "{EXPECTED_EXTERNAL_IMAGES["postgres:15-alpine"]}"
)
foreach ($image in $images) {{
  docker pull $image
}}
'''

    assert list(_powershell_cli_images(script)) == [
        EXPECTED_EXTERNAL_IMAGES["nats:2.15.0-alpine"],
        EXPECTED_EXTERNAL_IMAGES["postgres:15-alpine"],
    ]


def test_powershell_docker_pull_loop_rejects_an_unpinned_literal_array_entry() -> None:
    script = """$images = @(
  "redis:7-alpine",
  "postgres:15-alpine@sha256:fe0737ba566a2c5b2a28f34433c0a423261900ec17b9bf7ad115e1aae7e57f1b"
)
foreach ($image in $images) {
  docker pull $image
}
"""

    images = list(_powershell_cli_images(script))
    assert len(images) == 2
    with pytest.raises(AssertionError, match="unpinned static image"):
        for image in images:
            _assert_pinned(image, source="powershell-loop-control")


def test_powershell_literal_array_without_matching_docker_pull_is_not_an_image() -> (
    None
):
    script = """$harness = @(
  "scripts/quality/check_prometheus_alert_rules.py"
)
foreach ($path in $harness) {
  Write-Host $path
}
"""

    assert list(_powershell_cli_images(script)) == []


def test_powershell_dynamic_reassignment_does_not_reuse_stale_literal_array() -> None:
    script = """$images = @(
  "redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
)
$images = Get-Images
foreach ($image in $images) {
  docker pull $image
}
"""

    assert list(_powershell_cli_images(script)) == []


def test_powershell_array_append_after_literal_binding_fails_closed() -> None:
    script = """$images = @(
  "redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
)
$images += "redis:latest"
foreach ($image in $images) {
  docker pull $image
}
"""

    images = list(_powershell_cli_images(script))
    assert images == ["<modified PowerShell image array>"]
    with pytest.raises(AssertionError, match="unpinned static image"):
        _assert_pinned(images[0], source="powershell-array-append-control")


def test_reusable_backend_image_pull_loop_keeps_all_four_audited_pins() -> None:
    workflow = _workflow(WORKFLOWS / "reusable-backend-tests.yml")
    images = [
        image
        for scalar in _scalars(workflow)
        for image in _powershell_cli_images(scalar)
    ]

    assert Counter(images) == Counter(
        EXPECTED_EXTERNAL_IMAGES[image]
        for image in (
            "nats:2.15.0-alpine",
            "postgres:15-alpine",
            "redis:7-alpine",
            "pgvector/pgvector:pg17",
        )
    )


def test_all_static_external_workflow_images_are_digest_pinned() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _workflow(path)
        source = path.relative_to(ROOT).as_posix()

        for image in _image_values(workflow):
            _assert_pinned(image, source=source)

        for scalar in _scalars(workflow):
            for image in _docker_cli_images(scalar):
                _assert_pinned(image, source=source)
            for image in _powershell_cli_images(scalar):
                _assert_pinned(image, source=source)


def test_external_workflow_images_use_the_audited_digests() -> None:
    scalars = [
        scalar
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for scalar in _scalars(_workflow(path))
    ]
    combined = "\n".join(scalars)

    for tag, pinned in EXPECTED_EXTERNAL_IMAGES.items():
        assert pinned in combined, f"expected pinned workflow image {pinned}"
        assert not re.search(rf"{re.escape(tag)}(?!@sha256:)", combined)


def test_precommit_semgrep_image_remains_immutable() -> None:
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    hooks = [
        hook
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "semgrep-docker"
    ]
    assert len(hooks) == 1
    hook = hooks[0]

    reusable_security_jobs = _workflow(WORKFLOWS / "reusable-security-audit.yml")[
        "jobs"
    ]
    assert "semgrep" not in reusable_security_jobs

    entry_tokens = shlex.split(hook.get("entry", ""))
    local_images = [
        token for token in entry_tokens if token.startswith("semgrep/semgrep:")
    ]
    assert local_images == [PRECOMMIT_SEMGREP_IMAGE]
    assert hook["args"] == ["--config", "auto", "--error", "--oss-only"]
    assert hook["exclude"] == (
        r"(^|/)tests/|^alembic/|^native/rust_ext/fuzz/|_test\.go$|"
        r"^frontend/coverage-[^/]+/"
    )
    assert hook["require_serial"] is True


def test_go_and_compose_s3_cells_use_the_audited_seaweedfs_image() -> None:
    image = (
        "ghcr.io/chrislusf/seaweedfs:4.48@sha256:"
        "4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d"
    )
    for path in (
        ROOT / "services/file-processor/internal/workflow/workflow_integration_test.go",
        WORKFLOWS / "nightly-full-gate.yml",
        ROOT / "docker-compose.sandbox.yml",
    ):
        assert image in path.read_text(encoding="utf-8"), path

    sandbox = _workflow(ROOT / "docker-compose.sandbox.yml")["services"]["minio"]
    assert sandbox["command"] == ["mini", "-dir=/data", "-s3.port=9000"]
    assert sandbox["environment"]["S3_BUCKET"] == "uploads"
    assert "127.0.0.1:59000:9000" in sandbox["ports"]
    assert sandbox["healthcheck"]["test"] == [
        "CMD",
        "wget",
        "-qO-",
        "http://localhost:9000/status",
    ]


def test_active_workflows_pin_linux_runner_version() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        assert "ubuntu-latest" not in text, (
            f"{path.relative_to(ROOT).as_posix()} must pin ubuntu-24.04"
        )


def test_deployment_workflows_cannot_report_mock_success() -> None:
    assert not (WORKFLOWS / "preview-env.yml").exists()

    path = WORKFLOWS / "deploy.yml"
    text = path.read_text(encoding="utf-8")
    workflow = _workflow(path)
    deploy = workflow["jobs"]["deploy"]
    steps = deploy["steps"]

    assert workflow["name"] == "Deploy (Helm / Kubernetes)"
    assert deploy["environment"]["url"] == "${{ vars.DEPLOYMENT_URL }}"
    assert "placeholder" not in text.lower()
    assert "mocking kubernetes" not in text.lower()
    assert "deployed successfully" not in text.lower()
    assert "example.com" not in text
    assert not re.search(r"(?m)^\s*#\s*(?:helm|kubectl)\b", text)
    assert not any(name.startswith("build-") for name in workflow["jobs"])
    resolve = workflow["jobs"]["resolve-images"]
    resolve_text = "\n".join(str(step.get("run", "")) for step in resolve["steps"])
    assert ".github/workflows/build-release-images.yml" in resolve_text
    assert "verify_release_image_manifest.py" in resolve_text
    assert (
        "release-image-provenance-$RELEASE_SHA-attempt-$BUILD_RUN_ATTEMPT"
        in resolve_text
    )

    validate = _step(deploy, "Validate deployment contract")["run"]
    for setting in (
        "OIDC_DEPLOY_ROLE_ARN",
        "AWS_REGION",
        "EKS_CLUSTER_NAME",
        "K8S_NAMESPACE",
        "HELM_RELEASE_NAME",
        "HELM_VALUES_FILE",
        "CONNECTIONS_SECRET_NAME",
        "APPLICATION_SECRETS_NAME",
        "DEPLOYMENT_URL",
        "GATEWAY_HEALTH_URL",
        "WS_HUB_HEALTH_URL",
        "BACKEND_HEALTH_URL",
        "FRONTEND_HEALTH_URL",
    ):
        assert setting in validate
    assert "Required deployment setting" in validate
    assert "^sha256:[0-9a-f]{64}$" in validate
    assert "must resolve inside the checked-out repository" in validate

    cluster = _step(deploy, "Configure and verify cluster access")["run"]
    assert "aws eks update-kubeconfig" in cluster
    assert "kubectl cluster-info" in cluster

    helm = _step(deploy, "Deploy Helm release atomically")["run"]
    assert "bash .github/scripts/deploy-helm.sh upgrade" in helm
    helm_script = (WORKFLOWS.parent / "scripts" / "deploy-helm.sh").read_text(
        encoding="utf-8"
    )
    assert "helm upgrade --install" in helm_script
    for flag in ("--rollback-on-failure", "--wait=legacy", "--wait-for-jobs"):
        assert flag in helm_script

    assert not any(step.get("name") == "Deploy WS Hub image" for step in steps)

    capture = _step(deploy, "Capture rollback state")
    rollback = _step(deploy, "Roll back a deployment that failed verification")
    assert capture["id"] == "rollback_state"
    assert "helm list" in capture["run"]
    assert "ws_hub_image=" not in capture["run"]
    assert "failure()" in rollback["if"]
    assert "helm rollback" in rollback["run"]
    assert "helm uninstall" in rollback["run"]
    assert "PREVIOUS_WS_HUB_IMAGE" not in rollback["run"]
    assert "kubectl set image" not in rollback["run"]

    smoke = _step(deploy, "Post-deployment smoke test")
    assert smoke["env"] == {
        "GATEWAY_URL": "${{ vars.GATEWAY_HEALTH_URL }}",
        "WS_HUB_URL": "${{ vars.WS_HUB_HEALTH_URL }}",
        "BACKEND_URL": "${{ vars.BACKEND_HEALTH_URL }}",
        "FRONTEND_URL": "${{ vars.FRONTEND_HEALTH_URL }}",
    }
    kyverno = _step(deploy, "Verify Kyverno policy compliance (MOD-14-02)")
    kyverno_script = kyverno["run"]
    assert "validatingpolicies.policies.kyverno.io" in kyverno_script
    assert "clusterpolicies.kyverno.io" not in kyverno_script
    assert ".status.conditionStatus.ready == true" in kyverno_script
    assert 'index("Deny") != null' in kyverno_script
    assert 'index("Audit") != null' in kyverno_script
    assert "validationFailureAction" not in kyverno_script
    dora = _step(deploy, "Record DORA Lead Time for Changes")
    assert steps.index(smoke) < steps.index(kyverno) < steps.index(rollback)
    assert steps.index(rollback) < steps.index(dora)


def test_deploy_bootstraps_checksum_bound_tools_before_oidc() -> None:
    """Deployment tooling must be immutable before cloud credentials exist."""

    workflow = _workflow(WORKFLOWS / "deploy.yml")
    deploy = workflow["jobs"]["deploy"]
    steps = deploy["steps"]
    names = [step.get("name") for step in steps]

    assert not any(
        str(step.get("uses", "")).startswith(
            ("azure/setup-kubectl@", "azure/setup-helm@")
        )
        for step in steps
    )
    tooling = _step(deploy, "Install checksum-pinned deployment tools")
    oidc = _step(deploy, "Configure AWS credentials (OIDC)")
    assert names.index(tooling["name"]) < names.index(oidc["name"])
    assert tooling["env"] == {
        "KUBECTL_VERSION": "${{ vars.KUBECTL_VERSION }}",
        "KUBECTL_SHA256": "${{ vars.KUBECTL_SHA256 }}",
        "HELM_VERSION": "v4.2.4",
        "HELM_ARCHIVE_SHA256": HELM_4_2_4_LINUX_AMD64_SHA256,
    }

    run = str(tooling["run"])
    assert "set -euo pipefail" in run
    assert '[[ "$KUBECTL_VERSION" =~ ^v1\\.[0-9]+\\.[0-9]+$ ]]' in run
    assert '[[ "$KUBECTL_SHA256" =~ ^[0-9a-f]{64}$ ]]' in run
    assert '[[ "$HELM_VERSION" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]' in run
    assert '[[ "$HELM_ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]]' in run
    assert "mktemp -d" in run
    assert "--proto '=https'" in run
    assert "--tlsv1.2" in run
    assert "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" in run
    assert "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" in run
    assert run.count("sha256sum --check --strict") == 2
    assert "sudo install --mode 0755" in run
    assert "kubectl version --client --output=json" in run
    assert "helm version --template '{{.Version}}'" in run

    lines = [line.strip() for line in run.splitlines()]
    verify_indices = [
        index
        for index, line in enumerate(lines)
        if "sha256sum --check --strict" in line
    ]
    install_indices = [
        index for index, line in enumerate(lines) if line.startswith("sudo install")
    ]
    assert len(verify_indices) == 2
    assert len(install_indices) == 2
    assert max(verify_indices) < min(install_indices)

    contract = _step(deploy, "Validate deployment contract")
    assert contract["env"]["KUBECTL_VERSION"] == "${{ vars.KUBECTL_VERSION }}"
    assert contract["env"]["KUBECTL_SHA256"] == "${{ vars.KUBECTL_SHA256 }}"
    assert "KUBECTL_VERSION" in contract["run"]
    assert "KUBECTL_SHA256" in contract["run"]


def test_deploy_smoke_dependencies_are_hash_locked_before_oidc() -> None:
    """Smoke-test dependencies cannot execute mutable index artifacts."""

    deploy = _workflow(WORKFLOWS / "deploy.yml")["jobs"]["deploy"]
    steps = deploy["steps"]
    names = [step.get("name") for step in steps]
    install = _step(deploy, "Install hash-locked smoke-test dependencies")
    setup_python = _step(deploy, "Setup Python")
    oidc = _step(deploy, "Configure AWS credentials (OIDC)")
    assert names.index(setup_python["name"]) < names.index(oidc["name"])
    assert names.index(install["name"]) < names.index(oidc["name"])

    run = str(install["run"])
    assert "python -m pip --isolated install" in run
    assert "--index-url https://pypi.org/simple" in run
    assert "--require-hashes" in run
    assert "--only-binary=:all:" in run
    assert "--no-deps" in run
    assert 'pip install "requests==' not in run
    for requirement, digest in DEPLOY_SMOKE_REQUIREMENTS.items():
        assert f"{requirement} --hash=sha256:{digest}" in run
    assert 'requests.__version__ == "2.34.2"' in run


def test_deploy_rejects_unsupported_kubectl_server_version_skew() -> None:
    """The environment-selected client must be compatible with the live API server."""

    deploy = _workflow(WORKFLOWS / "deploy.yml")["jobs"]["deploy"]
    cluster = _step(deploy, "Configure and verify cluster access")
    assert cluster["env"]["KUBECTL_VERSION"] == "${{ vars.KUBECTL_VERSION }}"

    run = str(cluster["run"])
    assert "kubectl version --output=json" in run
    assert ".clientVersion.major" in run
    assert ".clientVersion.minor" in run
    assert ".serverVersion.major" in run
    assert ".serverVersion.minor" in run
    assert "version_skew=$((client_minor - server_minor))" in run
    assert "version_skew < -1 || version_skew > 1" in run
    assert "outside the supported +/-1 minor version skew" in run


def test_sbom_osv_reporting_does_not_hide_scanner_failures() -> None:
    job = _workflow(WORKFLOWS / "sbom.yml")["jobs"]["sbom-go"]
    scan = _step(job, "Scan Go modules for vulnerabilities + generate SBOM")
    validate = _step(job, "Validate OSV scanner result")

    assert scan["id"] == "osv_scan"
    assert "|| true" not in scan["run"]
    assert "scanner_status=$?" in scan["run"]
    assert "scanner_status=$scanner_status" in scan["run"]
    assert validate["if"] == "always()"
    assert validate["env"]["SCANNER_STATUS"] == (
        "${{ steps.osv_scan.outputs.scanner_status }}"
    )
    assert '"$SCANNER_STATUS" -gt 1' in validate["run"]
    assert "structurally valid SARIF" in validate["run"]
    assert '"$SCANNER_STATUS" -eq 1 && "$finding_count" -eq 0' in validate["run"]


def test_reusable_trivy_scans_upload_evidence_then_fail_closed() -> None:
    job = _workflow(WORKFLOWS / "reusable-security-audit.yml")["jobs"][
        "docker-security"
    ]
    steps = {step.get("id"): step for step in job["steps"] if step.get("id")}
    scan_ids = (
        "trivy_fs",
        "trivy_config",
        "trivy_revocation",
        "trivy_university",
        "trivy_redis_compat",
    )
    scans = {scan_id: steps[scan_id] for scan_id in scan_ids}

    assert scans["trivy_fs"]["with"]["scan-type"] == "fs"
    assert scans["trivy_fs"]["with"]["scan-ref"] == "."
    assert scans["trivy_config"]["with"]["scan-type"] == "config"
    assert scans["trivy_config"]["with"]["scan-ref"] == "."
    assert scans["trivy_config"]["with"]["trivy-config"] == (
        "security/trivy-university-config.yaml"
    )
    assert scans["trivy_config"]["with"]["skip-dirs"] == (
        "charts/revocation-store,charts/university-ecosystem,charts/redis-compat"
    )

    chart_scans = {
        "trivy_revocation": (
            "charts/revocation-store",
            "${{ runner.temp }}/trivy-inputs/trivy-revocation-config.json",
            "trivy-revocation-config.sarif",
        ),
        "trivy_university": (
            "charts/university-ecosystem",
            "${{ runner.temp }}/trivy-inputs/trivy-university-config.json",
            "trivy-university-config.sarif",
        ),
        "trivy_redis_compat": (
            "charts/redis-compat",
            "${{ runner.temp }}/trivy-inputs/trivy-redis-compat-config.json",
            "trivy-redis-compat-config.sarif",
        ),
    }
    chart_outputs: set[str] = set()
    for scan_id, (chart, config, output) in chart_scans.items():
        scan = scans[scan_id]
        assert scan["with"]["scan-type"] == "config"
        assert scan["with"]["scan-ref"] == chart
        assert scan["with"]["trivy-config"] == config
        assert scan["with"]["output"] == output
        chart_outputs.add(scan["with"]["output"])
    assert chart_outputs == {details[2] for details in chart_scans.values()}

    uploads = {
        "trivy_fs": (
            "Upload Trivy filesystem scan results",
            "trivy-fs.sarif",
            ".github/workflows/ci.yml:docker-security",
        ),
        "trivy_config": (
            "Upload Trivy config scan results",
            "trivy-config.sarif",
            "trivy-config",
        ),
        "trivy_revocation": (
            "Upload Trivy revocation-store results",
            "trivy-revocation-config.sarif",
            "trivy-revocation-config",
        ),
        "trivy_university": (
            "Upload Trivy university-ecosystem results",
            "trivy-university-config.sarif",
            "trivy-university-config",
        ),
        "trivy_redis_compat": (
            "Upload Trivy redis-compat results",
            "trivy-redis-compat-config.sarif",
            "trivy-redis-compat-config",
        ),
    }
    for _, (name, sarif_file, category) in uploads.items():
        upload = _step(job, name)
        assert upload["if"] == "always()"
        assert upload["continue-on-error"] is True
        assert upload["with"]["sarif_file"] == sarif_file
        assert upload["with"]["category"] == category

    for scan_id, scan in scans.items():
        assert scan["continue-on-error"] is True
        assert scan["with"]["exit-code"] == "1"
        assert scan["with"]["severity"] == "CRITICAL,HIGH"
        assert scan["with"]["limit-severities-for-sarif"] is True
        if scan_id != "trivy_fs":
            assert scan["with"]["trivyignores"] == ".trivyignore.yaml"

    preflight = _step(job, "Validate isolated Helm profiles before Trivy scans")
    assert (
        'if ! jq -e \'type == "object" and (.Results | type == "array" and length > 0)\''
        in preflight["run"]
    )
    assert 'grep -Fqi "Skipping chart"' in preflight["run"]
    assert 'grep -Fqi "missing in charts/"' in preflight["run"]
    assert 'grep -Fqi "Failed to render Chart files"' in preflight["run"]
    assert (
        'trivy config --config "$config" --misconfig-scanners helm' in preflight["run"]
    )

    reassert = _step(job, "Re-assert Trivy filesystem and configuration gates")
    assert reassert["if"] == "always()"
    assert reassert["env"] == {
        "FILESYSTEM_OUTCOME": "${{ steps.trivy_fs.outcome }}",
        "CONFIGURATION_OUTCOME": "${{ steps.trivy_config.outcome }}",
        "REVOCATION_OUTCOME": "${{ steps.trivy_revocation.outcome }}",
        "UNIVERSITY_OUTCOME": "${{ steps.trivy_university.outcome }}",
        "REDIS_COMPAT_OUTCOME": "${{ steps.trivy_redis_compat.outcome }}",
    }
    assert 'exit "$failed"' in reassert["run"]
    assert 'if [[ "$outcome" != "success" ]]' in reassert["run"]


def test_trivy_oci_export_precedes_helm_dependency_mutation_and_preflight(
    tmp_path: Path,
) -> None:
    job = _workflow(WORKFLOWS / "reusable-security-audit.yml")["jobs"][
        "docker-security"
    ]
    steps = job["steps"]
    source_guard = _step(job, "Verify source revision for backend OCI evidence")
    export = _step(job, "Export backend OCI and prepare isolated Helm profiles")
    dependencies = _step(job, "Build Helm dependencies for Trivy")
    preflight = _step(job, "Validate isolated Helm profiles before Trivy scans")

    assert "git status --porcelain=v1 --untracked-files=all" in source_guard["run"]
    assert "git diff --quiet HEAD --" in export["run"]
    assert "set -euo pipefail" in export["run"]
    assert export["run"].index("git diff --quiet HEAD --") < export["run"].index(
        "docker buildx build"
    )
    assert "python3 scripts/ci/helm_dependency_build.py" in dependencies["run"]
    assert steps.index(source_guard) < steps.index(export) < steps.index(dependencies)
    assert steps.index(dependencies) < steps.index(preflight)

    steps_by_id = {step.get("id"): step for step in steps if step.get("id")}
    for scan_id in ("trivy_revocation", "trivy_university", "trivy_redis_compat"):
        assert steps.index(dependencies) < steps.index(steps_by_id[scan_id])

    # Verify the tracked-worktree condition the export guard relies on using a
    # disposable Git checkout. Dependency generation after the guard may dirty
    # tracked chart inputs; OCI export must already have completed by then.
    git = which("git")
    assert git is not None, "Git is required for the isolated source-guard test"
    repository = tmp_path / "checkout"
    repository.mkdir()
    tracked_file = repository / "tracked.txt"
    tracked_file.write_text("source snapshot\n", encoding="utf-8")

    def run_git(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603 - fixed Git command and fixture args
            [git, *args],
            cwd=repository,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()

    run_git("init", "--quiet")
    run_git("add", "tracked.txt")
    run_git(
        "-c",
        "user.name=Workflow contract fixture",
        "-c",
        "user.email=workflow-contract@example.invalid",
        "commit",
        "-m",
        "fixture source",
    )
    clean_diff = subprocess.run(  # noqa: S603 - resolved Git and fixture-owned arguments
        [git, "diff", "--quiet", "HEAD", "--"],
        cwd=repository,
        check=False,
        text=True,
        capture_output=True,
    )
    assert clean_diff.returncode == 0

    tracked_file.write_text("dependency-generated mutation\n", encoding="utf-8")
    dirty_diff = subprocess.run(  # noqa: S603 - resolved Git and fixture-owned arguments
        [git, "diff", "--quiet", "HEAD", "--"],
        cwd=repository,
        check=False,
        text=True,
        capture_output=True,
    )
    assert dirty_diff.returncode == 1


def test_workflow_tool_installers_do_not_use_latest_selectors() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))
    )
    assert not re.search(r"\bgo install\s+\S+@(?:latest|main|master)\b", combined)
    assert "go.uber.org/nilaway/cmd/nilaway@v0.0.0-20260918162853-acb8859b9031" in (
        WORKFLOWS / "nilaway.yml"
    ).read_text(encoding="utf-8")
    reusable_go = (WORKFLOWS / "reusable-go-tests.yml").read_text(encoding="utf-8")
    assert (
        "github.com/avito-tech/go-mutesting/cmd/go-mutesting@v0.0.0-20261002081621-9ce5f731e321"
        in reusable_go
    )
    assert "uv pip install atheris" not in combined


def test_dependency_review_does_not_upload_a_report_it_never_creates() -> None:
    text = (WORKFLOWS / "dependency-review.yml").read_text(encoding="utf-8")
    assert "dependency-review-report.json" not in text


def test_schemathesis_operation_shards_preserve_depth_and_fail_closed_aggregate() -> (
    None
):
    workflow = _workflow(WORKFLOWS / "nightly-full-gate.yml")
    shard_job = workflow["jobs"]["schemathesis-api-tests-shard"]
    matrix = shard_job["strategy"]["matrix"]["shard"]

    # Every operation remains covered with the same 25 examples; only the
    # process fan-out changes so each TestClient/lifespan-heavy shard is
    # smaller.  Keep the matrix explicit so a missing logical shard cannot be
    # hidden behind a dynamic expression.
    assert matrix == list(range(8))
    assert shard_job["name"] == (
        "Schemathesis - API Schema Conformance / shard ${{ matrix.shard }}/8"
    )
    run = _step(shard_job, "Run Schemathesis conformance tests")
    assert run["env"] == {
        "DATABASE_URL": "sqlite+aiosqlite:///./test_schemathesis.db",
        "ENVIRONMENT": "testing",
        "REVOCATION_REDIS_URL": "redis://localhost:6380/0",
        "OTEL_SDK_DISABLED": "true",
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET": "1",
        "SCHEMATHESIS_MAX_EXAMPLES": "25",
        "SCHEMATHESIS_SHARD_COUNT": "8",
        "SCHEMATHESIS_SHARD_INDEX": "${{ matrix.shard }}",
    }

    aggregate = workflow["jobs"]["schemathesis-api-tests"]
    assert (
        aggregate["if"]
        == "${{ always() && !cancelled() && github.ref == 'refs/heads/main' }}"
    )
    assert aggregate["needs"] == "schemathesis-api-tests-shard"
    gate = _step(aggregate, "Require every Schemathesis shard to pass")
    assert gate["env"] == {
        "SHARD_RESULT": "${{ needs.schemathesis-api-tests-shard.result }}"
    }
    assert 'if [[ "$SHARD_RESULT" != "success" ]]' in gate["run"]
    assert 'echo "Schemathesis shard aggregate: $SHARD_RESULT"' in gate["run"]
    assert "exit 1" in gate["run"]


def test_mvp_blocking_ci_excludes_mutation_and_deferred_heavy_graphs() -> None:
    workflow = _workflow(CI)
    jobs = workflow["jobs"]
    deferred_job_ids = {
        "stryker-preflight",
        "stryker-shards",
        "stryker-aggregate",
        "stryker-evidence-roundtrip",
        "frontend-mutation-required-context",
        "mutation-scope",
        "mutation-tests-stats",
        "mutation-tests-universe-base",
        "mutation-tests-universe",
        "mutation-tests-incremental",
        "e2e-tests",
        "e2e-tests-cross-browser",
        "schemathesis-api-tests-shard",
        "schemathesis-api-tests",
        "chaos-tests",
        "chaos-loadtest-orchestrator",
    }
    assert deferred_job_ids.isdisjoint(jobs)

    aggregate = jobs["ci-success"]
    assert deferred_job_ids.isdisjoint(aggregate["needs"])
    aggregate_script = "\n".join(
        step.get("run", "") for step in aggregate["steps"]
    ).lower()
    assert not any(
        token in aggregate_script
        for token in ("mutation", "schemathesis", "chaos", "cross-browser")
    )
    assert {
        "security-audit",
        "coverage-policy-gate",
        "provenance-check",
        "openapi-verify",
        "graphql-drift-check",
    }.issubset(aggregate["needs"])

    frontend = jobs["frontend-tests"]
    assert frontend["with"]["run-lighthouse"] is False


def test_deferred_heavy_evidence_remains_on_trusted_scheduled_or_manual_workflows() -> (
    None
):
    nightly_path = WORKFLOWS / "nightly-full-gate.yml"
    nightly = _workflow(nightly_path)
    nightly_events = nightly.get("on", nightly.get(True, {}))
    assert "schedule" in nightly_events
    assert "workflow_dispatch" in nightly_events
    assert "refs/heads/main" in str(nightly["jobs"])
    deferred_jobs = {
        "mutation-tests-full",
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
        "frontend-mutation-tests-full",
        "frontend-mutation-roundtrip",
        "browser-matrix",
        "schemathesis-api-tests-shard",
        "schemathesis-api-tests",
        "chaos-tests",
        "chaos-loadtest-orchestrator",
        "load-and-chaos",
    }
    assert deferred_jobs.issubset(nightly["jobs"])
    for job_id in deferred_jobs:
        assert "github.ref == 'refs/heads/main'" in str(
            nightly["jobs"][job_id].get("if", "")
        ), f"deferred evidence job is not default-branch guarded: {job_id}"

    dispatch_guard = nightly["jobs"]["verify-default-branch-dispatch"]
    assert dispatch_guard["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
    assert (
        "refs/heads/main"
        in _step(dispatch_guard, "Require protected default branch")["run"]
    )
    reporter = nightly["jobs"]["notify-failure"]
    assert "always()" in reporter["if"]
    reported_jobs = deferred_jobs - {"schemathesis-api-tests-shard"}
    assert reported_jobs.issubset(reporter["needs"])
    assert nightly["jobs"]["schemathesis-api-tests"]["needs"] == (
        "schemathesis-api-tests-shard"
    )

    browser = nightly["jobs"]["browser-matrix"]
    include = browser["strategy"]["matrix"]["include"]
    chromium_shards = [entry for entry in include if entry["browser"] == "chromium"]
    assert [entry["shard-index"] for entry in chromium_shards] == [1, 2, 3, 4]
    assert all(entry["shard-total"] == 4 for entry in chromium_shards)
    assert {entry["browser"] for entry in include} == {
        "chromium",
        "firefox",
        "webkit",
        "mobile-webkit",
    }

    manual_mutation = _workflow(WORKFLOWS / "manual-mutation-evidence.yml")
    manual_events = manual_mutation.get("on", manual_mutation.get(True, {}))
    assert "workflow_dispatch" in manual_events
    assert "manual-full-backend-mutation" in manual_mutation["jobs"]


def test_q4_heavy_scans_are_scheduled_manual_and_default_branch_guarded() -> None:
    expected = {
        "lhci-linux.yml": ("lhci", "0 5 * * 1"),
        "sqlmap.yml": ("sqlmap", "0 4 * * 1"),
        "trufflehog.yml": ("trufflehog", "0 3 * * 1"),
    }
    for filename, (job_id, cron) in expected.items():
        workflow = _workflow(WORKFLOWS / filename)
        triggers = workflow.get("on", workflow.get(True, {}))
        assert set(triggers) == {"schedule", "workflow_dispatch"}
        assert triggers["schedule"] == [{"cron": cron}]
        assert "pull_request" not in triggers and "push" not in triggers
        verify = workflow["jobs"]["verify-default-branch-dispatch"]
        assert verify["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
        assert (
            "refs/heads/main"
            in _step(verify, "Require protected default branch")["run"]
        )
        job = workflow["jobs"][job_id]
        assert job["needs"] == "verify-default-branch-dispatch"
        assert "github.ref == 'refs/heads/main'" in job["if"]
        assert "needs.verify-default-branch-dispatch.result == 'success'" in job["if"]

    required = json.loads(
        (ROOT / "quality" / "release-required-checks.json").read_text()
    )
    for event in ("push_main", "pull_request_main"):
        contexts = {
            check["name"] for check in required["events"][event]["required_checks"]
        }
        assert "SQLMap Scan" not in contexts
        assert "TruffleHog Scan" not in contexts
        assert "Gitleaks scan" in contexts
        assert "Analyze (python)" in contexts

    for filename in ("lhci-linux.yml", "sqlmap.yml", "trufflehog.yml"):
        scheduled = _workflow(WORKFLOWS / filename)
        events = scheduled.get("on", scheduled.get(True, {}))
        assert "schedule" in events, filename
        assert "workflow_dispatch" in events, filename
        assert "refs/heads/main" in str(scheduled["jobs"]), filename

    release = json.loads(
        (ROOT / "quality" / "release-required-checks.json").read_text(encoding="utf-8")
    )
    for event in release["events"].values():
        names = {check["name"] for check in event["required_checks"]}
        assert "SQLMap Scan" not in names
        assert "TruffleHog Scan" not in names
