import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def _read_toml(relative_path: str) -> dict[str, object]:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _read_renovate() -> dict[str, object]:
    return json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))


def _package_rules(renovate: dict[str, object]) -> list[dict[str, object]]:
    rules = renovate["packageRules"]
    assert isinstance(rules, list)
    assert all(isinstance(rule, dict) for rule in rules)
    return rules


def test_dependency_resolution_policy_enforces_cooldown_and_security_visibility() -> (
    None
):
    pyproject = _read_toml("pyproject.toml")
    tool = pyproject["tool"]
    assert isinstance(tool, dict)
    uv = tool["uv"]
    assert isinstance(uv, dict)
    assert uv.get("exclude-newer") == "7 days"

    renovate = _read_renovate()
    assert renovate["osvVulnerabilityAlerts"] is True
    vulnerability_alerts = renovate["vulnerabilityAlerts"]
    assert isinstance(vulnerability_alerts, dict)
    assert vulnerability_alerts["enabled"] is True

    rules = _package_rules(renovate)
    security_rules = [
        rule for rule in rules if rule.get("matchCategories") == ["security"]
    ]
    assert len(security_rules) == 1
    security_rule = security_rules[0]
    assert rules[-1] is security_rule
    assert security_rule["minimumReleaseAge"] is False
    assert security_rule["automerge"] is False
    assert security_rule["labels"] == [
        "security",
        "manual-cooldown-override-required",
    ]
    assert isinstance(security_rule.get("description"), str)
    assert security_rule["description"]
    assert any(rule.get("matchDatasources") == ["pypi"] for rule in rules[:-1])
    assert all(rule.get("minimumReleaseAge") == "7 days" for rule in rules[:-1])


def test_cooldown_lock_metadata_and_emergency_runbook_are_auditable() -> None:
    lock_options = _read_toml("uv.lock").get("options")
    assert isinstance(lock_options, dict)
    assert "exclude-newer" in lock_options
    assert lock_options["exclude-newer-span"] == "P7D"

    runbook = (ROOT / "docs" / "DEPENDENCY_COOLDOWN_EMERGENCY.md").read_text(
        encoding="utf-8"
    )
    assert TARGETED_EMERGENCY_COMMAND in runbook
    assert "minimumReleaseAge: false" in runbook
    for audit_field in REQUIRED_AUDIT_FIELDS:
        assert audit_field in runbook
    for prohibited_bypass in PROHIBITED_BYPASSES:
        assert f"Do not use `{prohibited_bypass}`" in runbook
