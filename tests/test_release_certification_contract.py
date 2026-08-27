from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
PRODUCER_WORKFLOW = ROOT / ".github" / "workflows" / "build-release-images.yml"
POLICY_PATH = ROOT / "quality" / "release-required-checks.json"
POLICY_SCHEMA_PATH = ROOT / "quality" / "release-required-checks.schema.json"


def _load_certification_module():
    path = ROOT / "scripts" / "quality" / "generate_certification.py"
    spec = importlib.util.spec_from_file_location("generate_certification", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_collection_module():
    path = ROOT / "scripts" / "quality" / "collect_release_check_evidence.py"
    spec = importlib.util.spec_from_file_location(
        "collect_release_check_evidence", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_artifact_collection_module():
    path = ROOT / "scripts" / "quality" / "validate_release_artifact_evidence.py"
    spec = importlib.util.spec_from_file_location("release_artifact_evidence", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_verifier_module():
    path = ROOT / "scripts" / "quality" / "verify_certification.py"
    spec = importlib.util.spec_from_file_location("verify_certification", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _run(
    name: str,
    sha: str,
    check_id: int,
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    workflow_path: str = ".github/workflows/ci.yml",
    event: str = "push",
    head_branch: str = "main",
    app_slug: str = "github-actions",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
        "details_url": f"https://example.test/check-runs/{check_id}",
        "app": {"slug": app_slug},
        "workflow_run": {
            "id": 1000 + check_id,
            "path": workflow_path,
            "event": event,
            "head_branch": head_branch,
            "head_sha": sha,
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
            "repository": "egorribun/university_ecosystem",
            "job_id": 2000 + check_id,
        },
    }


def _policy(*, allow_safe_skip: bool = False) -> dict[str, Any]:
    second: dict[str, Any] = {
        "name": "Security Gate",
        "category": "security",
        "allowed_conclusions": ["success"],
        "rationale": "Release security boundary.",
    }
    if allow_safe_skip:
        second.update(
            allowed_conclusions=["success", "skipped"],
            safe_to_skip=True,
            skip_reason="Not applicable to this exact push event.",
        )
    return {
        "schema_version": 2,
        "events": {
            "push_main": {
                "github_event": "push",
                "github_ref": "refs/heads/main",
                "github_repository": "egorribun/university_ecosystem",
                "required_checks": [
                    {
                        "name": "CI Success",
                        "workflow_path": ".github/workflows/ci.yml",
                        "category": "quality_manifest",
                        "allowed_conclusions": ["success"],
                        "rationale": "Canonical aggregate quality gate.",
                    },
                    {**second, "workflow_path": ".github/workflows/security.yml"},
                ],
            }
        },
    }


def _evidence(sha: str) -> dict[str, Any]:
    return {
        "commit_sha": sha,
        "check_runs": [
            _run("CI Success", sha, 1),
            _run(
                "Security Gate",
                sha,
                2,
                workflow_path=".github/workflows/security.yml",
            ),
        ],
    }


def test_release_collects_every_paginated_check_run_for_exact_sha() -> None:
    workflow = yaml.safe_load(PRODUCER_WORKFLOW.read_text(encoding="utf-8"))
    certify = workflow["jobs"]["certify"]
    collect = _step(certify, "Collect SHA-bound release check evidence")
    script = str(collect["run"])

    assert collect["env"]["RELEASE_SHA"] == "${{ inputs.release-sha }}"
    assert "gh api --paginate --slurp" in script
    assert "commits/$RELEASE_SHA/check-runs?per_page=100&filter=latest" in script
    assert "check-run-pages.json" in script
    assert "scripts/quality/collect_release_check_evidence.py" in script
    assert "--event push_main" in script
    assert '--repository "$GITHUB_REPOSITORY"' in script
    assert '--commit-sha "$RELEASE_SHA"' in script


def test_release_collects_and_validates_every_quality_artifact_page() -> None:
    workflow = yaml.safe_load(PRODUCER_WORKFLOW.read_text(encoding="utf-8"))
    verify = _step(workflow["jobs"]["certify"], "Verify release SHA and quality run")
    script = str(verify["run"])

    assert "gh api --paginate --slurp" in script
    assert "actions/runs/$QUALITY_RUN_ID/artifacts?per_page=100" in script
    assert "quality-artifact-pages.json" in script
    assert "scripts/quality/validate_release_artifact_evidence.py" in script
    assert '--expected-name "quality-evidence-$RELEASE_SHA"' in script


def test_artifact_inventory_accepts_complete_multi_page_response() -> None:
    module = _load_artifact_collection_module()
    target = "quality-evidence-" + "a" * 40
    first_page = {
        "total_count": 101,
        "artifacts": [
            {"id": index + 1, "name": f"optional-{index}", "expired": False}
            for index in range(100)
        ],
    }
    second_page = {
        "total_count": 101,
        "artifacts": [{"id": 101, "name": target, "expired": False}],
    }

    selected = module.validate_artifact_pages(
        [first_page, second_page], expected_name=target
    )

    assert selected["id"] == 101


@pytest.mark.parametrize(
    "pages, message",
    [
        (
            [
                {"total_count": 2, "artifacts": []},
                {"total_count": 1, "artifacts": []},
            ],
            "inconsistent",
        ),
        ([{"total_count": 2, "artifacts": []}], "truncated"),
        ([{"total_count": 1, "artifacts": "invalid"}], "artifacts array"),
    ],
)
def test_artifact_inventory_rejects_malformed_or_incomplete_pagination(
    pages: object, message: str
) -> None:
    module = _load_artifact_collection_module()

    with pytest.raises(ValueError, match=message):
        module.validate_artifact_pages(
            pages, expected_name="quality-evidence-" + "a" * 40
        )


def test_artifact_inventory_rejects_duplicate_expected_name() -> None:
    module = _load_artifact_collection_module()
    target = "quality-evidence-" + "a" * 40
    pages = [
        {
            "total_count": 2,
            "artifacts": [
                {"id": 1, "name": target, "expired": False},
                {"id": 2, "name": target, "expired": True},
            ],
        }
    ]

    with pytest.raises(ValueError, match="duplicate"):
        module.validate_artifact_pages(pages, expected_name=target)


def test_collector_binds_check_to_exact_actions_run_and_job() -> None:
    module = _load_collection_module()
    sha = "a" * 40
    repository = "egorribun/university_ecosystem"
    check = _run("CI Success", sha, 11)
    check["details_url"] = f"https://github.com/{repository}/actions/runs/21/job/31"
    check.pop("workflow_run")
    responses = {
        f"repos/{repository}/actions/runs/21": {
            "id": 21,
            "path": ".github/workflows/ci.yml",
            "event": "push",
            "head_branch": "main",
            "head_sha": sha,
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 2,
            "repository": {"full_name": repository},
        },
        f"repos/{repository}/actions/jobs/31": {
            "id": 31,
            "run_id": 21,
            "run_attempt": 2,
            "head_sha": sha,
            "check_run_url": f"https://api.github.com/repos/{repository}/check-runs/11",
        },
    }

    evidence = module.collect_evidence(
        [{"total_count": 1, "check_runs": [check]}],
        _policy(),
        event="push_main",
        repository=repository,
        commit_sha=sha,
        fetch_json=responses.__getitem__,
    )

    assert evidence["check_runs"][0]["workflow_run"] == {
        "id": 21,
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
        "repository": repository,
        "job_id": 31,
    }


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///etc/passwd",
        "https://evil.example/repos/owner/repo/actions/runs/1",
        "repos/owner/repo/actions/runs/1?token=leak",
        "repos/other/repo/actions/jobs/1",
        "repos/owner/repo/check-runs/1",
    ],
)
def test_github_fetcher_rejects_noncanonical_endpoints(endpoint: str) -> None:
    module = _load_collection_module()

    with pytest.raises(ValueError, match="unsupported GitHub API endpoint"):
        module._github_api_url(endpoint, "owner/repo")


@pytest.mark.parametrize("resource", ["runs", "jobs"])
def test_github_fetcher_accepts_only_canonical_actions_endpoints(resource: str) -> None:
    module = _load_collection_module()
    endpoint = f"repos/owner/repo/actions/{resource}/123"

    assert module._github_api_url(endpoint, "owner/repo") == (
        f"https://api.github.com/{endpoint}"
    )


def test_collector_rejects_job_not_bound_to_check_run() -> None:
    module = _load_collection_module()
    sha = "a" * 40
    repository = "egorribun/university_ecosystem"
    check = _run("CI Success", sha, 11)
    check["details_url"] = f"https://github.com/{repository}/actions/runs/21/job/31"
    check.pop("workflow_run")

    def fetch_json(endpoint: str) -> dict[str, Any]:
        if endpoint.endswith("/runs/21"):
            return {
                "id": 21,
                "path": ".github/workflows/ci.yml",
                "event": "push",
                "head_branch": "main",
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
                "repository": {"full_name": repository},
            }
        return {
            "id": 31,
            "run_id": 21,
            "run_attempt": 1,
            "head_sha": sha,
            "check_run_url": f"https://api.github.com/repos/{repository}/check-runs/999",
        }

    with pytest.raises(ValueError, match="not bound to check run"):
        module.collect_evidence(
            [{"total_count": 1, "check_runs": [check]}],
            _policy(),
            event="push_main",
            repository=repository,
            commit_sha=sha,
            fetch_json=fetch_json,
        )


def test_release_certification_is_gated_by_canonical_policy() -> None:
    workflow = yaml.safe_load(PRODUCER_WORKFLOW.read_text(encoding="utf-8"))
    certify = workflow["jobs"]["certify"]
    runtime = _step(certify, "Setup release quality runtime")
    assert str(runtime["uses"]).startswith("astral-sh/setup-uv@")
    install = _step(certify, "Install locked certification dependencies")
    assert "uv sync --frozen --only-group release-certification" in install["run"]
    assert "--no-install-project" in install["run"]
    assert "QUALITY_CERTIFICATION_KEY" not in str(install)
    generate = _step(certify, "Generate quality certification record")
    script = str(generate["run"])

    assert "--check-policy quality/release-required-checks.json" in script
    assert "--check-event push_main" in script
    assert "--checks artifacts/quality/check-runs.json" in script
    assert (
        "uv run --frozen --no-sync --only-group release-certification python" in script
    )
    assert "--with" not in script
    assert generate["env"]["UV_OFFLINE"] == "true"
    verify = _step(certify, "Verify signed certification")
    assert (
        "uv run --frozen --no-sync --only-group release-certification python"
        in verify["run"]
    )
    assert "--with" not in verify["run"]
    assert verify["env"]["UV_OFFLINE"] == "true"
    assert "-m scripts.quality.verify_certification" in verify["run"]
    assert '--expected-commit-sha "$RELEASE_SHA"' in verify["run"]


def test_release_certification_dependency_group_is_lock_pinned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert project["dependency-groups"]["release-certification"] == [
        "jsonschema==4.25.1"
    ]
    root_package = next(
        package
        for package in lock["package"]
        if package["name"] == "university-ecosystem"
    )
    assert root_package["dev-dependencies"]["release-certification"] == [
        {"name": "jsonschema"}
    ]


def test_semantic_release_waits_for_every_signed_image() -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    producer = yaml.safe_load(PRODUCER_WORKFLOW.read_text(encoding="utf-8"))

    assert workflow["concurrency"] == {
        "group": "release-main",
        "cancel-in-progress": False,
    }
    assert producer["jobs"]["build"]["needs"] == ["certify"]
    assert set(producer["jobs"]["aggregate-image-provenance"]["needs"]) == {
        "certify",
        "build",
    }
    assert workflow["jobs"]["publish"]["needs"] == ["resolve-images"]
    assert "Release" not in {
        step.get("name")
        for step in producer["jobs"]["aggregate-image-provenance"]["steps"]
    }
    release = _step(workflow["jobs"]["publish"], "Release")
    assert "semantic-release" in release["run"]
    assert release["run"].index("git fetch origin refs/heads/main") < release[
        "run"
    ].index("semantic-release")
    assert 'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"' in release["run"]
    checkout = _step(workflow["jobs"]["publish"], "Checkout certified source")
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert "inputs.release-sha" not in str(checkout)
    workflow_text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert (
        workflow_text.count(
            "node node_modules/semantic-release/bin/semantic-release.js"
        )
        == 1
    )
    assert workflow_text.count("secrets.RELEASE_TOKEN") == 1


def test_release_jobs_check_out_event_sha_before_trusting_dispatch_inputs() -> None:
    """Privileged release jobs must execute only the workflow event's source.

    ``release-sha`` remains an input for binding promoted artifacts, but it must
    never select the repository revision used by a job with write permissions.
    The checkout and fail-closed assertions therefore precede every script that
    consumes release artifacts or invokes a release tool.
    """

    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    expected_guard_fragments = (
        '[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$RELEASE_SHA" = "$GITHUB_SHA"',
        'test "$RELEASE_SHA" = "$GITHUB_WORKFLOW_SHA"',
        'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"',
        "git fetch origin refs/heads/main:refs/remotes/origin/main --depth=1",
        'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"',
    )

    for job_name, verify_name in (
        (
            "resolve-images",
            "Verify canonical image producer run and artifact inventory",
        ),
        ("publish", "Verify publish source"),
    ):
        job = workflow["jobs"][job_name]
        checkout = _step(job, "Checkout certified source")
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        assert checkout["with"]["persist-credentials"] is False
        assert "inputs.release-sha" not in str(checkout)

        verify = _step(job, verify_name)
        script = str(verify["run"])
        assert verify["env"]["RELEASE_SHA"] == "${{ inputs.release-sha }}"
        assert all(fragment in script for fragment in expected_guard_fragments)

        steps = job["steps"]
        checkout_index = steps.index(checkout)
        verify_index = steps.index(verify)
        assert verify_index == checkout_index + 1
        # No release-side script may run before the source trust boundary is
        # established.  Download actions are checked separately by artifact
        # contract tests and are intentionally after this guard.
        assert all(
            not step.get("run") for step in steps[checkout_index + 1 : verify_index]
        )


def test_canonical_image_pipeline_checks_trusted_source_before_privileged_tools() -> (
    None
):
    """Input SHAs may bind artifacts, but never select executable workflow code."""

    producer = yaml.safe_load(PRODUCER_WORKFLOW.read_text(encoding="utf-8"))
    certify = producer["jobs"]["certify"]
    certify_checkout = _step(certify, "Checkout certified source")
    certify_verify = _step(certify, "Verify trusted source checkout")
    assert certify_checkout["with"]["ref"] == "${{ github.sha }}"
    assert certify_checkout["with"]["persist-credentials"] is False
    assert "inputs.release-sha" not in str(certify_checkout)
    certify_steps = certify["steps"]
    assert (
        certify_steps.index(certify_verify) == certify_steps.index(certify_checkout) + 1
    )
    certify_run = str(certify_verify["run"])
    for fragment in (
        '[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$RELEASE_SHA" = "$GITHUB_SHA"',
        'test "$RELEASE_SHA" = "$GITHUB_WORKFLOW_SHA"',
        'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"',
        "git fetch origin refs/heads/main:refs/remotes/origin/main --depth=1",
        'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"',
    ):
        assert fragment in certify_run
    assert "gh api" not in certify_run
    setup_index = certify_steps.index(_step(certify, "Setup release quality runtime"))
    assert setup_index > certify_steps.index(certify_verify)
    quality_verify = _step(certify, "Verify release SHA and quality run")
    assert certify_steps.index(quality_verify) > setup_index
    assert '[[ "$QUALITY_RUN_ID" =~ ^[1-9][0-9]*$ ]]' in str(quality_verify["run"])

    aggregate = producer["jobs"]["aggregate-image-provenance"]
    aggregate_checkout = _step(aggregate, "Checkout certified source")
    aggregate_verify = _step(aggregate, "Verify aggregate source")
    assert aggregate_checkout["with"]["ref"] == "${{ github.sha }}"
    assert aggregate_checkout["with"]["persist-credentials"] is False
    assert "inputs.release-sha" not in str(aggregate_checkout)
    aggregate_steps = aggregate["steps"]
    assert aggregate_steps.index(aggregate_verify) == (
        aggregate_steps.index(aggregate_checkout) + 1
    )
    aggregate_run = str(aggregate_verify["run"])
    for fragment in (
        '[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$RELEASE_SHA" = "$GITHUB_SHA"',
        'test "$RELEASE_SHA" = "$GITHUB_WORKFLOW_SHA"',
        'test "$(git rev-parse HEAD)" = "$RELEASE_SHA"',
        "git fetch origin refs/heads/main:refs/remotes/origin/main --depth=1",
        'test "$(git rev-parse origin/main)" = "$RELEASE_SHA"',
    ):
        assert fragment in aggregate_run


def test_policy_binds_each_check_to_a_workflow_and_repository() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    event = policy["events"]["push_main"]

    assert event["github_repository"] == "egorribun/university_ecosystem"
    assert event["github_event"] == "push"
    assert event["github_ref"] == "refs/heads/main"
    assert all(
        check["workflow_path"].startswith(".github/workflows/")
        for check in event["required_checks"]
    )


def test_canonical_release_check_policy_is_schema_valid_and_auditable() -> None:
    schema = json.loads(POLICY_SCHEMA_PATH.read_text(encoding="utf-8"))
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(policy)

    checks = policy["events"]["push_main"]["required_checks"]
    names = [check["name"] for check in checks]
    assert names.count("CI Success") == 1
    assert any(check["category"] == "security" for check in checks)
    assert all(check["rationale"].strip() for check in checks)
    assert all(check["allowed_conclusions"] == ["success"] for check in checks)


def test_canonical_policy_requires_every_codeql_language() -> None:
    codeql = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
    )
    languages = {
        entry["language"]
        for entry in codeql["jobs"]["analyze"]["strategy"]["matrix"]["include"]
    }
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    names = {
        check["name"] for check in policy["events"]["push_main"]["required_checks"]
    }

    assert {f"Analyze ({language})" for language in languages} <= names


def test_canonical_policy_requires_independent_release_security_gates() -> None:
    expected: set[str] = set()
    for workflow_name, job_name in [
        ("gitleaks.yml", "gitleaks"),
        ("trufflehog.yml", "trufflehog"),
        ("cargo-deny.yml", "cargo-deny"),
        ("checkov.yml", "checkov"),
        ("zizmor.yml", "zizmor"),
        ("sqlmap.yml", "sqlmap"),
        ("sbom.yml", "vuln-gate"),
    ]:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        )
        expected.add(workflow["jobs"][job_name]["name"])
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    names = {
        check["name"] for check in policy["events"]["push_main"]["required_checks"]
    }

    assert expected <= names


