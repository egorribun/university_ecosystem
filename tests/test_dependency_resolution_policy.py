import json
import re
import tomllib
from pathlib import Path

import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "renovate.json").exists() and (ROOT.parent / "renovate.json").exists():
    ROOT = ROOT.parent

TARGETED_EMERGENCY_COMMAND = (
    'uv lock --upgrade-package "<package>" --exclude-newer-package "<package>=false"'
)
PROHIBITED_BYPASSES = (
    "--exclude-newer false",
    "UV_EXCLUDE_NEWER=false",
    "Semgrep suppression",
    "SKIP=semgrep",
    "--no-verify",
)
REQUIRED_AUDIT_FIELDS = (
    "advisory ID (CVE/GHSA/OSV)",
    "exact package",
    "fixed version",
    "normal PR",
    "security reviewer",
    "uv lock --check",
    "review the `uv.lock` diff",
    "normal test/vulnerability-gate evidence",
)
RENOVATE_PRE_COMMIT_HOOK = """  - repo: https://github.com/renovatebot/pre-commit-hooks
    rev: 44.142.1 # 79024b1a7a706341245d73344bf413ee29bf5013
    hooks:
      - id: renovate-config-validator
        args: [--strict]
        pass_filenames: false
"""
RENOVATE_VALIDATOR_COMMAND = "pre-commit run renovate-config-validator --all-files"
CI_RENOVATE_VALIDATOR_COMMAND = (
    "python -m pre_commit run renovate-config-validator --all-files"
)

# Local workspace members are versioned with the repository, not independently
# resolved from PyPI.  Every external production requirement must carry an
# explicit upper bound; adding an exception requires a reviewed policy change.
REVIEWED_UNBOUNDED_DEPENDENCIES = frozenset()


def _read_toml(relative_path: str) -> dict[str, object]:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _read_renovate() -> dict[str, object]:
    return json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))


def _package_rules(renovate: dict[str, object]) -> list[dict[str, object]]:
    rules = renovate["packageRules"]
    assert isinstance(rules, list)
    assert all(isinstance(rule, dict) for rule in rules)
    return rules


def _make_target_body(source: str, target_name: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(target_name)}:\s*\n(?P<body>(?:\t.*(?:\n|$))*)",
        source,
    )
    assert match is not None, f"missing {target_name} target"
    return match.group("body")


def _workflow_named_step(source: str, step_name: str) -> str:
    marker = f"      - name: {step_name}\n"
    start = source.find(marker)
    assert start >= 0, f"missing {step_name} workflow step"
    end = source.find("\n      - name:", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def test_dependency_resolution_policy_enforces_cooldown_and_security_visibility() -> (
    None
):
    pyproject = _read_toml("pyproject.toml")
    tool = pyproject["tool"]
    assert isinstance(tool, dict)
    uv = tool["uv"]
    assert isinstance(uv, dict)
    assert uv.get("required-version") == "==0.12.23"
    assert uv.get("exclude-newer") == "7 days"
    assert uv.get("exclude-newer-package") == {"certifi": "2026-10-20T02:24:17Z"}
    assert "certifi==2026.10.19" in uv["constraint-dependencies"]

    renovate = _read_renovate()
    assert renovate["osvVulnerabilityAlerts"] is True
    rules = _package_rules(renovate)
    assert all(rule["minimumReleaseAge"] == "7 days" for rule in rules)
    assert not any(rule.get("matchCategories") == ["security"] for rule in rules)
    assert any(rule.get("matchDatasources") == ["pypi"] for rule in rules)
    assert renovate["vulnerabilityAlerts"] == {
        "enabled": True,
        "labels": ["security", "manual-cooldown-override-required"],
        "automerge": False,
        "minimumReleaseAge": None,
        "prCreation": "immediate",
    }


def test_httpx2_requirement_stays_on_the_patched_security_floor() -> None:
    """The declared floor must not permit versions with known HTTPX2 CVEs."""
    pyproject = _read_toml("pyproject.toml")
    dependency_groups = pyproject["dependency-groups"]
    assert isinstance(dependency_groups, dict)
    dev_dependencies = dependency_groups["dev"]
    assert isinstance(dev_dependencies, list)
    httpx_requirement = next(
        (
            entry
            for entry in dev_dependencies
            if isinstance(entry, str) and entry.startswith("httpx2")
        ),
        None,
    )
    assert httpx_requirement == "httpx2>=2.12.0,<3"


def test_precommit_mypy_installs_the_declared_psycopg_driver() -> None:
    pyproject = _read_toml("pyproject.toml")
    project = pyproject["project"]
    assert isinstance(project, dict)
    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)
    production = next(
        Requirement(value)
        for value in dependencies
        if isinstance(value, str) and Requirement(value).name == "psycopg"
    )

    pre_commit = yaml.safe_load(_read_text(".pre-commit-config.yaml"))
    mypy_repo = next(
        repo
        for repo in pre_commit["repos"]
        if repo["repo"] == "https://github.com/pre-commit/mirrors-mypy"
    )
    mypy_hook = next(hook for hook in mypy_repo["hooks"] if hook["id"] == "mypy")
    isolated = next(
        Requirement(value)
        for value in mypy_hook["additional_dependencies"]
        if Requirement(value).name == "psycopg"
    )
    assert isolated.extras == production.extras
    assert isolated.specifier == production.specifier


