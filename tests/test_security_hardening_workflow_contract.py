"""Supply-chain hardening contracts for scanner bootstrap steps."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
PRE_COMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"
SECURITY_AUDIT = WORKFLOWS / "reusable-security-audit.yml"
STANDALONE_SECURITY_WORKFLOWS = {
    "checkov.yml": "checkov",
    "codeql.yml": "analyze",
    "dependency-review.yml": "dependency-review",
    "gitleaks.yml": "gitleaks",
    "zizmor.yml": "zizmor",
}
DETECT_SECRETS_REQUIREMENTS = ROOT / "security" / "detect-secrets-requirements.txt"
DETECT_SECRETS_SCAN_EXCLUSION = (
    r"^(?:\.secrets\.baseline|frontend/WASM_SOURCE_PROVENANCE\.json)$"
)

ACTIONLINT_SOURCE_SHA = (
    "5dc52e8daa4ef51bfd76a648128474bd41d65df0"  #  -- immutable upstream source revision
)
ACTIONLINT_ARCHIVE_SHA256 = "908edaee62f6afa5c53b4773c91333043e17f4a1f315f8f5e311a63de0c122ba"  #  -- source archive checksum
HADOLINT_SHA256 = "c7187db94eeeeca956519a6af171adc31453941a1e777961f6e680f697c8c507"
SHELLCHECK_SHA256 = "8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198"
CARGO_BINSTALL_SCRIPT_COMMIT = "5aafaaca52423a22d83a812fa3ca77492e2895db"  # pragma: allowlist secret -- immutable installer commit
CARGO_BINSTALL_SCRIPT_SHA256 = "d3a93702160e0ec03e2a4e996855db1f01adee801fb84a43add24e0877ef8eae"  # pragma: allowlist secret -- release checksum
SLSA_VERIFIER_SHA256 = (
    "946dbec729094195e88ef78e1734324a27869f03e2c6bd2f61cbc06bd5350339"
)
KUBECONFORM_SHA256 = "9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883"
K6_SHA256 = "39c3117b6af817592dcd0ce4242105c0a7af10948c2a425306f0be8f7a8a8ab1"
SQUAWK_SHA256 = "03efe0e666b63bf33e2493693ee0aa9dbed07cbdcd20f7a8292245c1da9d790a"
SQUAWK_RELEASE_URL = (
    "https://github.com/sbdchd/squawk/releases/download/v2.67.0/squawk-linux-x64"
)
SQUAWK_BINARY_DIRECTORY = "university-ecosystem-tools/squawk/v2.67.0/linux-x64"
SQUAWK_BINARY_SUFFIX = f"{SQUAWK_BINARY_DIRECTORY}/squawk-linux-x64"
SQUAWK_RUNNER = "ubuntu-24.04"
SQUAWK_VERIFY_SHELL = "/bin/bash --noprofile --norc -e -o pipefail {0}"
SQUAWK_EXCLUSIONS = (
    "prefer-robust-stmts",
    "prefer-text-field",
    "prefer-bigint-over-int",
    "prefer-identity",
    "prefer-timestamp-tz",
    "disallowed-unique-constraint",
    "require-enum-value-ordering",
)
SQUAWK_AUD148_CONDITION = (
    "${{ !cancelled() &&\n"
    "    (steps.migration-squawk.outcome == 'success' ||\n"
    "     steps.migration-squawk.outcome == 'failure') }}"
)
TRIVY_SHA256 = "c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f"
CRD_CATALOG_COMMIT = "866b2653a5334db9aed20ad74701e20fd464471b"  # pragma: allowlist secret -- immutable schema revision


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _squawk_exclusions(run: Any) -> tuple[str, ...] | None:
    if not isinstance(run, str):
        return None
    match = re.search(r"squawk_args=\((.*?)\)", run, re.DOTALL)
    if match is None:
        return None
    normalized = " ".join(match.group(1).split())
    expected = " ".join(f"--exclude {rule}" for rule in SQUAWK_EXCLUSIONS)
    return SQUAWK_EXCLUSIONS if normalized == expected else None


def _has_standalone_squawk_checks(run: Any, target: str, expected_count: int) -> bool:
    if not isinstance(run, str):
        return False
    input_line = f'printf \'%s  %s\\n\' "$expected_sha256" "${target}" |'
    pattern = re.compile(
        r"(?m)^[ \t]*"
        + re.escape(input_line)
        + r"\r?\n[ \t]*/usr/bin/sha256sum --check --strict[ \t]*$"
    )
    return len(pattern.findall(run)) == expected_count


def _has_pinned_squawk_integrity_contract(job: Any) -> bool:
    if not isinstance(job, dict):
        return False
    if (
        job.get("name") != "Alembic Migrations"
        or job.get("runs-on") != SQUAWK_RUNNER
        or job.get("needs") != "pre-commit-check"
        or job.get("timeout-minutes") != 15
        or "if" in job
        or "strategy" in job
        or "continue-on-error" in job
    ):
        return False
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    names = [step.get("name") for step in steps if isinstance(step, dict)]
    if "Install Squawk Linter" in names:
        return False

    def named_step(name: str) -> dict[str, Any] | None:
        found = [
            step
            for step in steps
            if isinstance(step, dict) and step.get("name") == name
        ]
        return found[0] if len(found) == 1 else None

    verifier = named_step("Download and verify Squawk Linter")
    setup_python = named_step("Set up Python")
    lint = named_step("Lint Postgres Migrations (Squawk)")
    diagnostic = named_step("Collect bounded 148642dd1207 DDL evidence")
    if any(step is None for step in (verifier, setup_python, lint, diagnostic)):
        return False
    assert verifier is not None and lint is not None and diagnostic is not None
    if not (
        names.index("Download and verify Squawk Linter")
        < names.index("Set up Python")
        < names.index("Lint Postgres Migrations (Squawk)")
    ):
        return False
    for step in (verifier, lint):
        if "if" in step or "continue-on-error" in step:
            return False
    if "uses" in verifier or verifier.get("shell") != SQUAWK_VERIFY_SHELL:
        return False
    if lint.get("id") != "migration-squawk" or "continue-on-error" in diagnostic:
        return False
    if diagnostic.get("if") != SQUAWK_AUD148_CONDITION:
        return False

    verify_run = verifier.get("run")
    lint_run = lint.get("run")
    diagnostic_run = diagnostic.get("run")
    if not all(isinstance(run, str) for run in (verify_run, lint_run, diagnostic_run)):
        return False
    assert isinstance(verify_run, str)
    assert isinstance(lint_run, str)
    assert isinstance(diagnostic_run, str)

    expected_sha = f'expected_sha256="{SQUAWK_SHA256}"'
    asset_url = f'asset_url="{SQUAWK_RELEASE_URL}"'
    binary_assignment = (
        'squawk_binary_path="${RUNNER_TEMP:?RUNNER_TEMP is required}/'
        f'{SQUAWK_BINARY_SUFFIX}"'
    )
    checksum_input = 'printf \'%s  %s\\n\' "$expected_sha256" "$squawk_binary_path"'
    verify_requirements = (
        "set -euo pipefail",
        'if [[ "${RUNNER_OS:-}" != "Linux" || "${RUNNER_ARCH:-}" != "X64" ]]; then',
        "$(/usr/bin/uname -s)",
        "$(/usr/bin/uname -m)",
        'if [[ -z "${RUNNER_TEMP:-}" || "$RUNNER_TEMP" != /* ]]; then',
        expected_sha,
        asset_url,
        f'download_dir="$RUNNER_TEMP/{SQUAWK_BINARY_DIRECTORY}"',
        'binary_path="$download_dir/squawk-linux-x64"',
        'partial_path="$binary_path.partial"',
        'if [[ -e "$download_dir" || -L "$download_dir" ]]; then',
        "/usr/bin/curl --fail --silent --show-error --location",
        "--proto '=https' --proto-redir '=https' --tlsv1.2",
        '--max-redirs 5 --output "$partial_path" "$asset_url"',
        'if [[ ! -f "$partial_path" || '
        '-L "$partial_path" || ! -s "$partial_path" ]]; then',
        "/usr/bin/sha256sum --check --strict",
        'printf \'%s  %s\\n\' "$expected_sha256" "$partial_path" |',
        'printf \'%s  %s\\n\' "$expected_sha256" "$binary_path" |',
        '/usr/bin/chmod 0755 -- "$partial_path"',
    )
    if not all(fragment in verify_run for fragment in verify_requirements):
        return False
    if re.search(r"(?<!/)curl\b|(?<!/)sha256sum\b", verify_run):
        return False
    if not (
        _has_standalone_squawk_checks(verify_run, "partial_path", 1)
        and _has_standalone_squawk_checks(verify_run, "binary_path", 1)
    ):
        return False
    partial_input = 'printf \'%s  %s\\n\' "$expected_sha256" "$partial_path" |'
    final_input = 'printf \'%s  %s\\n\' "$expected_sha256" "$binary_path" |'
    partial_index = verify_run.find(partial_input)
    partial_checker = verify_run.find(
        "/usr/bin/sha256sum --check --strict", partial_index
    )
    chmod_index = verify_run.find('/usr/bin/chmod 0755 -- "$partial_path"')
    move_index = verify_run.find('/usr/bin/mv -- "$partial_path" "$binary_path"')
    final_index = verify_run.find(final_input)
    final_checker = verify_run.find("/usr/bin/sha256sum --check --strict", final_index)
    if not (
        0
        <= partial_index
        < partial_checker
        < chmod_index
        < move_index
        < final_index
        < final_checker
    ):
        return False

    if not all(fragment in lint_run for fragment in (binary_assignment, expected_sha)):
        return False
    lint_invocation = '"$squawk_binary_path" "${squawk_args[@]}" "$sql_file"'
    lint_call_index = lint_run.find(lint_invocation)
    lint_render_index = lint_run.find(
        "uv run python -m scripts.quality.render_live_alembic_sql"
    )
    lint_input_index = lint_run.rfind(checksum_input + " |", 0, lint_call_index)
    lint_checker_index = lint_run.find(
        "/usr/bin/sha256sum --check --strict", lint_input_index
    )
    if (
        "set -euo pipefail" not in lint_run
        or lint_call_index < 0
        or not (
            0
            <= lint_render_index
            < lint_input_index
            < lint_checker_index
            < lint_call_index
        )
        or lint_run.count("/usr/bin/sha256sum --check --strict") < 2
        or lint_run.count(checksum_input) < 2
        or not _has_standalone_squawk_checks(lint_run, "squawk_binary_path", 2)
        or lint_invocation not in lint_run
        or _squawk_exclusions(lint_run) != SQUAWK_EXCLUSIONS
        or "command -v squawk" in lint_run
        or 'squawk "${squawk_args[@]}"' in lint_run
    ):
        return False

    diag_version = 'AUD148_SQUAWK_VERSION="$("$squawk_binary_path" --version)"'
    diag_hash = (
        'AUD148_SQUAWK_BINARY_SHA256="$(/usr/bin/sha256sum -- '
        '"$squawk_binary_path" | /usr/bin/cut'
    )
    if not all(
        fragment in diagnostic_run
        for fragment in (binary_assignment, expected_sha, diag_version, diag_hash)
    ):
        return False
    diag_call_index = diagnostic_run.find(lint_invocation)
    version_input_index = diagnostic_run.find(checksum_input + " |")
    version_checker_index = diagnostic_run.find(
        "/usr/bin/sha256sum --check --strict", version_input_index
    )
    version_hash_index = diagnostic_run.find(diag_hash)
    version_index = diagnostic_run.find(diag_version)
    diag_input_index = diagnostic_run.rfind(checksum_input + " |", 0, diag_call_index)
    diag_checker_index = diagnostic_run.find(
        "/usr/bin/sha256sum --check --strict", diag_input_index
    )
    diagnostic_lint_log_index = diagnostic_run.find('lint_log="$(mktemp)"')
    if (
        "set -euo pipefail" not in diagnostic_run
        or not (
            0
            <= version_input_index
            < version_checker_index
            < version_hash_index
            < version_index
        )
        or not (
            0
            <= diagnostic_lint_log_index
            < diag_input_index
            < diag_checker_index
            < diag_call_index
        )
        or diagnostic_run.count("/usr/bin/sha256sum --check --strict") < 2
        or diagnostic_run.count(checksum_input) < 2
        or not _has_standalone_squawk_checks(diagnostic_run, "squawk_binary_path", 2)
        or lint_invocation not in diagnostic_run
        or _squawk_exclusions(diagnostic_run) != SQUAWK_EXCLUSIONS
        or "command -v squawk" in diagnostic_run
        or 'squawk "${squawk_args[@]}"' in diagnostic_run
    ):
        return False
    return True


def _job_with_step_update(
    job: dict[str, Any], name: str, updates: dict[str, Any]
) -> dict[str, Any]:
    changed_steps = []
    for step in job["steps"]:
        if step.get("name") == name:
            changed_steps.append({**step, **updates})
        else:
            changed_steps.append(step)
    return {**job, "steps": changed_steps}


def _suppress_squawk_checksum(run: str, occurrence: int) -> str:
    command = "/usr/bin/sha256sum --check --strict"
    matches = list(re.finditer(re.escape(command), run))
    if not 0 <= occurrence < len(matches):
        raise AssertionError("requested Squawk checksum occurrence is missing")
    match = matches[occurrence]
    return run[: match.end()] + " || true" + run[match.end() :]


def test_ci_scanner_bootstraps_are_version_pinned_and_checksum_verified() -> None:
    """Scanner builds and downloaded artifacts are pinned before execution."""

    jobs = _workflow(CI)["jobs"]

    actionlint_run = _step(jobs["actionlint"], "Install and Run actionlint")["run"]
    pre_commit = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    actionlint_repo = next(
        repo
        for repo in pre_commit["repos"]
        if repo.get("repo") == "https://github.com/rhysd/actionlint"
    )
    assert actionlint_repo["rev"] == ACTIONLINT_SOURCE_SHA

    checkout = jobs["actionlint"]["steps"][0]
    assert checkout["with"]["persist-credentials"] is False
    go_setup = _step(jobs["actionlint"], "Set up Go for source-pinned actionlint")
    assert go_setup["uses"] == (
        "actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e"
    )
    assert go_setup["with"]["go-version"] == "1.26.10"
    assert go_setup["with"]["cache"] is False

    assert f'actionlint_source_sha="{ACTIONLINT_SOURCE_SHA}"' in actionlint_run
    assert f'actionlint_archive_sha256="{ACTIONLINT_ARCHIVE_SHA256}"' in actionlint_run
    assert "raw.githubusercontent.com" not in actionlint_run
    assert "bash <(" not in actionlint_run
    assert (
        "https://api.github.com/repos/rhysd/actionlint/tarball/${actionlint_source_sha}"
        in actionlint_run
    )
    assert "sha256sum --check --strict" in actionlint_run
    assert "tar --extract --gzip" in actionlint_run
    assert 'test "$(go env GOVERSION)" = "go1.26.10"' in actionlint_run
    assert "go build -buildvcs=false -trimpath" in actionlint_run
    assert (
        "-X github.com/rhysd/actionlint.version=${actionlint_source_sha}"
        in actionlint_run
    )
    assert 'grep -Fqx "$actionlint_source_sha"' in actionlint_run
    assert '"$RUNNER_TEMP/actionlint" -color -shellcheck ""' in actionlint_run
    source_checkout = actionlint_run.index('cd "$actionlint_source_dir"')
    source_build = actionlint_run.index("go build -buildvcs=false -trimpath")
    repo_checkout = actionlint_run.index('cd "$GITHUB_WORKSPACE"')
    workflow_lint = actionlint_run.index(
        '"$RUNNER_TEMP/actionlint" -color -shellcheck ""'
    )
    assert source_checkout < source_build < repo_checkout < workflow_lint
    assert "curl --fail" in actionlint_run
    assert "--proto '=https'" in actionlint_run
    assert "--tlsv1.2" in actionlint_run

    hadolint_run = _step(jobs["dockerfile-lint"], "Run Hadolint")["run"]
    assert 'hadolint_version="2.15.1"' in hadolint_run
    assert HADOLINT_SHA256 in hadolint_run
    assert "sha256sum --check --strict" in hadolint_run
    assert "curl --fail" in hadolint_run
    assert "sudo curl" not in hadolint_run
    hadolint_lines = [line.strip() for line in hadolint_run.splitlines()]
    assert next(
        index
        for index, line in enumerate(hadolint_lines)
        if "sha256sum --check --strict" in line
    ) < next(index for index, line in enumerate(hadolint_lines) if "chmod +x" in line)

    shellcheck_install = _step(jobs["shellcheck"], "Install shellcheck")["run"]
    assert "wget -qO-" not in shellcheck_install
    assert "| tar" not in shellcheck_install
    assert 'shellcheck_version="0.11.0"' in shellcheck_install
    assert SHELLCHECK_SHA256 in shellcheck_install
    assert "sha256sum --check --strict" in shellcheck_install
    assert "curl --fail" in shellcheck_install
    shellcheck_run = _step(jobs["shellcheck"], "Run ShellCheck")["run"]
    assert "shellcheck-v0.11.0/shellcheck" in shellcheck_run


def test_security_audit_checkouts_disable_credentials_and_detect_secrets_is_locked() -> (
    None
):
    """Security jobs cannot persist a checkout token or install mutable tooling."""

    workflow = _workflow(SECURITY_AUDIT)
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            if "actions/checkout@" not in step.get("uses", ""):
                continue
            assert step.get("with", {}).get("persist-credentials") is False, job_name

    install = _step(
        workflow["jobs"]["detect-secrets-baseline"], "Install detect-secrets"
    )["run"]
    assert "python -m pip install" in install
    assert "--require-hashes" in install
    assert "--only-binary=:all:" in install
    assert "security/detect-secrets-requirements.txt" in install
    assert "pip install detect-secrets==" not in install

    requirements = DETECT_SECRETS_REQUIREMENTS.read_text(encoding="utf-8")
    assert "--only-binary=:all:" in requirements
    expected = {
        "detect-secrets==1.5.0": "e24e7b9b5a35048c313e983f76c4bd09dad89f045ff059e354f9943bf45aa060",  # pragma: allowlist secret -- wheel checksum
        "PyYAML==6.0.3": "c458b6d084f9b935061bc36216e8a69a7e293a2f1e68bf956dcd9e6cbcd143f5",  # pragma: allowlist secret -- wheel checksum
        "requests==2.34.2": "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",  # pragma: allowlist secret -- wheel checksum
        "certifi==2026.10.19": "42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b",
        "charset-normalizer==3.5.2": "34276fd796040bf0993ab33a369aa572e6979c7aab225a88893667ad8eac8f7a",
        "idna==3.20": "a7db850025b95ded1eae8a46181a1a6c56c92c96f0e2b005d9ff8dc0210cab44",  # pragma: allowlist secret -- wheel checksum
        "urllib3==2.8.0": "0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3",  # pragma: allowlist secret -- wheel checksum
    }
    requirement_lines = {
        line.split(maxsplit=1)[0]: line
        for line in requirements.splitlines()
        if line and not line.startswith("#") and not line.startswith("--")
    }
    assert set(requirement_lines) == set(expected)
    for requirement, digest in expected.items():
        line = requirement_lines[requirement]
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", line)
        assert hashes
        assert digest in hashes
        assert len(line.split()) == 1 + len(hashes)


def test_every_security_scanner_waits_for_the_shared_policy_integrity_gate() -> None:
    """PR-controlled scanner inputs are checked before any consumer runs."""

    jobs = _workflow(SECURITY_AUDIT)["jobs"]
    integrity = jobs["policy-integrity"]
    assert integrity["name"] == "Security policy integrity"
    assert integrity["permissions"] == {"contents": "read"}
    verify = _step(integrity, "Verify security policy inputs against protected base")
    assert verify["if"] == "${{ github.event_name == 'pull_request' }}"
    run = verify["run"]
    assert 'git fetch --no-tags --depth=1 origin "$BASE_SHA"' in run
    assert 'git diff --quiet "$BASE_SHA" -- "$path"' in run
    assert "BASE_REPOSITORY" in run
    assert 'BASE_REPOSITORY" != "$GITHUB_REPOSITORY"' in run
    assert 'PR_AUTHOR" != "egorribun"' in run
    for protected_input in (
        ".github/workflows",
        "scripts/osv_batch_audit.py",
        "scripts/check_dependency_audit_report.py",
        "scripts/audit_dependencies.py",
        "scripts/ci/helm_dependency_build.py",
        "scripts/quality/filter_checkov_sarif.py",
        "scripts/verify_secrets_baseline.py",
        "scripts/quality/validate_semgrep_sarif.py",
        "security/detect-secrets-requirements.txt",
        "native/rust_ext/deny.toml",
        "frontend/package.json",
        "frontend/.npmrc",
        "frontend/scripts/ensure-wasm.mjs",
        "frontend/scripts/setup-husky.cjs",
        "frontend/scripts/setup-lhci-binaries.cjs",
    ):
        assert f'"{protected_input}"' in run

    consumers = (
        "pip-audit",
        "npm-audit",
        "docker-security",
        "govulncheck",
        "sbom",
        "detect-secrets-baseline",
    )
    for consumer in consumers:
        needs = jobs[consumer].get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "policy-integrity" in needs, consumer


def test_npm_audit_install_disables_pr_lifecycle_scripts() -> None:
    """The dependency audit must not execute package lifecycle hooks."""

    job = _workflow(SECURITY_AUDIT)["jobs"]["npm-audit"]
    install = _step(job, "Install dependencies")["run"]
    assert "npm ci --ignore-scripts --no-audit --no-fund" in install


def test_weekly_cleanup_scopes_credentials_to_operation_steps() -> None:
    """Cleanup credentials must not leak into checkout or dependency setup."""

    cleanup = _workflow(WORKFLOWS / "weekly-cleanup.yml")["jobs"]["cleanup"]
    assert "DATABASE_URL" not in cleanup.get("env", {})
    assert "SECRET_KEY" not in cleanup.get("env", {})

    steps = cleanup["steps"]
    source_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Verify trusted main source"
    )
    validate_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Validate cleanup configuration"
    )
    run_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Run weekly cleanup"
    )
    assert source_index < validate_index < run_index

    secret_steps = {
        step.get("name")
        for step in steps
        if {"DATABASE_URL", "SECRET_KEY"}.intersection(step.get("env", {}))
    }
    assert secret_steps == {"Validate cleanup configuration", "Run weekly cleanup"}
    validation = steps[validate_index]
    assert validation["env"] == {
        "DATABASE_URL": "${{ secrets.DATABASE_URL }}",
        "SECRET_KEY": "${{ secrets.SECRET_KEY }}",
    }
    assert "set -euo pipefail" in validation["run"]
    assert '[[ -z "$DATABASE_URL" || -z "$SECRET_KEY" ]]' in validation["run"]


def test_standalone_security_scanners_verify_trusted_base_before_consuming_policy() -> (
    None
):
    """Standalone scanners must fail closed before reading PR-controlled config."""

    for workflow_name, job_name in STANDALONE_SECURITY_WORKFLOWS.items():
        workflow = _workflow(WORKFLOWS / workflow_name)
        job = workflow["jobs"][job_name]
        steps = job["steps"]
        checkout = next(
            step for step in steps if "actions/checkout@" in step.get("uses", "")
        )
        assert checkout.get("with", {}).get("persist-credentials") is False
        verify_index = next(
            index
            for index, step in enumerate(steps)
            if step.get("name")
            == "Verify security policy inputs against protected base"
        )
        verify = steps[verify_index]
        assert verify["if"] == "${{ github.event_name == 'pull_request' }}"
        assert verify["env"] == {
            "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
            "BASE_REPOSITORY": "${{ github.event.pull_request.base.repo.full_name }}",
            "PR_AUTHOR": "${{ github.event.pull_request.user.login }}",
        }
        run = verify["run"]
        if workflow_name == "gitleaks.yml":
            # A depth-limited fetch changes the history boundary even after a
            # full checkout; history scanning must preserve complete ancestry.
            assert checkout["with"]["fetch-depth"] == 0
            assert 'git fetch --no-tags origin "$BASE_SHA"' in run
            assert "--depth" not in run
        else:
            assert 'git fetch --no-tags --depth=1 origin "$BASE_SHA"' in run
        assert 'git diff --quiet "$BASE_SHA" -- "$path"' in run
        assert 'BASE_REPOSITORY" != "$GITHUB_REPOSITORY"' in run
        assert 'PR_AUTHOR" != "egorribun"' in run

        if workflow_name == "checkov.yml":
            scanner_index = next(
                index
                for index, step in enumerate(steps)
                if step.get("id") == "checkov_all"
            )
        else:
            scanner_index = next(
                index
                for index, step in enumerate(steps)
                if step.get("name", "").startswith(
                    (
                        "Initialize CodeQL",
                        "Dependency Review",
                        "Run Gitleaks",
                        "Run complete Gitleaks history",
                        "Run zizmor",
                    )
                )
            )
        assert verify_index < scanner_index, workflow_name


def test_security_audit_trivy_bootstrap_is_immutable_and_checksum_verified() -> None:
    """The security gate must verify Trivy before the scanner can execute."""

    job = _workflow(SECURITY_AUDIT)["jobs"]["docker-security"]
    install = _step(job, "Install checksum-pinned Trivy")
    assert install["name"] == "Install checksum-pinned Trivy"
    assert install["env"] == {
        "TRIVY_VERSION": "0.75.0",
        "TRIVY_ARCHIVE_SHA256": TRIVY_SHA256,
    }

    run = install["run"]
    assert "set -euo pipefail" in run
    assert '[[ "$TRIVY_VERSION" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]]' in run
    assert '[[ "$TRIVY_ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]]' in run
    assert "mktemp -d" in run
    assert "trap 'rm -rf -- \"$trivy_dir\"' EXIT" in run
    assert "curl --fail --silent --show-error --location" in run
    assert "--proto '=https'" in run
    assert "--tlsv1.2" in run
    assert (
        "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
        in run
    )
    assert "sha256sum --check --strict" in run
    assert "sudo install --mode 0755" in run
    assert "trivy --version" in run
    assert "aquasecurity.github.io/trivy-repo" not in run
    assert "apt-get install" not in run
    assert "wget" not in run

    lines = [line.strip() for line in run.splitlines()]
    verify_index = next(
        index
        for index, line in enumerate(lines)
        if "sha256sum --check --strict" in line
    )
    extract_index = next(
        index for index, line in enumerate(lines) if line.startswith("tar --extract")
    )
    install_index = next(
        index for index, line in enumerate(lines) if line.startswith("sudo install")
    )
    assert verify_index < extract_index < install_index


def test_cargo_udeps_bootstrap_is_immutable_and_checksum_verified() -> None:
    """Rust lint tooling must not execute mutable remote installer content."""

    jobs = _workflow(CI)["jobs"]
    install = _step(jobs["rust-lint"], "Install cargo-udeps")["run"]
    assert "set -euo pipefail" in install
    assert f'binstall_script_commit="{CARGO_BINSTALL_SCRIPT_COMMIT}"' in install
    assert f'binstall_script_sha256="{CARGO_BINSTALL_SCRIPT_SHA256}"' in install
    assert (
        'binstall_script_url="https://raw.githubusercontent.com/cargo-bins/cargo-binstall/${binstall_script_commit}/install-from-binstall-release.sh"'
        in install
    )
    assert "sha256sum --check --strict" in install
    assert "cargo binstall -y cargo-udeps@0.1.61" in install
    assert "cargo-binstall/main/" not in install


def test_ci_provenance_and_kubernetes_tooling_are_immutable_and_verified() -> None:
    """Downloaded CI tooling and remote schemas cannot drift silently."""

    jobs = _workflow(CI)["jobs"]
    provenance = _step(jobs["provenance-check"], "Install slsa-verifier")["run"]
    assert 'slsa_verifier_version="2.7.1"' in provenance
    assert SLSA_VERIFIER_SHA256 in provenance
    assert "curl --fail" in provenance
    assert "--proto '=https'" in provenance
    assert "--tlsv1.2" in provenance
    assert "sha256sum --check --strict" in provenance
    assert "curl -sSLo" not in provenance

    k8s = jobs["helm-validate"]
    kubeconform = _step(k8s, "Install kubeconform")["run"]
    assert 'kubeconform_version="0.8.0"' in kubeconform
    assert KUBECONFORM_SHA256 in kubeconform
    assert "curl --fail" in kubeconform
    assert "--proto '=https'" in kubeconform
    assert "--tlsv1.2" in kubeconform
    assert "sha256sum --check --strict" in kubeconform
    assert "curl -sSLo" not in kubeconform

    for step_name in (
        "Validate manifests with kubeconform",
        "Validate static K8s manifests with kubeconform",
    ):
        schema_validation = _step(k8s, step_name)["run"]
        assert CRD_CATALOG_COMMIT in schema_validation
        assert "/CRDs-catalog/main/" not in schema_validation

    stress = jobs["ws-stress-test"]
    k6 = _step(stress, "Install k6")["run"]
    assert 'k6_version="2.3.0"' in k6
    assert K6_SHA256 in k6
    assert "curl --fail" in k6
    assert "--proto '=https'" in k6
    assert "--tlsv1.2" in k6
    assert "sha256sum --check --strict" in k6
    assert "| tar" not in k6
    assert '"/tmp/k6-v${k6_version}-linux-amd64/k6"' in k6


def test_detect_secrets_verification_is_finding_level_and_base_bound() -> None:
    """PRs bind findings to immutable source and policy inputs."""

    job = _workflow(SECURITY_AUDIT)["jobs"]["detect-secrets-baseline"]
    fetch = _step(job, "Fetch immutable trusted source base")
    assert fetch["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "PUSH_BEFORE_SHA": "${{ github.event.before }}",
    }
    fetch_run = fetch["run"]
    assert 'pull_request) SOURCE_BASE_SHA="$PR_BASE_SHA" ;;' in fetch_run
    assert 'push) SOURCE_BASE_SHA="$PUSH_BEFORE_SHA" ;;' in fetch_run
    assert 'git fetch --no-tags --depth=1 origin "$SOURCE_BASE_SHA"' in fetch_run
    assert 'git cat-file -e "${SOURCE_BASE_SHA}^{commit}"' in fetch_run
    assert 'git show "$SOURCE_BASE_SHA:.secrets.baseline"' in fetch_run
    assert '"$RUNNER_TEMP/trusted-base-baseline.json"' in fetch_run

    scan = _step(job, "Scan repo (no baseline)")["run"]
    assert f"--exclude-files '{DETECT_SECRETS_SCAN_EXCLUSION}'" in scan
    exclusion = re.compile(DETECT_SECRETS_SCAN_EXCLUSION)
    assert exclusion.fullmatch(".secrets.baseline")
    assert exclusion.fullmatch("frontend/WASM_SOURCE_PROVENANCE.json")
    assert not exclusion.fullmatch("quality/security-false-positive-dispositions.json")
    assert not exclusion.search("frontend/WASM_SOURCE_PROVENANCE.json.bak")
    assert not exclusion.search("frontend/WASM_INVENTORY.json")
    assert not exclusion.search("frontend/src/generated.json")

    verify = _step(job, "Verify baseline has not regressed")
    assert verify["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "HEAD_SHA": "${{ github.sha }}",
        "PR_AUTHOR": "${{ github.event.pull_request.user.login }}",
        "TRUSTED_BASELINE_PATH": "${{ runner.temp }}/trusted-base-baseline.json",
    }
    verify_run = verify["run"]
    assert '--trusted-base-baseline "$TRUSTED_BASELINE_PATH"' in verify_run
    assert '--trusted-base-source-sha "$SOURCE_BASE_SHA"' in verify_run
    assert '--trusted-disposition-source-sha "$HEAD_SHA"' in verify_run
    assert (
        'if [[ "$EVENT_NAME" == "pull_request" && "$PR_AUTHOR" == "egorribun" ]]'
        in verify_run
    )
    assert (
        'git diff --quiet "$SOURCE_BASE_SHA" -- '
        "quality/security-false-positive-dispositions.json"
    ) in verify_run
    assert "--owner-authored-disposition-update" in verify_run
    assert "current_scan.json" in verify_run


def test_semgrep_is_not_a_blocking_security_audit_job() -> None:
    """The required audit graph does not duplicate the pinned pre-commit hook."""

    jobs = _workflow(SECURITY_AUDIT)["jobs"]
    assert "semgrep" not in jobs


def test_npm_failure_metadata_is_diagnostic_only_and_keeps_audit_blocking() -> None:
    workflow = _workflow(SECURITY_AUDIT)
    job = workflow["jobs"]["npm-audit"]
    gate = _step(job, "Run npm audit with allowlist")
    diagnostic = _step(job, "Report npm advisory metadata after failure")

    assert workflow["permissions"] == {"contents": "read"}
    assert job.get("continue-on-error", False) is False
    assert gate.get("continue-on-error", False) is False
    assert "scripts/audit_dependencies.py" in gate["run"]
    assert diagnostic["if"] == "${{ failure() }}"
    assert "continue-on-error" not in diagnostic
    assert diagnostic["timeout-minutes"] == 2
    assert diagnostic["shell"] == "bash"
    run = diagnostic["run"]
    assert '["audit", "--audit-level=high", "--json"]' in run
    assert "shell: false" in run
    assert "timeout: 60_000" in run
    assert 'console.log("npm advisory metadata: " + JSON.stringify({' in run
    for field in ("id", "package", "name", "severity", "url", "range"):
        assert f"{field}: scalar(" in run
    assert "console.log(result.stdout)" not in run
    assert "--fix" not in run


def test_squawk_integrity_contract_rejects_weakening_controls() -> None:
    """Pin the Linux x64 asset, trusted checker, consumers, and blocking guard."""
    job = _workflow(CI)["jobs"]["alembic-migrations"]
    assert _has_pinned_squawk_integrity_contract(job)

    verifier = _step(job, "Download and verify Squawk Linter")
    verify_run = verifier["run"]
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Download and verify Squawk Linter",
            {"run": verify_run.replace(SQUAWK_SHA256, "0" * 64, 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Download and verify Squawk Linter",
            {"run": verify_run.replace("/usr/bin/sha256sum", "sha256sum", 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Download and verify Squawk Linter",
            {"run": verify_run.replace("/usr/bin/curl", "curl", 1)},
        )
    )
    lint = _step(job, "Lint Postgres Migrations (Squawk)")
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Lint Postgres Migrations (Squawk)",
            {"run": lint["run"].replace(SQUAWK_SHA256, "0" * 64, 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Lint Postgres Migrations (Squawk)",
            {"run": lint["run"].replace("/usr/bin/sha256sum", "sha256sum", 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Lint Postgres Migrations (Squawk)",
            {
                "run": lint["run"].replace(
                    'squawk_binary_path="${RUNNER_TEMP:?RUNNER_TEMP is required}/'
                    + SQUAWK_BINARY_SUFFIX
                    + '"',
                    'squawk_binary_path="$(command -v squawk)"',
                    1,
                )
            },
        )
    )
    diagnostic = _step(job, "Collect bounded 148642dd1207 DDL evidence")
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {"run": diagnostic["run"].replace(SQUAWK_SHA256, "0" * 64, 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {"run": diagnostic["run"].replace("/usr/bin/sha256sum", "sha256sum", 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {
                "run": diagnostic["run"].replace(
                    'squawk_binary_path="${RUNNER_TEMP:?RUNNER_TEMP is required}/'
                    + SQUAWK_BINARY_SUFFIX
                    + '"',
                    'squawk_binary_path="$(command -v squawk)"',
                    1,
                )
            },
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {"if": diagnostic["if"] + " && false"},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {"if": "false"},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Download and verify Squawk Linter",
            {"if": "false"},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Download and verify Squawk Linter",
            {"continue-on-error": True},
        )
    )
    assert not _has_pinned_squawk_integrity_contract({**job, "if": "false"})
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Lint Postgres Migrations (Squawk)",
            {"if": "false"},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Lint Postgres Migrations (Squawk)",
            {"continue-on-error": True},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Download and verify Squawk Linter",
            {"run": _suppress_squawk_checksum(verify_run, 0)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Lint Postgres Migrations (Squawk)",
            {"run": _suppress_squawk_checksum(lint["run"], 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {"run": _suppress_squawk_checksum(diagnostic["run"], 1)},
        )
    )
    assert not _has_pinned_squawk_integrity_contract({**job, "continue-on-error": True})
    assert not _has_pinned_squawk_integrity_contract(
        _job_with_step_update(
            job,
            "Collect bounded 148642dd1207 DDL evidence",
            {"continue-on-error": True},
        )
    )
    assert not _has_pinned_squawk_integrity_contract({**job, "runs-on": "macos-15"})
    assert not _has_pinned_squawk_integrity_contract(
        {**job, "strategy": {"matrix": {"os": ["ubuntu-24.04", "macos-15"]}}}
    )


def test_npm_audit_uses_the_compiler_archive_bootstrap_node_version() -> None:
    """The audit runner must satisfy the existing archive producer preflight."""

    workflow = _workflow(SECURITY_AUDIT)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["workflow_call"]["inputs"]["node-version"]["default"] == "24.21.0"
    setup = _step(workflow["jobs"]["npm-audit"], "Set up Node.js")
    assert setup["with"]["node-version"] == "${{ inputs.node-version }}"

    callers = [
        (path, name, job)
        for path in WORKFLOWS.glob("*.yml")
        for name, job in _workflow(path).get("jobs", {}).items()
        if job.get("uses") == "./.github/workflows/reusable-security-audit.yml"
    ]
    assert callers, "the security audit must remain part of CI"
    for path, name, job in callers:
        assert job.get("with", {}).get("node-version", "24.21.0") == "24.21.0", (
            path.name,
            name,
        )


def test_generated_signing_keys_are_masked_before_environment_export() -> None:
    openssl = 'secret="$(openssl rand -hex 32)"'
    python = (
        "secret=\"$(python -c 'import secrets; print(secrets.token_urlsafe(48))')\""
    )
    conditional = "env.SECRET_KEY == ''"
    cases = [
        (
            CI,
            name,
            "Generate CI secret key if not configured (RZ-14-06)",
            openssl,
            None,
            conditional,
        )
        for name in (
            "compose-validate",
            "backend-type-check",
            "alembic-migrations",
            "openapi-verify",
            "verify-runtime-reqs",
            "msw-mock-drift",
        )
    ]
    cases.append(
        (
            CI,
            "quality-inventory-check",
            "Generate ephemeral audit settings",
            openssl,
            None,
            conditional,
        )
    )
    cases.extend(
        (CI, job, name, python, "bash", None)
        for job, name in (
            ("rust-ffi-asan", "Generate ephemeral ASan signing key"),
            ("rust-ffi-tsan", "Generate ephemeral TSan signing key"),
        )
    )
    cases.extend(
        (
            WORKFLOWS / "deploy.yml",
            job,
            "Generate migration secret key",
            openssl,
            None,
            None,
        )
        for job in ("validate", "rollback")
    )
    for path, job_name, step_name, generator, shell, guard in cases:
        job = _workflow(path)["jobs"][job_name]
        steps = [step for step in job["steps"] if step.get("name") == step_name]
        assert len(steps) == 1, (path.name, job_name)
        step = steps[0]
        assert step.get("shell") == shell
        assert step.get("if") == guard
        assert step["run"].splitlines() == [
            "set -euo pipefail",
            generator,
            "printf '::add-mask::%s\\n' \"$secret\"",
            'printf \'SECRET_KEY=%s\\n\' "$secret" >> "$GITHUB_ENV"',
        ], (path.name, job_name)