def test_validator_accepts_complete_successful_sha_bound_evidence() -> None:
    module = _load_certification_module()
    sha = "a" * 40

    validated = module.validate_required_checks(
        _evidence(sha), _policy(), event="push_main", commit_sha=sha
    )

    assert validated == {
        "CI Success": {
            "id": 1,
            "status": "completed",
            "conclusion": "success",
            "details_url": "https://example.test/check-runs/1",
            "app_slug": "github-actions",
            "workflow_run": _evidence(sha)["check_runs"][0]["workflow_run"],
        },
        "Security Gate": {
            "id": 2,
            "status": "completed",
            "conclusion": "success",
            "details_url": "https://example.test/check-runs/2",
            "app_slug": "github-actions",
            "workflow_run": _evidence(sha)["check_runs"][1]["workflow_run"],
        },
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda evidence: evidence.update(commit_sha="b" * 40), "commit SHA"),
        (lambda evidence: evidence["check_runs"].pop(), "Security Gate.*missing"),
        (
            lambda evidence: evidence["check_runs"][0].update(
                status="in_progress", conclusion=None
            ),
            "CI Success.*not completed",
        ),
        (
            lambda evidence: evidence["check_runs"][0].update(conclusion="failure"),
            "CI Success.*failure",
        ),
        (
            lambda evidence: evidence["check_runs"][0].update(conclusion="skipped"),
            "CI Success.*skipped",
        ),
        (
            lambda evidence: evidence["check_runs"].append(
                dict(evidence["check_runs"][0], id=99)
            ),
            "CI Success.*duplicate",
        ),
        (
            lambda evidence: evidence["check_runs"][0].update(head_sha="b" * 40),
            "foreign commit SHA",
        ),
    ],
)
def test_validator_fails_closed_on_untrusted_check_evidence(
    mutate, message: str
) -> None:
    module = _load_certification_module()
    sha = "a" * 40
    evidence = _evidence(sha)
    mutate(evidence)

    with pytest.raises(ValueError, match=message):
        module.validate_required_checks(
            evidence, _policy(), event="push_main", commit_sha=sha
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda run: run.update(app={"slug": "third-party"}), "GitHub Actions app"),
        (lambda run: run.pop("workflow_run"), "workflow provenance"),
        (
            lambda run: run["workflow_run"].update(
                path=".github/workflows/nightly.yml"
            ),
            "workflow path",
        ),
        (lambda run: run["workflow_run"].update(event="schedule"), "workflow event"),
        (lambda run: run["workflow_run"].update(head_branch="feature"), "head branch"),
        (
            lambda run: run["workflow_run"].update(head_sha="b" * 40),
            "workflow head SHA",
        ),
        (
            lambda run: run["workflow_run"].update(repository="attacker/fork"),
            "workflow repository",
        ),
        (lambda run: run["workflow_run"].pop("job_id"), "workflow job id"),
    ],
)
def test_validator_rejects_wrong_or_missing_workflow_provenance(
    mutate, message: str
) -> None:
    module = _load_certification_module()
    sha = "a" * 40
    evidence = _evidence(sha)
    mutate(evidence["check_runs"][0])

    with pytest.raises(ValueError, match=message):
        module.validate_required_checks(
            evidence, _policy(), event="push_main", commit_sha=sha
        )