def test_renovate_validator_contract_is_pinned_and_blocking() -> None:
    pre_commit_text = _read_text(".pre-commit-config.yaml")
    assert RENOVATE_PRE_COMMIT_HOOK in pre_commit_text
    pre_commit_config = yaml.safe_load(pre_commit_text)
    renovate_repo = next(
        repo
        for repo in pre_commit_config["repos"]
        if repo["repo"] == "https://github.com/renovatebot/pre-commit-hooks"
    )
    assert renovate_repo["rev"] == "44.142.1"
    renovate_hook = next(
        hook
        for hook in renovate_repo["hooks"]
        if hook["id"] == "renovate-config-validator"
    )
    assert renovate_hook["args"] == ["--strict"]
    assert renovate_hook["pass_filenames"] is False

    makefile = _read_text("Makefile")
    assert (
        _make_target_body(makefile, "renovate-config-validate").strip()
        == RENOVATE_VALIDATOR_COMMAND
    )

    workflow_renovate = _read_text(".github/workflows/renovate-config-validation.yml")
    parsed_workflow = yaml.safe_load(workflow_renovate)
    validator_job = parsed_workflow["jobs"]["renovate-validation"]
    workflow_steps = validator_job["steps"]
    validator_step = next(
        step
        for step in workflow_steps
        if step.get("name") == "Run strict Renovate validator"
    )
    assert validator_step["run"].splitlines() == [
        "set -euo pipefail",
        "pre-commit run renovate-config-validator --all-files --show-diff-on-failure",
    ]
    assert "uses" not in validator_step
    assert "pre-commit/action" not in workflow_renovate
    assert "continue-on-error" not in validator_job

    action_refs = [
        step["uses"]
        for step in workflow_steps
        if isinstance(step, dict) and "uses" in step
    ]
    assert action_refs
    assert all(
        re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action_ref) for action_ref in action_refs
    )

    cache_step = next(
        step
        for step in workflow_steps
        if step.get("name") == "Restore fast pre-commit environments"
    )
    assert (
        cache_step["uses"] == "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
    )
    assert cache_step["with"]["path"] == "~/.cache/pre-commit"
    assert (
        cache_step["with"]["key"]
        == "pre-commit-fast-v2-${{ runner.os }}-${{ env.pythonLocation }}-${{ hashFiles('.pre-commit-config.yaml', 'uv.lock') }}"
    )

    install_step = next(
        step
        for step in workflow_steps
        if step.get("name") == "Install hash-verified pre-commit runner"
    )
    install_run = install_step["run"]
    assert "uv export --frozen" in install_run
    assert "--only-group ci-precommit-runner" in install_run
    assert "--require-hashes" in install_run
    assert "--only-binary=:all:" in install_run
    assert 'test "$(pre-commit --version)" = "pre-commit 4.6.2"' in install_run

    lock_check = next(
        step
        for step in workflow_steps
        if step.get("name") == "Verify uv.lock is up to date"
    )
    assert lock_check["run"] == "uv lock --check"

    assert "permissions:\n  contents: read" in workflow_renovate
    assert "on:\n  push:\n    branches: [main]\n  pull_request:" in workflow_renovate
    assert (
        "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
        in workflow_renovate
    )
    assert (
        "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
        in workflow_renovate
    )

    workflow_ci = _read_text(".github/workflows/ci.yml")
    assert "Validate Renovate configuration (strict)" not in workflow_ci

    ci_success = workflow_ci.partition("  ci-success:\n")[2]
    assert "${{ needs.pre-commit-check.result }}" in ci_success


