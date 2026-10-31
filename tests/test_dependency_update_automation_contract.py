"""Contracts for reviewed updates to tool versions embedded in workflows."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

MANAGER_DESCRIPTIONS = {
    "Update the SQLMap workflow exact PyPI version pin": 1,
    "Update the govulncheck go install release pin": 3,
    "Update the osv-scanner release binary version and checksum together": 2,
    "Update the cargo-audit standalone Cargo CLI version": 3,
    "Update the golangci-lint CLI input to its SHA-pinned action": 2,
    "Update tested Helm 4.2 CLI inputs to azure/setup-helm": 8,
    "Update Nuclei CLI input independently of its SHA-pinned action": 1,
}

MANUAL_UPDATE_ROUTES = {
    "Trivy archive version and SHA-256 move together": {
        ".github/workflows/reusable-build-and-sign.yml": (
            "TRIVY_VERSION",
            "TRIVY_ARCHIVE_SHA256",
        ),
        "tests/test_security_hardening_workflow_contract.py": (
            "TRIVY_VERSION",
            "TRIVY_ARCHIVE_SHA256",
        ),
    },
    "Deploy-time kubectl and Helm archives are checksum-coupled": {
        ".github/workflows/deploy.yml": (
            "KUBECTL_VERSION",
            "KUBECTL_SHA256",
            "HELM_VERSION",
            "HELM_ARCHIVE_SHA256",
        ),
        "tests/test_workflow_fail_closed_contracts.py": (
            "KUBECTL_VERSION",
            "KUBECTL_SHA256",
            "HELM_VERSION",
            "HELM_ARCHIVE_SHA256",
        ),
    },
    "GHCR workflow services lack Docker datasource release timestamps": {
        ".github/workflows/nightly-full-gate.yml": (
            "ghcr.io/chrislusf/seaweedfs",
            "ghcr.io/shopify/toxiproxy",
            "@sha256:",
        ),
        "tests/test_workflow_fail_closed_contracts.py": (
            "ghcr.io/chrislusf/seaweedfs",
            "ghcr.io/shopify/toxiproxy",
            "@sha256:",
        ),
        ".github/workflows/reusable-backend-tests.yml": (
            "ghcr.io/axllent/mailpit",
            "@sha256:",
        ),
        "tests/test_mfa_mailpit_workflow_contract.py": (
            "ghcr\\.io/axllent/mailpit:v1\\.31\\.4@sha256:"
        ),
    },
    "The oasdiff npm wrapper and native binary remain a reviewed pair": {
        ".github/workflows/contract-validation.yml": ("@oasdiff-js/oasdiff-js@1.0.0",),
        "tests/test_contract_validation_workflow_contract.py": (
            "@oasdiff-js/oasdiff-js@1.0.0",
        ),
    },
    "Docker Hub image rows in tests retain exact version and digest pairs": {
        "tests/test_workflow_fail_closed_contracts.py": (
            "EXPECTED_EXTERNAL_IMAGES",
            "pgvector/pgvector:pg17@sha256:",
            "redis:7-alpine@sha256:",
            "nats:2.15.0-alpine@sha256:",
        ),
    },
    "Go pseudo-version tool installs require explicit reviewed commits": {
        ".github/workflows/nilaway.yml": (
            "go.uber.org/nilaway/cmd/nilaway@v0.0.0-20260918162853-acb8859b9031",
        ),
        ".github/workflows/reusable-go-tests.yml": (
            "github.com/avito-tech/go-mutesting/cmd/go-mutesting@v0.0.0-20261002081621-9ce5f731e321",
        ),
        "tests/test_workflow_fail_closed_contracts.py": (
            "go.uber.org/nilaway/cmd/nilaway@v0.0.0-20260918162853-acb8859b9031",
            "github.com/avito-tech/go-mutesting/cmd/go-mutesting@v0.0.0-20261002081621-9ce5f731e321",
        ),
    },
}


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _compile_renovate_regex(pattern: str) -> re.Pattern[str]:
    assert pattern.startswith("/") and pattern.endswith("/")
    return re.compile(pattern[1:-1])


def _python_regex(pattern: str) -> re.Pattern[str]:
    # Renovate uses RE2 named groups `(?<name>...)`; the rest of these patterns
    # intentionally stays within the shared RE2/Python syntax subset.
    translated = re.sub(r"\(\?<([A-Za-z][A-Za-z0-9_]*)>", r"(?P<\1>", pattern)
    return re.compile(translated)


def test_renovate_custom_managers_are_narrow_and_cooldown_bound() -> None:
    renovate = json.loads(_text("renovate.json"))
    managers = renovate["customManagers"]
    assert isinstance(managers, list)
    by_description = {manager["description"]: manager for manager in managers}

    for description, expected_matches in MANAGER_DESCRIPTIONS.items():
        manager = by_description[description]
        assert manager["customType"] == "regex"
        if (
            description
            == "Update the osv-scanner release binary version and checksum together"
        ):
            assert manager["datasourceTemplate"] == "github-release-attachments"
            assert "autoReplaceStringTemplate" not in manager
        else:
            assert manager["datasourceTemplate"] in {"pypi", "github-releases", "crate"}
            assert manager["autoReplaceStringTemplate"].count("{{{newValue}}}") == 1
        assert manager["versioningTemplate"] in {"pep440", "semver", "cargo"}
        patterns = [
            _compile_renovate_regex(value) for value in manager["managerFilePatterns"]
        ]
        matcher = _python_regex(manager["matchStrings"][0])
        sources = [
            path
            for path in (ROOT / ".github" / "workflows").glob("*.yml")
            if any(
                pattern.fullmatch(path.relative_to(ROOT).as_posix())
                for pattern in patterns
            )
        ]
        actual_matches = sum(
            len(list(matcher.finditer(path.read_text(encoding="utf-8"))))
            for path in sources
        )
        assert actual_matches == expected_matches, (
            description,
            sources,
            actual_matches,
        )

    image_manager = by_description[
        "Update matched Docker Hub service image references with their tag and digest in workflow and test files"
    ]
    image_matcher = _python_regex(image_manager["matchStrings"][0])
    source_paths = list((ROOT / ".github" / "workflows").glob("*.yml")) + list(
        (ROOT / "tests").rglob("*.py")
    )
    image_matches = [
        match
        for path in source_paths
        if any(
            _compile_renovate_regex(pattern).fullmatch(
                path.relative_to(ROOT).as_posix()
            )
            for pattern in image_manager["managerFilePatterns"]
        )
        for match in image_matcher.finditer(path.read_text(encoding="utf-8"))
    ]
    assert image_matches
    assert {match.group("depName") for match in image_matches} <= {
        "pgvector/pgvector",
        "redis",
        "nats",
    }
    assert all(
        match.group("currentDigest").startswith("sha256:") for match in image_matches
    )
    image_template = image_manager["autoReplaceStringTemplate"]
    assert "{{#if newDigest}}" in image_template
    assert "{{{newDigest}}}" in image_template
    assert "{{{currentDigest}}}" in image_template
    assert "{{{currentValue}}}" in image_template

    custom_rule = next(
        rule
        for rule in renovate["packageRules"]
        if rule.get("matchManagers") == ["custom.regex"]
    )
    assert custom_rule["minimumReleaseAge"] == "7 days"
    assert custom_rule["minimumReleaseAgeBehaviour"] == "timestamp-required"
    assert custom_rule["automerge"] is False
    assert "manual-review-required" in custom_rule["labels"]

    docker_rule = next(
        rule
        for rule in renovate["packageRules"]
        if rule.get("description")
        == "Keep workflow Docker Hub image version and digest pairs on manual security review"
    )
    assert docker_rule["matchManagers"] == ["custom.regex"]
    assert docker_rule["matchDatasources"] == ["docker"]
    assert set(docker_rule["matchPackageNames"]) == {
        "pgvector/pgvector",
        "redis",
        "nats",
    }
    assert docker_rule["minimumReleaseAge"] == "7 days"
    assert docker_rule["minimumReleaseAgeBehaviour"] == "timestamp-required"
    assert docker_rule["automerge"] is False
    assert {"security", "docker", "manual-review-required"} <= set(
        docker_rule["labels"]
    )
    assert renovate["vulnerabilityAlerts"] == {
        "enabled": True,
        "labels": ["security", "manual-cooldown-override-required"],
        "automerge": False,
        "minimumReleaseAge": None,
        "prCreation": "immediate",
    }

    helm_cap = next(
        rule
        for rule in renovate["packageRules"]
        if rule.get("matchPackageNames") == ["helm/helm"]
    )
    assert helm_cap["allowedVersions"] == "<4.3.0"
    assert helm_cap["minimumReleaseAge"] == "7 days"
    assert helm_cap["automerge"] is False


def test_dependabot_keeps_ecosystem_coverage_and_seven_day_cooldowns() -> None:
    dependabot = yaml.safe_load(_text(".github/dependabot.yml"))
    updates = dependabot["updates"]
    ecosystems = [item["package-ecosystem"] for item in updates]
    assert ecosystems.count("npm") == 1
    assert ecosystems.count("uv") == 1
    assert ecosystems.count("pip") == 1
    assert ecosystems.count("github-actions") == 1
    assert ecosystems.count("gomod") == 3
    for item in updates:
        assert item["target-branch"] == "egorribun"
        assert item["schedule"]["interval"] == "weekly"
        assert item["cooldown"]["default-days"] == 7
    npm = next(item for item in updates if item["package-ecosystem"] == "npm")
    assert set(npm["directories"]) == {"/", "/frontend"}
    uv = next(item for item in updates if item["package-ecosystem"] == "uv")
    assert {item["dependency-name"] for item in uv["ignore"]} == {
        "jsonschema",
        "types-jsonschema",
    }


def test_manual_tool_and_checksum_routes_have_live_contracts() -> None:
    for route, files in MANUAL_UPDATE_ROUTES.items():
        assert route
        for relative, required_fragments in files.items():
            source = _text(relative)
            for fragment in required_fragments:
                assert fragment in source, (route, relative, fragment)

    # GHCR values are deliberately excluded from the Docker Hub regex manager;
    # these paths retain the digest and version contract for manual paired updates.
    ghcr_images = re.findall(
        r"(?m)^\s*image:\s*(ghcr\.io/[^\s]+)",
        "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / ".github" / "workflows").glob("*.yml")
        ),
    )
    assert ghcr_images
    assert all("@sha256:" in image for image in ghcr_images)


def _osv_release_pairs(
    workflow_text: str, matcher: re.Pattern[str]
) -> list[re.Match[str]]:
    matches = list(matcher.finditer(workflow_text))
    assert len(matches) == 2
    workflow = yaml.safe_load(workflow_text)
    expected = (
        ("sbom-go", "Install osv-scanner"),
        ("vuln-gate-pr", "Install osv-scanner (pull request inventory)"),
    )
    installer_pairs = []
    for job_id, step_name in expected:
        installers = [
            step
            for step in workflow["jobs"][job_id]["steps"]
            if step.get("name") == step_name
        ]
        assert len(installers) == 1
        step_matches = list(matcher.finditer(installers[0]["run"]))
        assert len(step_matches) == 1
        installer_pairs.append(step_matches[0].groupdict())
    assert [match.groupdict() for match in matches] == installer_pairs
    pairs = {(pair["currentValue"], pair["currentDigest"]) for pair in installer_pairs}
    assert len(pairs) == 1
    return matches


def test_osv_release_manager_tracks_two_identical_version_checksum_pairs() -> None:
    renovate = json.loads(_text("renovate.json"))
    managers = [
        manager
        for manager in renovate["customManagers"]
        if manager.get("packageNameTemplate") == "google/osv-scanner"
    ]
    assert len(managers) == 1
    manager = managers[0]
    assert manager["datasourceTemplate"] == "github-release-attachments"
    assert manager["versioningTemplate"] == "semver"
    assert "autoReplaceStringTemplate" not in manager
    assert manager["managerFilePatterns"] == [r"/^\.github/workflows/sbom\.yml$/"]

    matcher = _python_regex(manager["matchStrings"][0])
    matches = _osv_release_pairs(_text(".github/workflows/sbom.yml"), matcher)
    for matched in matches:
        assert matched.group("currentValue") == "v2.6.0"
        assert re.fullmatch(r"[0-9a-f]{64}", matched.group("currentDigest"))


def test_osv_release_manager_can_reextract_a_paired_replacement() -> None:
    renovate = json.loads(_text("renovate.json"))
    manager = next(
        manager
        for manager in renovate["customManagers"]
        if manager.get("packageNameTemplate") == "google/osv-scanner"
    )
    matcher = _python_regex(manager["matchStrings"][0])
    workflow_text = _text(".github/workflows/sbom.yml")
    matches = _osv_release_pairs(workflow_text, matcher)
    current_version = matches[0].group("currentValue")
    current_digest = matches[0].group("currentDigest")
    next_version = "v9.8.7"
    next_digest = hashlib.sha256(b"synthetic future release").hexdigest()

    def replace_pair(original: re.Match[str]) -> str:
        return (
            original.group(0)
            .replace(current_version, next_version, 1)
            .replace(current_digest, next_digest, 1)
        )

    updated = matcher.sub(replace_pair, workflow_text)
    rematched = _osv_release_pairs(updated, matcher)
    assert len(rematched) == len(matches) == 2
    for matched in rematched:
        assert matched.group("currentValue") == next_version
        assert matched.group("currentDigest") == next_digest


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-main",
        "missing-pr",
        "duplicate-main",
        "extra-job",
        "version-drift",
        "digest-drift",
        "malformed-version",
        "malformed-digest",
    ),
)
def test_osv_release_pair_inventory_rejects_missing_extra_or_drift(
    mutation: str,
) -> None:
    renovate = json.loads(_text("renovate.json"))
    manager = next(
        manager
        for manager in renovate["customManagers"]
        if manager.get("packageNameTemplate") == "google/osv-scanner"
    )
    matcher = _python_regex(manager["matchStrings"][0])
    workflow = yaml.safe_load(_text(".github/workflows/sbom.yml"))
    # Keep each literal Renovate pair intact; prove serialization is healthy
    # before any rejected mutation can satisfy its negative oracle.
    _osv_release_pairs(yaml.safe_dump(workflow, sort_keys=False, width=4096), matcher)
    main_steps = workflow["jobs"]["sbom-go"]["steps"]
    pr_steps = workflow["jobs"]["vuln-gate-pr"]["steps"]
    main_install = next(
        step for step in main_steps if step.get("name") == "Install osv-scanner"
    )
    pr_install = next(
        step
        for step in pr_steps
        if step.get("name") == "Install osv-scanner (pull request inventory)"
    )
    original = matcher.search(pr_install["run"])
    assert original is not None
    if mutation == "missing-main":
        main_steps.remove(main_install)
    elif mutation == "missing-pr":
        pr_steps.remove(pr_install)
    elif mutation == "duplicate-main":
        main_steps.append(dict(main_install))
    elif mutation == "extra-job":
        workflow["jobs"]["unreviewed-producer"] = {"steps": [dict(main_install)]}
    else:
        field = "currentValue" if "version" in mutation else "currentDigest"
        old_value = original.group(field)
        if mutation == "version-drift":
            new_value = "v9.8.7"
        elif mutation == "digest-drift":
            new_value = hashlib.sha256(b"synthetic different release").hexdigest()
        else:
            new_value = "invalid"
        assert new_value != old_value
        pr_install["run"] = pr_install["run"].replace(old_value, new_value, 1)

    with pytest.raises(AssertionError):
        _osv_release_pairs(
            yaml.safe_dump(workflow, sort_keys=False, width=4096), matcher
        )