def test_hmac_verifier_rejects_tampered_certification() -> None:
    module = _load_certification_module()
    key = b"release-certification-test-key"
    record = module.build_record(
        commit_sha="a" * 40,
        contract_path=ROOT / "quality" / "quality-contract.json",
        report_paths=[],
        check_results={"CI Success": {"conclusion": "success"}},
        known_limitations=[],
        signing_key=key,
        generated_at="2026-08-27T00:00:00Z",
    )

    module.verify_record_hmac(record, key)
    record["commit_sha"] = "b" * 40
    with pytest.raises(ValueError, match="HMAC"):
        module.verify_record_hmac(record, key)


def test_on_disk_certification_verifier_checks_sha_and_hmac(tmp_path: Path) -> None:
    certification = _load_certification_module()
    verifier = _load_verifier_module()
    key = b"release-certification-test-key"
    path = tmp_path / "certification.json"
    record = certification.build_record(
        commit_sha="a" * 40,
        contract_path=ROOT / "quality" / "quality-contract.json",
        report_paths=[],
        check_results={"CI Success": {"conclusion": "success"}},
        known_limitations=[],
        signing_key=key,
        generated_at="2026-08-27T00:00:00Z",
    )
    path.write_text(json.dumps(record), encoding="utf-8")

    verifier.verify_certification(path, expected_commit_sha="a" * 40, key=key)
    with pytest.raises(ValueError, match="release commit SHA"):
        verifier.verify_certification(path, expected_commit_sha="b" * 40, key=key)


