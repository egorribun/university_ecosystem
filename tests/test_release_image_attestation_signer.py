"""Release image verification must authenticate its reusable signer workflow."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PRODUCER = WORKFLOWS / "build-release-images.yml"
BUILDER = WORKFLOWS / "reusable-build-and-sign.yml"


def _workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _verify_command(path: Path, job: str, step_name: str) -> list[str]:
    steps = _workflow(path)["jobs"][job]["steps"]
    matching_steps = [step for step in steps if step.get("name") == step_name]
    assert len(matching_steps) == 1
    body = str(matching_steps[0]["run"]).replace("\\\n", " ")
    commands = [
        line.strip()
        for line in body.splitlines()
        if line.strip().startswith("gh attestation verify ")
    ]
    assert len(commands) == 1
    return shlex.split(commands[0])


@pytest.mark.parametrize(
    ("workflow", "job", "step"),
    [
        (BUILDER, "build", "Verify final signature and attestation"),
        (
            PRODUCER,
            "aggregate-image-provenance",
            "Reverify every immutable image subject",
        ),
    ],
)
def test_image_attestation_verification_binds_the_actual_reusable_signer(
    workflow: Path, job: str, step: str
) -> None:
    producer = _workflow(PRODUCER)
    reusable_ref = producer["jobs"]["build"]["uses"]
    assert reusable_ref == "./.github/workflows/reusable-build-and-sign.yml"
    builder_steps = _workflow(BUILDER)["jobs"]["build"]["steps"]
    attestation_steps = [
        item
        for item in builder_steps
        if item.get("name") == "Attest build provenance for the published digest"
    ]
    assert len(attestation_steps) == 1
    assert attestation_steps[0]["uses"].startswith("actions/attest-build-provenance@")

    command = _verify_command(workflow, job, step)
    assert command.count("--signer-workflow") == 1
    signer = command[command.index("--signer-workflow") + 1]
    assert signer == f"$GITHUB_REPOSITORY/{reusable_ref.removeprefix('./')}"
