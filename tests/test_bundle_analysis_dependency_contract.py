"""The bundle analyzer must install its parser without bypassing WASM checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "reusable-frontend-tests.yml"
)
ROOT = Path(__file__).resolve().parents[1]


def _workflow() -> dict[str, Any]:
    value = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _step(job: dict[str, Any], name: str) -> tuple[int, dict[str, Any]]:
    matches = [
        (index, step)
        for index, step in enumerate(job["steps"])
        if isinstance(step, dict) and step.get("name") == name
    ]
    assert len(matches) == 1, f"Expected exactly one {name!r} step"
    return matches[0]


def test_bundle_analysis_downloads_both_conditional_wasm_artifacts_as_build_does() -> (
    None
):
    jobs = _workflow()["jobs"]
    build = jobs["build"]
    analysis = jobs["bundle-analysis"]
    assert analysis["needs"] == "build"
    assert build["needs"] == "wasm-build"
    assert analysis["defaults"] == build["defaults"]

    checkout_indices = [
        index
        for index, step in enumerate(analysis["steps"])
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkout_indices) == 1
    checkout_index = checkout_indices[0]
    assert analysis["steps"][checkout_index]["with"]["persist-credentials"] is False
    install_index, _ = _step(analysis, "Install dependencies")
    expected = {
        "Download immutable WASM modules": {
            "if": "${{ inputs.wasm-artifact-id == '' && inputs.wasm-artifact-name == '' && inputs.wasm-artifact-digest == '' }}",
            "with": {
                "name": "frontend-wasm-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}",
                "path": "${{ inputs.working-directory }}",
            },
        },
        "Download shared immutable WASM modules": {
            "if": "${{ inputs.wasm-artifact-id != '' && inputs.wasm-artifact-name != '' && inputs.wasm-artifact-digest != '' }}",
            "with": {
                "artifact-ids": "${{ inputs.wasm-artifact-id }}",
                "path": "${{ inputs.working-directory }}",
            },
        },
    }
    for name, contract in expected.items():
        index, download = _step(analysis, name)
        _, build_download = _step(build, name)
        assert download == build_download
        assert download["if"] == contract["if"]
        assert download["with"] == contract["with"]
        assert re.fullmatch(r"actions/download-artifact@[0-9a-f]{40}", download["uses"])
        assert checkout_index < index < install_index


def test_bundle_parser_is_an_exact_locked_direct_dev_dependency() -> None:
    manifest = json.loads(
        (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    lock = json.loads(
        (ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    assert manifest["devDependencies"]["parse5"] == "8.0.1"
    assert lock["packages"][""]["devDependencies"]["parse5"] == "8.0.1"
    installed = lock["packages"]["node_modules/parse5"]
    assert installed["version"] == "8.0.1"
    assert installed["dev"] is True


def test_bundle_analysis_installs_locked_dependencies_with_lifecycle_scripts() -> None:
    workflow = _workflow()
    analysis = workflow["jobs"]["bundle-analysis"]
    build = workflow["jobs"]["build"]
    setup_index, setup = _step(analysis, "Set up Node.js")
    _, build_setup = _step(build, "Setup Node.js")
    install_index, install = _step(analysis, "Install dependencies")
    _, build_install = _step(build, "Install dependencies")

    assert setup["uses"] == build_setup["uses"]
    assert setup["with"]["node-version"] == build_setup["with"]["node-version"]
    assert setup_index < install_index
    assert (
        install
        == build_install
        == {
            "name": "Install dependencies",
            "run": "npm ci --no-audit --no-fund",
        }
    )
    npmrc = (ROOT / "frontend" / ".npmrc").read_text(encoding="utf-8")
    assert not re.search(r"(?im)^\s*(?:ignore-scripts|omit|production)\s*=", npmrc)
    for scope in (workflow, analysis, install):
        env = scope.get("env", {})
        assert isinstance(env, dict)
        assert not {key.lower().replace("-", "_") for key in env}.intersection(
            {"npm_config_ignore_scripts", "npm_config_omit", "npm_config_production"}
        )
        assert str(env.get("NODE_ENV", "")).lower() != "production"


def test_bundle_analysis_tests_and_analyzes_only_after_install_and_artifact_download() -> (
    None
):
    analysis = _workflow()["jobs"]["bundle-analysis"]
    install_index, _ = _step(analysis, "Install dependencies")
    download_index, download = _step(analysis, "Download production bundle")
    test_index, test = _step(analysis, "Test bundle analyzer")
    analyze_index, analyze = _step(analysis, "Analyze bundle size")
    upload_index, _ = _step(analysis, "Upload bundle report")

    assert download["with"] == {
        "artifact-ids": "${{ needs.build.outputs.bundle-artifact-id }}",
        "path": "${{ inputs.working-directory }}/dist",
        "merge-multiple": True,
        "digest-mismatch": "error",
    }
    assert re.fullmatch(r"actions/download-artifact@[0-9a-f]{40}", download["uses"])
    assert "if" not in analysis
    assert "if" not in download
    assert not download.get("continue-on-error", False)
    assert install_index < test_index < analyze_index < upload_index
    assert download_index < test_index
    assert test["run"] == (
        "node --test scripts/check-bundle-budget.test.mjs "
        "scripts/maplibre-build-metadata.test.mjs"
    )
    assert analyze["run"] == "node scripts/check-bundle-budget.mjs"
    for step in (test, analyze):
        assert "if" not in step
        assert not step.get("continue-on-error", False)
    assert not analysis.get("continue-on-error", False)
