import json
import re
import tomllib
from pathlib import Path

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
    rev: 43.268.4 # ece9d8611e4e7da8cbcf7ea28039ec7928316032
    hooks:
      - id: renovate-config-validator
        args: [--strict]
        pass_filenames: false
"""
RENOVATE_VALIDATOR_COMMAND = "pre-commit run renovate-config-validator --all-files"
CI_RENOVATE_VALIDATOR_COMMAND = (
    "python -m pre_commit run renovate-config-validator --all-files"
)


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
    assert uv.get("exclude-newer") == "7 days"
    assert uv.get("exclude-newer-package") == {
        "cryptography": "2026-08-01T00:00:00Z",
        "h2": "2026-08-04T00:00:00Z",
        "mcp": "2026-08-04T00:00:00Z",
        "pyopenssl": "2026-08-02T00:00:00Z",
    }

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


def test_renovate_validator_contract_is_pinned_and_blocking() -> None:
    pre_commit_config = _read_text(".pre-commit-config.yaml")
    assert RENOVATE_PRE_COMMIT_HOOK in pre_commit_config

    makefile = _read_text("Makefile")
    assert (
        _make_target_body(makefile, "renovate-config-validate").strip()
        == RENOVATE_VALIDATOR_COMMAND
    )

    workflow_renovate = _read_text(".github/workflows/renovate-config-validation.yml")
    expected_validator_step = (
        "      - name: Run strict Renovate validator\n"
        "        uses: pre-commit/action@2c7b3805fd2a0fd8c1884dcaebf91fc102a13ecd # v3.0.1\n"
        "        with:\n"
        "          extra_args: renovate-config-validator --all-files\n"
    )
    validator_step = _workflow_named_step(
        workflow_renovate, "Run strict Renovate validator"
    )
    assert expected_validator_step in validator_step
    assert "continue-on-error" not in validator_step

    # Verify triggers, permissions, and SHA-pinned checkout/setup actions
    assert "permissions:\n  contents: read" in workflow_renovate
    assert "on:\n  push:\n  pull_request:" in workflow_renovate
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
    assert "      - pre-commit-check" in ci_success
    assert '"${{ needs.pre-commit-check.result }}"' in ci_success


def test_cooldown_lock_metadata_and_emergency_runbook_are_auditable() -> None:
    lock_options = _read_toml("uv.lock").get("options")
    assert isinstance(lock_options, dict)
    assert "exclude-newer" in lock_options
    assert lock_options["exclude-newer-span"] == "P7D"

    runbook = _read_text("docs/DEPENDENCY_COOLDOWN_EMERGENCY.md")
    assert TARGETED_EMERGENCY_COMMAND in runbook
    assert "`vulnerabilityAlerts`" in runbook
    assert "`minimumReleaseAge: null`" in runbook
    assert "minimumReleaseAge: false" not in runbook
    for audit_field in REQUIRED_AUDIT_FIELDS:
        assert audit_field in runbook
    for prohibited_bypass in PROHIBITED_BYPASSES:
        assert f"Do not use `{prohibited_bypass}`" in runbook
