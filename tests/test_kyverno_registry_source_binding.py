from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_first_party_allowlist_tracks_release_workloads() -> None:
    build_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "build-release-images.yml"
    ).read_text(encoding="utf-8")
    deploy_script = (
        REPOSITORY_ROOT / ".github" / "scripts" / "deploy-helm.sh"
    ).read_text(encoding="utf-8")
    policy = (REPOSITORY_ROOT / "k8s" / "kyverno" / "cluster-policies.yaml").read_text(
        encoding="utf-8"
    )

    built_images = set(
        re.findall(r"^\s*- image_name: ([a-z0-9-]+)$", build_workflow, re.MULTILINE)
    )
    deployed_images = set(
        re.findall(
            r'--set-string "[A-Za-z0-9_]+\.image\.repository=\$REGISTRY/'
            r'\$GITHUB_REPOSITORY/([a-z0-9-]+)"',
            deploy_script,
        )
    )
    policy_match = re.search(
        r"container\.image\.matches\('\^ghcr\[\.\]io/"
        r"egorribun/university_ecosystem/\(([^)]+)\)",
        policy,
    )

    assert deployed_images == {
        "backend",
        "frontend",
        "gateway",
        "ws-hub",
        "file-processor",
    }
    assert built_images == deployed_images | {"caddy"}
    assert policy_match is not None
    assert set(policy_match.group(1).split("|")) == deployed_images


def test_flagd_fixture_and_policy_match_pinned_manifest_identity() -> None:
    flagd_manifest = REPOSITORY_ROOT / "k8s" / "flagd" / "deployment.yaml"
    kustomization = REPOSITORY_ROOT / "k8s" / "flagd" / "kustomization.yaml"
    fixture = (
        REPOSITORY_ROOT
        / "k8s"
        / "kyverno"
        / "tests"
        / "restrict-image-registries"
        / "flagd-pod.yaml"
    )
    policy = (REPOSITORY_ROOT / "k8s" / "kyverno" / "cluster-policies.yaml").read_text(
        encoding="utf-8"
    )

    deployment = next(
        resource
        for resource in yaml.safe_load_all(flagd_manifest.read_text(encoding="utf-8"))
        if resource
        and resource.get("kind") == "Deployment"
        and resource.get("metadata", {}).get("name") == "flagd"
    )
    expected_namespace = yaml.safe_load(kustomization.read_text(encoding="utf-8"))[
        "namespace"
    ]
    expected_image = next(
        container["image"]
        for container in deployment["spec"]["template"]["spec"]["containers"]
        if container["name"] == "flagd"
    )
    fixture_pod = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    fixture_image = fixture_pod["spec"]["containers"][0]["image"]

    assert expected_namespace == fixture_pod["metadata"]["namespace"]
    assert fixture_image == expected_image
    assert f"container.image == '{expected_image}'" in policy


def test_staging_dependency_hold_fixture_tracks_chart_digests() -> None:
    values = yaml.safe_load(
        (REPOSITORY_ROOT / "charts" / "university-ecosystem" / "values.yaml").read_text(
            encoding="utf-8"
        )
    )
    fixture_path = (
        REPOSITORY_ROOT
        / "k8s"
        / "kyverno"
        / "tests"
        / "restrict-image-registries"
        / "staging-dependencies-pod.yaml"
    )
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    actual_images = {container["image"] for container in fixture["spec"]["containers"]}
    dependency_images = {
        f"{values['redis']['image']['registry']}/{values['redis']['image']['repository']}@{values['redis']['image']['digest']}",
        f"{values['redis']['metrics']['image']['registry']}/{values['redis']['metrics']['image']['repository']}@{values['redis']['metrics']['image']['digest']}",
        f"{values['nats']['image']['registry']}/{values['nats']['image']['repository']}@{values['nats']['image']['digest']}",
    }

    assert dependency_images == actual_images
