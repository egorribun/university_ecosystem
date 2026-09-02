"""Regression contracts for failures observed on the protected main branch."""

import re
import shlex
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
CONTRACT_WORKFLOW = WORKFLOW_DIRECTORY / "contract-validation.yml"
CI_WORKFLOW = WORKFLOW_DIRECTORY / "ci.yml"
COMMAND_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`\r\n]+)`")


def _logical_shell_lines(script: str) -> list[str]:
    logical_lines: list[str] = []
    continued = ""
    for physical_line in script.splitlines():
        stripped = physical_line.rstrip()
        if stripped.endswith(("\\", "`")):
            continued += stripped[:-1] + " "
            continue
        logical_lines.append(continued + physical_line)
        continued = ""
    if continued:
        logical_lines.append(continued)
    return logical_lines


def _shell_command_segments(script: str) -> list[list[str]]:
    segments: list[list[str]] = []
    for line in _logical_shell_lines(script):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            tokens = list(lexer)
        except ValueError:
            # Workflow blocks contain continuation and heredoc fragments that are
            # not standalone shell commands. They cannot execute npm by themselves.
            continue
        segment: list[str] = []
        for token in tokens:
            if token and all(character in ";&|()" for character in token):
                if segment:
                    segments.append(segment)
                    segment = []
            else:
                segment.append(token)
        if segment:
            segments.append(segment)

        if any("$(" in token or "`" in token for token in tokens):
            for match in COMMAND_SUBSTITUTION.finditer(line):
                substitution = match.group(1) or match.group(2)
                segments.extend(_shell_command_segments(substitution))
    return segments


def _is_environment_assignment(token: str) -> bool:
    name, separator, _value = token.partition("=")
    return bool(separator and name and name.replace("_", "a").isalnum())


def _segment_runs_generate_api(segment: list[str]) -> bool:
    argument_index = 0
    if argument_index < len(segment) and segment[argument_index] == "env":
        argument_index += 1
    while argument_index < len(segment) and _is_environment_assignment(
        segment[argument_index]
    ):
        argument_index += 1
    if argument_index < len(segment) and segment[argument_index] == "command":
        argument_index += 1
    if argument_index >= len(segment) or segment[argument_index] != "npm":
        return False

    argument_index += 1
    if argument_index < len(segment) and segment[argument_index] == "--prefix":
        argument_index += 2
    elif argument_index < len(segment) and segment[argument_index].startswith(
        "--prefix="
    ):
        argument_index += 1

    return segment[argument_index : argument_index + 2] == ["run", "generate:api"]


def _step_runs_generate_api(step: object) -> bool:
    if not isinstance(step, dict):
        return False
    script = step.get("run")
    return isinstance(script, str) and any(
        _segment_runs_generate_api(segment)
        for segment in _shell_command_segments(script)
    )


