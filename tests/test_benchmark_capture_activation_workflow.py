from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "benchmark.yml"
MODULE_PATH = ROOT / "scripts" / "quality" / "benchmark_capture_activation.py"
SPEC = importlib.util.spec_from_file_location("activation_template", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("activation template cannot be imported")
activation_template = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = activation_template
SPEC.loader.exec_module(activation_template)


def test_workflow_uses_the_resolved_helper_and_keeps_base_comparator() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    job = jobs["ws-hub-regression"]
    steps = job["steps"]
    capture = next(step for step in steps if step.get("id") == "capture_ws_hub")
    capture_text = capture["run"]
    compare = next(
        step
        for step in steps
        if step.get("name") == "Compare paired benchmark evidence"
    )
    compare_text = compare["run"]

    assert "benchmark_capture_activation.py" in capture_text
    assert '"$PYTHON_BIN" -I "$CAPTURE_HELPER"' in capture_text
    assert '"$PYTHON_BIN" -I "$BASE_CAPTURE_HELPER"' not in capture_text
    assert "PR_HEAD_REPOSITORY_VALUE" in capture["env"]
    assert "PR_NUMBER_VALUE" in capture["env"]
    assert "PR_HEAD_REF_VALUE" in capture["env"]
    assert "PR_BASE_REF_VALUE" in capture["env"]
    assert capture["env"]["PUSH_REF_VALUE"] == "${{ github.ref }}"
    assert 'PUSH_REF="$PUSH_REF_VALUE"' in capture_text
    assert 'PUSH_BASE_REF="$PUSH_BASE_REF"' in capture_text

    assert '"$BASE_COMPARATOR"' in compare_text
    assert "--expected-pairs 12" in compare_text
    assert "capture-helper-provenance.json" in compare_text
    assert '"$HELPER_SHA256"' in compare_text


def test_candidate_activation_is_bound_to_the_reviewed_helper_checkpoint() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert activation_template.ACTIVATION_PULL_REQUEST == "1306"
    assert activation_template.ACTIVATION_HEAD_REF == "egorribun"
    assert activation_template.ACTIVATION_BASE_REF == "main"
    assert (
        activation_template.CAPTURE_HELPER_PATH
        == "scripts/quality/capture_isolated_benchmarks.py"
    )
    assert activation_template.PINNED_HELPER_COMMIT == (
        "3fc0ec8ac23b7d6995783343d83d383df72d06c6"  #  -- public helper commit
    )
    assert activation_template.PINNED_HELPER_PARENT == (
        "a744430f4e6fe7cb5ad06642f6450bf36c64a2ae"  #  -- public helper parent
    )
    assert activation_template.PINNED_HELPER_TREE == (
        "1329e9636c08b17d6c64b8f4d541282ad9bc9c43"  #  -- public helper tree
    )
    assert activation_template.PINNED_HELPER_BLOB == (
        "454074e46ad6dafc4deee963fa450215344d33d9"  #  -- public helper blob
    )
    assert (
        activation_template.PINNED_HELPER_SHA256
        == (
            "727133b420f1ad551433e626ca590500f5735bdec0bde7be19a9f8e7ea4568c5"  #  -- public helper SHA-256
        )
    )
    assert activation_template.PINNED_HELPER_SIZE == "52218"
    helper = (
        ROOT / "scripts" / "quality" / "capture_isolated_benchmarks.py"
    ).read_bytes()
    assert len(helper) == int(activation_template.PINNED_HELPER_SIZE)
    assert (
        hashlib.sha256(helper).hexdigest() == activation_template.PINNED_HELPER_SHA256
    )
    assert "UNBOUND_HELPER_" not in source
    assert "reviewed_helper_pin_unbound" in source
    assert "helper_content_sha256_mismatch" in source


def test_main_push_activation_is_exact_canonical_main_with_a_bound_source_head() -> (
    None
):
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert 'push_ref != "refs/heads/main"' in source
    assert "repository != CANONICAL_REPOSITORY" in source
    assert "source_head_sha != candidate_sha" in source
    assert "main_push_source_candidate_mismatch" in source
    assert "_first_main_transition_uses_candidate" in source


def test_existing_comparator_budget_and_measurement_population_are_unchanged() -> None:
    compare_workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    benchmark = compare_workflow["jobs"]["ws-hub-regression"]
    compare_step = next(
        step
        for step in benchmark["steps"]
        if step.get("name") == "Compare paired benchmark evidence"
    )
    assert "BASE_COMPARATOR" in compare_step["run"]
    assert "--expected-pairs 12" in compare_step["run"]

    helper = (
        ROOT / "scripts" / "quality" / "capture_isolated_benchmarks.py"
    ).read_text(encoding="utf-8")
    comparator = (
        ROOT / "scripts" / "quality" / "compare_paired_benchmarks.py"
    ).read_text(encoding="utf-8")
    assert "PAIR_COUNT = 12" in helper
    assert "EXPECTED_PAIRS = 12" in comparator
    assert "THRESHOLD_RATIO = 1.10" in comparator
    assert "BOOTSTRAP_ITERATIONS = 10_000" in comparator
    assert "CONFIDENCE = 0.95" in comparator
