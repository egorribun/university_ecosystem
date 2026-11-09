from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _rendered_image(image: dict[str, str]) -> str:
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", image["digest"])
    return f"{image['registry']}/{image['repository']}@{image['digest']}"


def test_owner_review_allowlist_is_exact_current_chart_output() -> None:
    values = yaml.safe_load(
        (REPOSITORY_ROOT / "charts" / "university-ecosystem" / "values.yaml").read_text(
            encoding="utf-8"
        )
    )
    images = [
        values["redis"]["image"],
        values["redis"]["metrics"]["image"],
        values["nats"]["container"]["image"],
    ]
    expected = {_rendered_image(image) for image in images}
    policy = (REPOSITORY_ROOT / "k8s" / "kyverno" / "cluster-policies.yaml").read_text(
        encoding="utf-8"
    )
    explicit_dockerhub_refs = {
        image
        for image in re.findall(r"container\.image == '([^']+)'", policy)
        if image.startswith("docker.io/")
    }
    fixture = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "k8s"
            / "kyverno"
            / "tests"
            / "restrict-image-registries"
            / "staging-dependencies-pod.yaml"
        ).read_text(encoding="utf-8")
    )
    fixture_images = {container["image"] for container in fixture["spec"]["containers"]}

    assert len(expected) == 3
    assert explicit_dockerhub_refs == expected
    assert fixture_images == expected


def test_staging_allowlist_candidate_requires_external_digest_match() -> None:
    staging_values = yaml.safe_load(
        (
            REPOSITORY_ROOT / "charts" / "university-ecosystem" / "values-staging.yaml"
        ).read_text(encoding="utf-8")
    )
    deploy_script = (
        REPOSITORY_ROOT / ".github" / "scripts" / "deploy-helm.sh"
    ).read_text(encoding="utf-8")
    deploy_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
    ).read_text(encoding="utf-8")
    contract = (
        REPOSITORY_ROOT
        / "charts"
        / "university-ecosystem"
        / "templates"
        / "deployment-contract.yaml"
    ).read_text(encoding="utf-8")

    assert staging_values["redis"]["image"]["digest"] == "REQUIRED_SHA256_DIGEST"
    assert (
        staging_values["redis"]["metrics"]["image"]["digest"]
        == "REQUIRED_SHA256_DIGEST"
    )
    assert (
        staging_values["nats"]["container"]["image"]["digest"]
        == "REQUIRED_SHA256_DIGEST"
    )
    for name in (
        "REDIS_IMAGE_DIGEST",
        "REDIS_METRICS_IMAGE_DIGEST",
        "NATS_IMAGE_DIGEST",
    ):
        assert f"{name}: ${{{{ vars.{name} }}}}" in deploy_workflow
        assert f"${name}" in deploy_script
    assert '"nats" (printf "%s/%s@%s"' in contract
    assert ".Values.nats.container.image.digest" in contract
