"""Behavioral evidence for scanner and policy workflow failure boundaries."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.quality.verify_dependency_review_scope import (
    verify_policy_delta,
    verify_policy_scope,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-security-audit.yml"
DEPENDENCY_REVIEW = ROOT / ".github" / "dependency-review-config.yml"
pytest_plugins = ("pytester",)


@pytest.mark.parametrize(
    "suppression",
    [
        "allow-ghsas: [GHSA-aaaa-bbbb-cccc]",
        '"allow-ghsas":\n  - GHSA-aaaa-bbbb-cccc',
        "allow-ghsas: &advisories [GHSA-aaaa-bbbb-cccc]",
        '"allow-\\x67hsas": [GHSA-aaaa-bbbb-cccc]',
    ],
)
def test_aud479_global_advisory_suppressions_fail_even_on_existing_base(
    suppression: str,
) -> None:
    config = DEPENDENCY_REVIEW.read_text(encoding="utf-8") + "\n" + suppression + "\n"
    # Both encodings are ordinary YAML lists as consumed by the action.
    assert yaml.safe_load(config)["allow-ghsas"] == ["GHSA-aaaa-bbbb-cccc"]
    with pytest.raises(ValueError):
        # Match preflight's scope-then-delta sequence with an unchanged base.
        verify_policy_scope(config)
        verify_policy_delta(config, config)


def test_aud479_rejects_duplicate_keys_even_when_yaml_uses_the_last_value() -> None:
    config = DEPENDENCY_REVIEW.read_text(encoding="utf-8") + "\nlicense-check: true\n"
    assert yaml.safe_load(config)["license-check"] is True
    with pytest.raises(ValueError):
        verify_policy_scope(config)


def test_aud479_an_explicit_empty_ghsa_list_remains_valid() -> None:
    config = DEPENDENCY_REVIEW.read_text(encoding="utf-8") + "\nallow-ghsas: []\n"
    verify_policy_scope(config)


def test_aud479_rejects_unrecognized_list_indentation() -> None:
    original = DEPENDENCY_REVIEW.read_text(encoding="utf-8")
    config = original.replace("\n  - ", "\n    - ")
    assert yaml.safe_load(config) == yaml.safe_load(original)
    with pytest.raises(ValueError):
        verify_policy_scope(config)


def test_aud479_rejects_non_scalar_check_switch() -> None:
    original = DEPENDENCY_REVIEW.read_text(encoding="utf-8")
    config = original.replace("license-check: true", "license-check: [true]")
    assert yaml.safe_load(config)["license-check"] == [True]
    with pytest.raises(ValueError):
        verify_policy_scope(config)


@pytest.mark.parametrize("item", ["name: MIT", "false", "- MIT"])
def test_aud479_rejects_list_items_that_yaml_interprets_as_non_strings(
    item: str,
) -> None:
    original = DEPENDENCY_REVIEW.read_text(encoding="utf-8")
    config = original.replace("  - MIT\n", f"  - {item}\n", 1)
    assert config != original
    assert not isinstance(yaml.safe_load(config)["allow-licenses"][0], str)
    with pytest.raises(ValueError):
        verify_policy_scope(config)


def _step(job: str, name: str, workflow_path: Path = WORKFLOW) -> dict[str, Any]:
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    return next(
        step for step in workflow["jobs"][job]["steps"] if step.get("name") == name
    )


def _bash() -> str:
    if os.name == "nt":
        candidate = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Git"
            / "bin"
            / "bash.exe"
        )
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which("bash")
    if not executable:
        pytest.fail("Bash is required to exercise the GitHub Actions shell blocks")
    return executable


def _run(
    pytester: pytest.Pytester, script: str, prefix: str, **values: str
) -> pytest.RunResult:
    with pytest.MonkeyPatch.context() as environment:
        for name, value in values.items():
            environment.setenv(name, value)
        return pytester.run(
            _bash(),
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            prefix + "\n" + script,
            timeout=10,
        )


GO_STUBS = r"""
go() {
  if [[ "$1" == list && "$2" == -m ]]; then
    case "$AUD_SCENARIO" in
      module_list_error) return 2 ;;
      module_list_partial) printf '%s\n' module-a; return 2 ;;
      empty_module_list) return 0 ;;
      blank_module_path) printf '%s\n' module-a '' module-b; return 0 ;;
      module_with_space) printf '%s\n' 'module with space' module-b; return 0 ;;
      *) printf '%s\n' module-a module-b; return 0 ;;
    esac
  fi
  if [[ "$1" == list && "$2" == -C ]]; then
    if [[ "$AUD_SCENARIO" == empty_all_packages ]]; then
      return 0
    fi
    if [[ "$AUD_SCENARIO" == package_list_first_error && "$3" == module-a ]]; then
      return 2
    fi
    if [[ "$3" == module-b ]]; then
      case "$AUD_SCENARIO" in
        package_list_error) return 2 ;;
        package_list_partial) printf '%s\n' example/partial; return 2 ;;
        package_list_empty) return 0 ;;
      esac
    fi
    printf '%s\n' example/package
    return 0
  fi
  printf '%s\n' 'unexpected go call' >&2
  return 99
}
govulncheck() {
  printf 'scanned:%s\n' "$2"
  if [[ "$AUD_SCENARIO" == scanner_error && "$2" == module-b ]]; then
    return 3
  fi
}
"""


def _govulncheck(pytester: pytest.Pytester, scenario: str) -> pytest.RunResult:
    script = _step("govulncheck", "Run govulncheck on all Go modules")["run"]
    return _run(pytester, script, GO_STUBS, AUD_SCENARIO=scenario)


def test_aud485_scans_every_populated_module_on_success(
    pytester: pytest.Pytester,
) -> None:
    result = _govulncheck(pytester, "success")
    assert result.ret == 0, result.stderr.str()
    assert "scanned:module-a" in result.stdout.str()
    assert "scanned:module-b" in result.stdout.str()


def test_aud485_allows_an_empty_module_after_successful_package_discovery(
    pytester: pytest.Pytester,
) -> None:
    result = _govulncheck(pytester, "package_list_empty")
    assert result.ret == 0, result.stderr.str()
    assert "scanned:module-a" in result.stdout.str()
    assert "scanned:module-b" not in result.stdout.str()


def test_aud485_module_paths_with_spaces_are_kept_intact(
    pytester: pytest.Pytester,
) -> None:
    result = _govulncheck(pytester, "module_with_space")
    assert result.ret == 0, result.stderr.str()
    assert "scanned:module with space" in result.stdout.str()
    assert "scanned:module-b" in result.stdout.str()


@pytest.mark.parametrize(
    "scenario",
    [
        "module_list_error",
        "module_list_partial",
        "empty_module_list",
        "blank_module_path",
        "empty_all_packages",
        "package_list_error",
        "package_list_partial",
        "scanner_error",
    ],
)
def test_aud485_incomplete_discovery_and_scanner_failure_are_blocking(
    pytester: pytest.Pytester, scenario: str
) -> None:
    result = _govulncheck(pytester, scenario)
    assert result.ret != 0, (scenario, result.stdout.str(), result.stderr.str())


def test_aud485_continues_to_scan_after_a_package_discovery_error(
    pytester: pytest.Pytester,
) -> None:
    result = _govulncheck(pytester, "package_list_first_error")
    assert result.ret != 0
    assert "scanned:module-b" in result.stdout.str()


POLICY_STUBS = r"""
git() {
  if [[ "$1" == fetch ]]; then
    printf '%s\n' 'git-invoked'
  elif [[ "$1" == diff && "$AUD_DIRTY" == yes ]]; then
    return 1
  fi
  return 0
}
"""

POLICY_STEPS = [
    ("reusable-security-audit.yml", "policy-integrity"),
    ("reusable-security-audit.yml", "pip-audit"),
    ("dependency-review.yml", "dependency-review"),
    ("checkov.yml", "checkov"),
    ("codeql.yml", "analyze"),
    ("gitleaks.yml", "gitleaks"),
    ("zizmor.yml", "zizmor"),
]


def _policy(
    pytester: pytest.Pytester,
    workflow_name: str,
    job: str,
    head_repository: str,
    *,
    base_sha: str = "a" * 40,
    base_repository: str = "owner/project",
    author: str = "egorribun",
    dirty: str = "no",
) -> pytest.RunResult:
    script = _step(
        job,
        "Verify security policy inputs against protected base",
        ROOT / ".github" / "workflows" / workflow_name,
    )["run"]
    return _run(
        pytester,
        script,
        POLICY_STUBS,
        BASE_SHA=base_sha,
        BASE_REPOSITORY=base_repository,
        GITHUB_REPOSITORY="owner/project",
        HEAD_REPOSITORY=head_repository,
        PR_AUTHOR=author,
        AUD_DIRTY=dirty,
    )


@pytest.mark.parametrize(("workflow_name", "job"), POLICY_STEPS)
def test_aud487_policy_step_binds_actual_pull_request_head_repository(
    workflow_name: str, job: str
) -> None:
    step = _step(
        job,
        "Verify security policy inputs against protected base",
        ROOT / ".github" / "workflows" / workflow_name,
    )
    assert (
        step["env"].get("HEAD_REPOSITORY")
        == "${{ github.event.pull_request.head.repo.full_name }}"
    )


@pytest.mark.parametrize(("workflow_name", "job"), POLICY_STEPS)
def test_aud487_same_repository_and_immutable_base_are_accepted(
    pytester: pytest.Pytester, workflow_name: str, job: str
) -> None:
    result = _policy(pytester, workflow_name, job, "owner/project")
    assert result.ret == 0, result.stderr.str()
    assert "git-invoked" in result.stdout.str()


@pytest.mark.parametrize("head_repository", ["other/project", ""])
@pytest.mark.parametrize(("workflow_name", "job"), POLICY_STEPS)
def test_aud487_cross_repository_and_missing_head_are_rejected_before_fetch(
    pytester: pytest.Pytester, workflow_name: str, job: str, head_repository: str
) -> None:
    result = _policy(pytester, workflow_name, job, head_repository)
    assert result.ret != 0, (result.stdout.str(), result.stderr.str())
    assert "git-invoked" not in result.stdout.str()


@pytest.mark.parametrize(("workflow_name", "job"), POLICY_STEPS)
def test_aud487_malformed_base_sha_is_rejected_before_fetch(
    pytester: pytest.Pytester, workflow_name: str, job: str
) -> None:
    result = _policy(pytester, workflow_name, job, "owner/project", base_sha="bad")
    assert result.ret != 0
    assert "git-invoked" not in result.stdout.str()


@pytest.mark.parametrize(("workflow_name", "job"), POLICY_STEPS)
def test_aud487_foreign_base_is_rejected_before_fetch(
    pytester: pytest.Pytester, workflow_name: str, job: str
) -> None:
    result = _policy(
        pytester, workflow_name, job, "owner/project", base_repository="other/project"
    )
    assert result.ret != 0
    assert "git-invoked" not in result.stdout.str()


@pytest.mark.parametrize(("workflow_name", "job"), POLICY_STEPS)
@pytest.mark.parametrize(("author", "expected"), [("egorribun", 0), ("other", 1)])
def test_aud487_existing_owner_rule_remains_enforced(
    pytester: pytest.Pytester, workflow_name: str, job: str, author: str, expected: int
) -> None:
    result = _policy(
        pytester, workflow_name, job, "owner/project", author=author, dirty="yes"
    )
    assert (result.ret == 0) == (expected == 0), result.stderr.str()