def test_cooldown_lock_metadata_and_emergency_runbook_are_auditable() -> None:
    lock_options = _read_toml("uv.lock").get("options")
    assert isinstance(lock_options, dict)
    assert "exclude-newer" in lock_options
    assert lock_options["exclude-newer-span"] == "P7D"
    assert lock_options.get("exclude-newer-package") == {
        "certifi": "2026-10-20T02:24:17Z"
    }
    lock = _read_toml("uv.lock")
    packages = [package for package in lock["package"] if package["name"] == "certifi"]
    assert len(packages) == 1
    assert packages[0]["version"] == "2026.10.19"
    assert {"name": "certifi", "specifier": "==2026.10.19"} in lock["manifest"][
        "constraints"
    ]

    runbook = _read_text("docs/DEPENDENCY_COOLDOWN_EMERGENCY.md")
    assert TARGETED_EMERGENCY_COMMAND in runbook
    assert "`vulnerabilityAlerts`" in runbook
    assert "`minimumReleaseAge: null`" in runbook
    assert "minimumReleaseAge: false" not in runbook
    for audit_field in REQUIRED_AUDIT_FIELDS:
        assert audit_field in runbook
    for prohibited_bypass in PROHIBITED_BYPASSES:
        assert f"Do not use `{prohibited_bypass}`" in runbook


def test_all_external_production_dependencies_have_upper_bounds() -> None:
    """Prevent future lock refreshes from silently widening major versions."""

    pyproject = _read_toml("pyproject.toml")
    dependencies = pyproject["project"]["dependencies"]
    assert isinstance(dependencies, list)

    unbounded: set[str] = set()
    for entry in dependencies:
        assert isinstance(entry, str)
        requirement = Requirement(entry)
        if requirement.name == "rust_ext":
            continue
        if not any(specifier.operator == "<" for specifier in requirement.specifier):
            unbounded.add(requirement.name)

    unexpected = unbounded - REVIEWED_UNBOUNDED_DEPENDENCIES
    assert not unexpected, (
        "External production dependencies require explicit upper bounds; "
        f"unbounded={sorted(unbounded)}, reviewed={sorted(REVIEWED_UNBOUNDED_DEPENDENCIES)}"
    )


def test_dependency_upper_bound_policy_is_recorded_in_adr_index() -> None:
    """The SEC-09 decision and its exception policy must be discoverable."""

    adr_path = ROOT / "docs/adr/ADR-035-python-dependency-compatibility-policy.md"
    index_path = ROOT / "docs/adr/README.md"
    assert adr_path.is_file()
    adr = adr_path.read_text(encoding="utf-8").lower()
    assert "status" in adr and "accepted" in adr
    for heading in ("## context", "## decision", "## consequences", "## policy"):
        assert heading in adr
    assert "upper bound" in adr
    assert "reviewed exception" in adr
    index = index_path.read_text(encoding="utf-8")
    assert "ADR-035" in index
    assert "Python Dependency Compatibility Policy" in index


def test_sqlalchemy_20_uses_inline_typing_without_removed_mypy_plugin() -> None:
    pyproject = _read_toml("pyproject.toml")
    dependencies = pyproject["project"]["dependencies"]
    assert isinstance(dependencies, list)
    sqlalchemy = next(
        Requirement(value)
        for value in dependencies
        if isinstance(value, str) and Requirement(value).name == "sqlalchemy"
    )
    assert sqlalchemy.specifier.contains("2.0.54")
    assert not sqlalchemy.specifier.contains("2.1.0")

    mypy = pyproject["tool"]["mypy"]
    assert isinstance(mypy, dict)
    plugins = mypy["plugins"]
    assert isinstance(plugins, list)
    assert "sqlalchemy.ext.mypy.plugin" not in plugins