def test_on_disk_verifier_is_invocable_as_workflow_module() -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and module
        [sys.executable, "-m", "scripts.quality.verify_certification", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_validator_allows_skipped_only_when_event_policy_marks_it_safe() -> None:
    module = _load_certification_module()
    sha = "a" * 40
    evidence = _evidence(sha)
    evidence["check_runs"][1]["conclusion"] = "skipped"

    validated = module.validate_required_checks(
        evidence,
        _policy(allow_safe_skip=True),
        event="push_main",
        commit_sha=sha,
    )

    assert validated["Security Gate"]["conclusion"] == "skipped"


def test_validator_rejects_unsafe_or_unexplained_skip_policy() -> None:
    module = _load_certification_module()
    sha = "a" * 40
    evidence = _evidence(sha)
    evidence["check_runs"][1]["conclusion"] = "skipped"
    policy = _policy(allow_safe_skip=True)
    del policy["events"]["push_main"]["required_checks"][1]["skip_reason"]

    with pytest.raises(ValueError, match=r"skip.*safe"):
        module.validate_required_checks(
            evidence, policy, event="push_main", commit_sha=sha
        )


def test_validator_handles_more_than_one_api_page_without_truncation() -> None:
    module = _load_certification_module()
    sha = "a" * 40
    policy = _policy()
    evidence = _evidence(sha)
    evidence["check_runs"].extend(
        _run(f"Optional {index}", sha, index + 10) for index in range(101)
    )

    validated = module.validate_required_checks(
        evidence, policy, event="push_main", commit_sha=sha
    )

    assert set(validated) == {"CI Success", "Security Gate"}
