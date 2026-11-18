"""Source-bound contracts for the additive, immutable-subject diagnostic lane."""

import json
from pathlib import Path

import yaml

from scripts.quality.validate_ci_check_catalog import validate_catalog

_WORKFLOW = ".github/workflows/disposition-contract-diagnostic.yml"
_REPORTER = "81afe9a5273987eb25c500fab46d9312a10027f1"
_SUBJECT = "3d751d30f43c6e1e5a6c9aa046ea7137eb20e912"


def test_disposition_diagnostic_is_source_bound_and_advisory() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / _WORKFLOW).read_text())
    catalog = json.loads((root / "quality/ci-check-catalog.json").read_text())
    schema = json.loads((root / "quality/ci-check-catalog.schema.json").read_text())
    assert validate_catalog(catalog, repository_root=root, schema=schema) == []
    entry = next(item for item in catalog["workflows"] if item["path"] == _WORKFLOW)
    assert entry["jobs"]["diagnostic"]["profile"] == "advisory"
    assert entry["jobs"]["diagnostic"]["needs"] == []
    assert entry["jobs"]["diagnostic"]["artifacts"] == []
    retry = entry["jobs"]["diagnostic"]["retry_policy"]
    assert retry["mode"] == "review-required"
    assert retry["review_required"] is True
    assert retry["first_failure_preserved"] is False
    assert retry["classifier"] == "not-yet-classified"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["cache-mode"] == "none"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["on"]) == {"pull_request"}
    assert set(workflow["jobs"]) == {"diagnostic"}
    job = workflow["jobs"]["diagnostic"]
    assert "needs" not in job
    assert "continue-on-error" not in job
    assert type(job["timeout-minutes"]) is int
    assert job["timeout-minutes"] == 45
    assert job["if"] == (
        "${{ github.event_name == 'pull_request' && "
        "github.event.pull_request.head.repo.full_name == github.repository && "
        "github.head_ref == 'coff/diagnostic-disposition-contracts' && "
        "github.base_ref == 'egorribun' && "
        "github.event.pull_request.base.sha == "
        "'bc7313ca450cafedd307b1524ca85c3fc87de382' }}"
    )
    assert job["env"] == {
        "ENVIRONMENT": "testing",
        "OTEL_SDK_DISABLED": "true",
        "REVOCATION_REDIS_URL": "redis://localhost:6380/0",
        "PYTHON_GIL": "1",
    }
    steps = job["steps"]
    assert len(steps) == 8
    assert all("continue-on-error" not in step for step in steps)
    assert steps[0]["with"] == {
        "ref": _REPORTER,
        "path": "diagnostic",
        "fetch-depth": 0,
        "persist-credentials": False,
    }
    assert steps[1]["with"] == {
        "ref": _SUBJECT,
        "path": "subject",
        "fetch-depth": 0,
        "persist-credentials": False,
    }
    assert all(type(steps[index]["with"]["fetch-depth"]) is int for index in (0, 1))
    assert all(steps[index]["with"]["persist-credentials"] is False for index in (0, 1))
    expected_pin_env = {"DIAGNOSTIC_SHA": _REPORTER, "SUBJECT_SHA": _SUBJECT}
    assert steps[2]["env"] == steps[6]["env"] == expected_pin_env
    assert steps[2]["run"].splitlines() == [
        "set -euo pipefail",
        '[[ "$DIAGNOSTIC_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'test "$(git -C diagnostic rev-parse HEAD)" = "$DIAGNOSTIC_SHA"',
        'test "$(git -C subject rev-parse HEAD)" = "$SUBJECT_SHA"',
        "printf 'diagnostic_sha=%s subject_sha=%s\\n' "
        '"$DIAGNOSTIC_SHA" "$SUBJECT_SHA"',
    ]
    assert steps[3]["with"] == {"python-version": "3.14"}
    assert steps[4]["with"] == {
        "version": "0.12.23",
        "working-directory": "subject",
        "enable-cache": False,
    }
    assert steps[5]["working-directory"] == "subject"
    assert steps[5]["run"].splitlines() == ["uv lock --check", "uv sync --frozen"]
    assert steps[6]["run"].splitlines() == [
        "set -euo pipefail",
        'test "$(git -C diagnostic rev-parse HEAD)" = "$DIAGNOSTIC_SHA"',
        'test "$(git -C subject rev-parse HEAD)" = "$SUBJECT_SHA"',
        "git -C diagnostic diff --quiet HEAD --",
        "git -C diagnostic diff --cached --quiet HEAD --",
        "git -C subject diff --quiet HEAD --",
        "git -C subject diff --cached --quiet HEAD --",
    ]
    assert steps[7]["working-directory"] == "subject"
    assert steps[7]["run"].strip() == (
        ".venv/bin/python "
        "../diagnostic/scripts/quality/disposition_contract_diagnostic.py "
        '--subject-root "$GITHUB_WORKSPACE/subject"'
    )
    assert [step["uses"] for step in steps if "uses" in step] == [
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
        "astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2",
    ]
    assert job["services"] == {
        "redis": {
            "image": (
                "redis:7-alpine@sha256:"
                "e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
            ),
            "ports": ["6379:6379"],
            "options": (
                '--health-cmd "redis-cli ping" --health-interval 10s '
                "--health-timeout 5s --health-retries 5"
            ),
        }
    }
    assert [index for index, step in enumerate(steps) if "env" in step] == [2, 6]
    assert all("if" not in step for step in steps)
