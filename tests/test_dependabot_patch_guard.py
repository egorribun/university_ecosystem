"""Execute the real Dependabot auto-merge decision with a local API double."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ("pytester",)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Bump example from 1.2.3 to 1.2.4", 1),
        ("build(deps): bump example from 0.2.0 to 0.2.9", 1),
        ("Bump example from 1.2.9007199254740992 to 1.2.9007199254740993", 1),
        ("Bump example from 1.2.3 to 2.2.4", 0),
        ("Bump example from 1.2.3 to 1.3.4", 0),
        ("Bump example from 1.2.3 to 1.2.3", 0),
        ("Bump example from 1.2.3 to 1.2.2", 0),
        ("Bump example from 1.2.3 to 1.2.4-beta.1", 0),
        ("Bump example from 1.2.3 to 1.2.04", 0),
        ("Bump example from 1.2.3 to 1.2.4 in /frontend", 0),
        ("Bump the npm-dependencies group with 53 updates", 0),
    ],
)
def test_auto_merge_executes_only_for_increasing_stable_patches(
    pytester, title: str, expected: int
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/auto-merge-patches.yml").read_text(
            encoding="utf-8"
        )
    )
    job = workflow["jobs"]["auto-merge"]
    assert job["if"] == "github.event.pull_request.user.id == 49699333"
    script = next(
        step["with"]["script"]
        for step in job["steps"]
        if step.get("name") == "Fetch PR details"
    )
    assert "${{" not in script
    node = shutil.which("node")
    assert node, "Node is required to execute the actual auto-merge decision"
    harness = (
        'const assert = require("node:assert/strict");\n'
        'const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;\n'
        "const calls = [];\n"
        "const github = { graphql: async (query, variables) => {\n"
        "  assert.match(query, /enablePullRequestAutoMerge/);\n"
        "  assert.match(query, /mergeMethod: SQUASH/);\n"
        "  assert.equal(variables.pullRequestId, 'test-pr');\n"
        "  calls.push(variables);\n"
        "}};\n"
        "const context = {payload: {pull_request: {number: 42, node_id: 'test-pr', "
        f"title: {json.dumps(title)}}}}}}};\n"
        "new AsyncFunction('context', 'github', 'console', "
        f"{json.dumps(script)})(context, github, {{log() {{}}}})\n"
        f".then(() => assert.equal(calls.length, {expected}));\n"
    )
    target = pytester.path / "auto-merge-contract.cjs"
    target.write_text(harness, encoding="utf-8")
    result = pytester.run(node, str(target), timeout=20)
    assert result.ret == 0