def test_openapi_drift_gate_only_compares_generated_contract_artifacts() -> None:
    """Unrelated lockfile changes must not be reported as OpenAPI drift."""

    workflow = yaml.safe_load(CONTRACT_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["openapi-typescript-drift"]["steps"]
    drift_step = next(
        step
        for step in steps
        if step.get("name") == "Check for schema-drift / uncommitted changes"
    )
    script = drift_step["run"]

    assert "git diff --exit-code ||" not in script
    assert "git diff --exit-code -- \\" in script
    for generated_path in (
        "frontend/openapi.json",
        "frontend/src/api/generated/",
        "frontend/src/tests/mocks/generated/",
    ):
        assert generated_path in script


def test_primary_ci_openapi_gate_checks_every_generated_directory() -> None:
    """The primary gate must not silently check a non-existent legacy file."""

    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["openapi-verify"]["steps"]
    drift_step = next(
        step
        for step in steps
        if step.get("name") == "Verify generated API types are up to date"
    )
    script = drift_step["run"]

    assert "schema.ts" not in script
    for generated_path in (
        "frontend/openapi.json",
        "frontend/src/api/generated/",
        "frontend/src/tests/mocks/generated/",
    ):
        assert generated_path in script


def _assert_all_openapi_producers_are_normalized() -> None:
    producer_contracts = {
        (CONTRACT_WORKFLOW, "openapi-typescript-drift"): (
            "Generate current OpenAPI spec",
            "Regenerate TypeScript client and MSW mocks",
            "Check for schema-drift / uncommitted changes",
        ),
        (CI_WORKFLOW, "openapi-verify"): (
            "Generate OpenAPI schema",
            "Generate API types",
            "Verify generated API types are up to date",
        ),
        (CI_WORKFLOW, "msw-mock-drift"): (
            "Generate OpenAPI spec from live FastAPI app",
            "Regenerate MSW mock handlers from OpenAPI spec",
            "Fail if MSW mocks are out of sync with OpenAPI spec",
        ),
    }

    workflow_paths = sorted(
        {
            *WORKFLOW_DIRECTORY.glob("*.yml"),
            *WORKFLOW_DIRECTORY.glob("*.yaml"),
        }
    )
    workflows = {
        workflow_path: yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for workflow_path in workflow_paths
    }
    discovered_producers = {
        (workflow_path, job_name)
        for workflow_path, workflow in workflows.items()
        for job_name, job in workflow["jobs"].items()
        if any(_step_runs_generate_api(step) for step in job.get("steps", []))
    }
    contracted_producers = set(producer_contracts)

    assert discovered_producers == contracted_producers, (
        "OpenAPI generator producers and normalization contracts diverged: "
        f"discovered={sorted((str(path), job) for path, job in discovered_producers)!r}, "
        f"contracted={sorted((str(path), job) for path, job in contracted_producers)!r}"
    )

    for (workflow_path, job_name), (
        schema_name,
        generate_name,
        drift_name,
    ) in producer_contracts.items():
        workflow = workflows[workflow_path]
        steps = workflow["jobs"][job_name]["steps"]
        step_indexes = {step.get("name"): index for index, step in enumerate(steps)}

        install_index = step_indexes["Install frontend dependencies"]
        schema_index = step_indexes[schema_name]
        normalize_index = step_indexes["Normalize generated OpenAPI schema"]
        generate_index = step_indexes[generate_name]
        drift_index = step_indexes[drift_name]

        assert install_index < normalize_index, job_name
        assert schema_index < normalize_index < generate_index < drift_index, job_name

        normalize_step = steps[normalize_index]
        assert normalize_step["working-directory"] == "frontend", job_name
        assert normalize_step["run"].strip() == (
            "npm exec -- prettier --write openapi.json"
        ), job_name


def test_all_openapi_producers_normalize_schema_before_client_generation() -> None:
    """Every SDK/mock producer must consume the canonical JSON representation."""

    _assert_all_openapi_producers_are_normalized()


def test_openapi_producer_contract_rejects_uncontracted_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newly added real generator must not bypass normalization checks."""

    original_read_text = Path.read_text

    def read_text_with_uncontracted_generator(
        path: Path, *args: object, **kwargs: object
    ) -> str:
        contents = original_read_text(path, *args, **kwargs)
        if path != CI_WORKFLOW:
            return contents
        workflow = yaml.safe_load(contents)
        workflow["jobs"]["uncontracted-openapi-generator"] = {
            "steps": [{"name": "Generate client", "run": "npm run generate:api"}]
        }
        return yaml.safe_dump(workflow)

    monkeypatch.setattr(Path, "read_text", read_text_with_uncontracted_generator)

    with pytest.raises(AssertionError, match="uncontracted-openapi-generator"):
        _assert_all_openapi_producers_are_normalized()


def test_openapi_producer_discovery_ignores_echo_only_mentions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documentation emitted by a shell step is not a generator producer."""

    original_read_text = Path.read_text

    def read_text_with_echo_only_mention(
        path: Path, *args: object, **kwargs: object
    ) -> str:
        contents = original_read_text(path, *args, **kwargs)
        if path != CI_WORKFLOW:
            return contents
        workflow = yaml.safe_load(contents)
        workflow["jobs"]["generator-documentation"] = {
            "steps": [
                {
                    "name": "Explain local regeneration",
                    "run": 'echo "Run npm run generate:api before opening a PR"',
                }
            ]
        }
        return yaml.safe_dump(workflow)

    monkeypatch.setattr(Path, "read_text", read_text_with_echo_only_mention)

    _assert_all_openapi_producers_are_normalized()


@pytest.mark.parametrize(
    "generator_command",
    (
        "cd frontend && npm run generate:api",
        "npm --prefix frontend run generate:api",
        "npm run \\\ngenerate:api",
        "NODE_ENV=test npm run generate:api",
        'echo "$(npm run generate:api)"',
        "(npm run generate:api)",
    ),
)
def test_openapi_producer_contract_detects_shell_execution_variants(
    monkeypatch: pytest.MonkeyPatch,
    generator_command: str,
) -> None:
    """Equivalent executable npm forms must be discovered as producers."""

    original_read_text = Path.read_text

    def read_text_with_generator_variant(
        path: Path, *args: object, **kwargs: object
    ) -> str:
        contents = original_read_text(path, *args, **kwargs)
        if path != CI_WORKFLOW:
            return contents
        workflow = yaml.safe_load(contents)
        workflow["jobs"]["variant-openapi-generator"] = {
            "steps": [{"name": "Generate client", "run": generator_command}]
        }
        return yaml.safe_dump(workflow)

    monkeypatch.setattr(Path, "read_text", read_text_with_generator_variant)

    with pytest.raises(AssertionError, match="variant-openapi-generator"):
        _assert_all_openapi_producers_are_normalized()


def test_openapi_producer_contract_scans_new_yaml_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A producer in a newly added .yaml workflow must require a contract."""

    new_workflow = WORKFLOW_DIRECTORY / "foo.yaml"
    original_glob = Path.glob
    original_read_text = Path.read_text

    def glob_with_new_workflow(path: Path, pattern: str):
        discovered = list(original_glob(path, pattern))
        if path == WORKFLOW_DIRECTORY and pattern == "*.yaml":
            discovered.append(new_workflow)
        return iter(discovered)

    def read_text_with_new_workflow(path: Path, *args: object, **kwargs: object) -> str:
        if path == new_workflow:
            return yaml.safe_dump(
                {
                    "jobs": {
                        "new-yaml-openapi-generator": {
                            "steps": [
                                {
                                    "name": "Generate client",
                                    "run": "npm run generate:api",
                                }
                            ]
                        }
                    }
                }
            )
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "glob", glob_with_new_workflow)
    monkeypatch.setattr(Path, "read_text", read_text_with_new_workflow)

    with pytest.raises(AssertionError, match="new-yaml-openapi-generator"):
        _assert_all_openapi_producers_are_normalized()


def test_primary_ci_generates_canonical_tracked_openapi() -> None:
    """Every CI producer must serialize the tracked spec identically."""

    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    generator_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name")
        in {
            "Generate OpenAPI schema",
            "Generate OpenAPI spec from live FastAPI app",
        }
    ]

    assert len(generator_steps) == 2
    for step in generator_steps:
        script = step["run"]
        assert 'json.dumps(app.openapi(), indent=2, sort_keys=True) + "\\n"' in script
        assert 'encoding="utf-8"' in script
