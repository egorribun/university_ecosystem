"""Render contracts for file-processor and outbox-worker external egress (AUD-189).

The guards fail chart rendering when an external MinIO or Elasticsearch endpoint
has no owner-declared TCP 443 CIDRs, and they reject broad CIDR prefixes. The
CIDRs used here are reserved TEST-NET documentation ranges, never deployment
values.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
RELEASE = "egress-guard"
NAMESPACE = "university-ecosystem"
HELM = shutil.which("helm")
TEST_NET_CIDR = "192.0.2.0/24"
EXTERNAL_MINIO_MESSAGE = (
    "networkPolicy.fileProcessorHTTPSEgress.egressCIDRs must contain owner-verified "
    "CIDRs when fileProcessor.config.minioEndpoint is external"
)
EXTERNAL_ELASTICSEARCH_MESSAGE = (
    "networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs must contain owner-verified "
    "CIDRs when backend.config.elasticsearchURL is external"
)

pytestmark = pytest.mark.skipif(HELM is None, reason="Helm is not installed")

BASE_ARGS = (
    "--namespace",
    NAMESPACE,
    "--set-string",
    "global.environment=development",
    "--set-string",
    "applicationSecrets.existingSecret=ci-application-secrets",
    "--set-string",
    "global.imageTag=0123456789abcdef0123456789abcdef01234567",
)


def _render(
    *overrides: str, skip_schema: bool = False, release: str = RELEASE
) -> subprocess.CompletedProcess[str]:
    command = [str(HELM), "template", release, str(CHART), *BASE_ARGS]
    if skip_schema:
        command.append("--skip-schema-validation")
    command.extend(overrides)
    return subprocess.run(  # noqa: S603 - fixed local Helm contract command
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def _rendered(*overrides: str, release: str = RELEASE) -> list[dict[str, Any]]:
    result = _render(*overrides, release=release)
    assert result.returncode == 0, result.stderr
    return [
        item for item in yaml.safe_load_all(result.stdout) if isinstance(item, dict)
    ]


def _policy(
    resources: list[dict[str, Any]], suffix: str, release: str = RELEASE
) -> dict[str, Any]:
    matches = [
        item
        for item in resources
        if item.get("kind") == "NetworkPolicy"
        and item["metadata"]["name"] == f"{release}{suffix}"
    ]
    assert len(matches) == 1, suffix
    return matches[0]


def _ipblock_egress(policy: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        (rule["to"][0]["ipBlock"]["cidr"], rule.get("ports", []))
        for rule in policy["spec"]["egress"]
        if rule.get("to")
        and "ipBlock" in rule["to"][0]
        and rule["to"][0]["ipBlock"]["cidr"] != "0.0.0.0/0"
        and rule["to"][0]["ipBlock"]["cidr"] != "::/0"
    ]


def _assert_fails(result: subprocess.CompletedProcess[str], message: str) -> None:
    assert result.returncode != 0
    assert message in result.stderr, result.stderr


@pytest.mark.parametrize(
    "endpoint",
    [
        "minio.example.test",
        "minio.example.test:443",
        "https://minio.example.test",
        "minio.university-ecosystem.svc.cluster.example.test:443",
    ],
)
def test_external_minio_without_cidrs_fails_the_render(endpoint: str) -> None:
    _assert_fails(
        _render("--set-string", f"fileProcessor.config.minioEndpoint={endpoint}"),
        EXTERNAL_MINIO_MESSAGE,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "minio:9000",
        "minio.university-ecosystem.svc:9000",
        "minio.university-ecosystem.svc.cluster.local:9000",
    ],
)
def test_in_cluster_minio_renders_without_external_egress(endpoint: str) -> None:
    resources = _rendered(
        "--set-string", f"fileProcessor.config.minioEndpoint={endpoint}"
    )
    file_processor = _policy(resources, "-file-processor-policy")
    assert _ipblock_egress(file_processor) == []
    minio_rules = [
        rule
        for rule in file_processor["spec"]["egress"]
        if rule.get("to")
        and rule["to"][0].get("podSelector", {}).get("matchLabels", {})
        == {"app.kubernetes.io/name": "minio"}
    ]
    assert minio_rules == [
        {
            "to": [
                {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "minio"}}}
            ],
            "ports": [{"protocol": "TCP", "port": 9000}],
        }
    ]


def test_external_minio_with_declared_cidr_adds_only_that_443_rule() -> None:
    resources = _rendered(
        "--set-string",
        "fileProcessor.config.minioEndpoint=minio.example.test:443",
        "--set-json",
        f'networkPolicy.fileProcessorHTTPSEgress.egressCIDRs=["{TEST_NET_CIDR}"]',
    )
    file_processor = _policy(resources, "-file-processor-policy")
    assert _ipblock_egress(file_processor) == [
        (TEST_NET_CIDR, [{"protocol": "TCP", "port": 443}])
    ]
    outbox = _policy(resources, "-outbox-worker-policy")
    assert _ipblock_egress(outbox) == []


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("minio:9001", "must use port 9000"),
        ("minio.university-ecosystem.svc.cluster.local:9001", "must use port 9000"),
        ("minio.example.test:9000", "must use TCP 443"),
        ("minio.other.svc.cluster.local:9000", "must use TCP 443"),
    ],
)
def test_minio_endpoint_port_must_match_the_declared_egress(
    endpoint: str, message: str
) -> None:
    result = _render(
        "--set-string",
        f"fileProcessor.config.minioEndpoint={endpoint}",
        "--set-json",
        f'networkPolicy.fileProcessorHTTPSEgress.egressCIDRs=["{TEST_NET_CIDR}"]',
    )
    _assert_fails(result, message)


def test_external_elasticsearch_without_cidrs_fails_the_render() -> None:
    _assert_fails(
        _render(
            "--set-string", "backend.config.elasticsearchURL=https://es.example.test"
        ),
        EXTERNAL_ELASTICSEARCH_MESSAGE,
    )


def test_external_elasticsearch_with_declared_cidr_opens_outbox_443_only() -> None:
    resources = _rendered(
        "--set-string",
        "backend.config.elasticsearchURL=https://es.example.test",
        "--set-json",
        f'networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs=["{TEST_NET_CIDR}"]',
    )
    outbox = _policy(resources, "-outbox-worker-policy")
    assert _ipblock_egress(outbox) == [
        (TEST_NET_CIDR, [{"protocol": "TCP", "port": 443}])
    ]
    file_processor = _policy(resources, "-file-processor-policy")
    assert _ipblock_egress(file_processor) == []


def test_in_cluster_elasticsearch_fails_closed_for_outbox_without_a_peer() -> None:
    _assert_fails(
        _render("--set-string", "backend.config.elasticsearchURL=elasticsearch:9200"),
        "names an in-cluster service, but this chart has no NetworkPolicy peer",
    )


def test_disabled_elasticsearch_and_disabled_outbox_need_no_cidrs() -> None:
    _rendered("--set-string", "backend.config.elasticsearchURL=")
    _rendered(
        "--set-string",
        "backend.config.elasticsearchURL=https://es.example.test",
        "--set",
        "outboxWorker.enabled=false",
    )


def test_embedding_key_with_default_external_base_needs_declared_cidrs() -> None:
    _assert_fails(
        _render("--set-string", "outboxWorker.env.EMBEDDING_API_KEY=placeholder-key"),
        "outboxWorkerHTTPSEgress.egressCIDRs must contain owner-verified CIDRs when outboxWorker.env enables embeddings",
    )


def test_embedding_with_declared_cidr_renders_outbox_443_rule() -> None:
    resources = _rendered(
        "--set-string",
        "outboxWorker.env.EMBEDDING_API_KEY=placeholder-key",
        "--set-json",
        f'networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs=["{TEST_NET_CIDR}"]',
    )
    assert _ipblock_egress(_policy(resources, "-outbox-worker-policy")) == [
        (TEST_NET_CIDR, [{"protocol": "TCP", "port": 443}])
    ]


@pytest.mark.parametrize(
    "env_overrides",
    [
        {"SEMANTIC_SEARCH_ENABLED": "false"},
        {"EMBEDDING_API_BASE": "https://embeddings.example.test:9000"},
    ],
    ids=("semantic-disabled", "explicit-port-9000"),
)
def test_embedding_guard_only_applies_when_embeddings_would_run(
    env_overrides: dict[str, str],
) -> None:
    arguments = [
        "--set-string",
        "outboxWorker.env.EMBEDDING_API_KEY=placeholder-key",
    ]
    for key, value in env_overrides.items():
        arguments.extend(("--set-string", f"outboxWorker.env.{key}={value}"))
    if "EMBEDDING_API_BASE" in env_overrides:
        result = _render(
            *arguments,
            "--set-json",
            f'networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs=["{TEST_NET_CIDR}"]',
        )
        _assert_fails(result, "must use TCP 443 (AUD-189)")
    else:
        _rendered(*arguments)


def test_embedding_key_without_outbox_worker_needs_no_cidrs() -> None:
    _rendered(
        "--set-string",
        "outboxWorker.env.EMBEDDING_API_KEY=placeholder-key",
        "--set",
        "outboxWorker.enabled=false",
    )


def test_in_cluster_embedding_base_fails_closed_without_a_peer() -> None:
    _assert_fails(
        _render(
            "--set-string",
            "outboxWorker.env.EMBEDDING_API_KEY=placeholder-key",
            "--set-string",
            "outboxWorker.env.EMBEDDING_API_BASE=http://embeddings:8080",
        ),
        "names an in-cluster service, but this chart has no NetworkPolicy peer",
    )


RELEASE_SCOPED_COMPONENTS = {
    "backend",
    "gateway",
    "file-processor",
    "ws-hub",
    "frontend",
    "outbox-worker",
}


@pytest.mark.parametrize("release", ["scope-release-a", "scope-release-b"])
def test_every_component_selector_and_peer_is_release_scoped(release: str) -> None:
    resources = _rendered(release=release)
    checked = 0

    def visit(node: Any) -> None:
        nonlocal checked
        if isinstance(node, dict):
            labels = node.get("matchLabels")
            if isinstance(labels, dict):
                component = labels.get("app.kubernetes.io/component")
                if component in RELEASE_SCOPED_COMPONENTS:
                    checked += 1
                    assert labels.get("app.kubernetes.io/instance") == release, labels
                    assert (
                        labels.get("app.kubernetes.io/name") == "university-ecosystem"
                    ), labels
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for resource in resources:
        if resource.get("kind") == "NetworkPolicy":
            visit(resource["spec"])
    assert checked >= 8


def test_external_elasticsearch_must_use_443_for_outbox() -> None:
    _assert_fails(
        _render(
            "--set-string",
            "backend.config.elasticsearchURL=https://es.example.test:9200",
            "--set-json",
            f'networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs=["{TEST_NET_CIDR}"]',
        ),
        "must use TCP 443 for outbox-worker",
    )


@pytest.mark.parametrize(
    "cidr",
    ["10.0.0.0/8", "10.0.0.0/24", "192.0.2.1/32", "2001:db8::/16", "2001:db8::/32"],
)
def test_prefixes_in_the_allowed_range_render(cidr: str) -> None:
    _rendered(
        "--set-json",
        f'networkPolicy.fileProcessorHTTPSEgress.egressCIDRs=["{cidr}"]',
        "--set-json",
        f'networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs=["{cidr}"]',
    )


@pytest.mark.parametrize(
    ("cidr", "message"),
    [
        ("10.0.0.0/1", "must be an IPv4 CIDR with prefix /8 to /32"),
        ("10.0.0.0/7", "must be an IPv4 CIDR with prefix /8 to /32"),
        ("::/8", "must be an IPv4 CIDR with prefix /8 to /32 or an IPv6 CIDR"),
        ("2001:db8::/15", "or an IPv6 CIDR with prefix /16 to /128"),
        ("0.0.0.0/0", "must not be a /0 range"),
        ("::/0", "must not be a /0 range"),
    ],
)
@pytest.mark.parametrize(
    "value_path",
    [
        "networkPolicy.fileProcessorHTTPSEgress.egressCIDRs",
        "networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs",
    ],
)
def test_broad_prefixes_are_rejected_without_relying_on_the_schema(
    cidr: str, message: str, value_path: str
) -> None:
    _assert_fails(
        _render(
            "--set-json",
            f'{value_path}=["{cidr}"]',
            skip_schema=True,
        ),
        message,
    )


def test_schema_rejects_the_default_route_before_template_rendering() -> None:
    result = _render(
        "--set-json",
        'networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs=["0.0.0.0/0"]',
    )
    assert result.returncode != 0
    assert "outboxWorkerHTTPSEgress" in result.stderr


def test_ws_hub_backend_peer_carries_the_release_instance_labels() -> None:
    resources = _rendered(release="ws-peer-release")
    backend = _policy(resources, "-backend-policy", release="ws-peer-release")
    ws_hub_peers = [
        peer
        for rule in backend["spec"]["ingress"]
        for peer in rule.get("from", [])
        if peer.get("podSelector", {})
        .get("matchLabels", {})
        .get("app.kubernetes.io/component")
        == "ws-hub"
    ]
    assert ws_hub_peers == [
        {
            "podSelector": {
                "matchLabels": {
                    "app.kubernetes.io/name": "university-ecosystem",
                    "app.kubernetes.io/instance": "ws-peer-release",
                    "app.kubernetes.io/component": "ws-hub",
                }
            }
        }
    ]


DEPLOY_SCRIPT = ROOT / ".github" / "scripts" / "deploy-helm.sh"
_DIGEST = "sha256:" + ("a" * 64)
# Kubernetes TLS Secret resource name, not credential material.
_TLS_RESOURCE_NAME = "-".join(("university", "tls"))


def _deploy_environment(**overrides: str) -> dict[str, str]:
    """Staging inputs for the deploy renderer; external MinIO and Elasticsearch."""
    base = {
        "DEPLOY_ENVIRONMENT": "staging",
        "K8S_NAMESPACE": NAMESPACE,
        "HELM_RELEASE_NAME": RELEASE,
        "HELM_VALUES_FILE": str(CHART / "values-staging.yaml"),
        "CONNECTIONS_SECRET_NAME": "connections",  # pragma: allowlist secret
        "APPLICATION_SECRETS_NAME": "application",  # pragma: allowlist secret
        "REGISTRY": "ghcr.io",
        "GITHUB_REPOSITORY": "example/university",
        "DEPLOY_VERSION": "9d08136558b95d1182f889574f67b1b1d21abc9f",  # pragma: allowlist secret
        "BACKEND_IMAGE_DIGEST": _DIGEST,
        "FRONTEND_IMAGE_DIGEST": _DIGEST,
        "GATEWAY_IMAGE_DIGEST": _DIGEST,
        "FILE_PROCESSOR_IMAGE_DIGEST": _DIGEST,
        "WS_HUB_IMAGE_DIGEST": _DIGEST,
        "DEPLOYMENT_URL": "https://university.staging.example.org",
        "CWV_EXPORT_OIDC_SUBJECT": "repo:example/university:environment:staging",
        "FRONTEND_HOST": "university.staging.example.org",
        "API_HOST": "api.university.staging.example.org",
        "TLS_SECRET_NAME": _TLS_RESOURCE_NAME,
        "CERT_MANAGER_ISSUER_NAME": "university-issuer",
        "ELASTICSEARCH_URL": "es.staging.example.org",
        "FLAGD_HOST": "flagd.staging.example.org",
        "OTLP_ENDPOINT": "otel.staging.example.org:4317",
        "MINIO_ENDPOINT": "minio.staging.example.org:443",
        "TEMPORAL_HOST": "temporal.staging.example.org:7233",
        "REDIS_IMAGE_DIGEST": _DIGEST,
        "REDIS_METRICS_IMAGE_DIGEST": _DIGEST,
        "NATS_IMAGE_DIGEST": _DIGEST,
        "GITHUB_RUN_ID": "1",
        "GITHUB_RUN_ATTEMPT": "1",
        "MINIO_EGRESS_CIDRS": "",
        "ELASTICSEARCH_EGRESS_CIDRS": "",
    }
    base.update(overrides)
    return base


def _run_deploy_render(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    from tests.test_mfa_helm_contract import _bash

    return subprocess.run(  # noqa: S603 - fixed repository deploy renderer
        [_bash(), str(DEPLOY_SCRIPT), "render"],
        cwd=ROOT,
        env={**os.environ, **environment},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def test_deploy_fails_closed_without_minio_egress_cidrs() -> None:
    result = _run_deploy_render(_deploy_environment())
    assert result.returncode != 0
    assert "MINIO_ENDPOINT is external; set MINIO_EGRESS_CIDRS" in result.stderr


def test_deploy_fails_closed_without_elasticsearch_egress_cidrs() -> None:
    result = _run_deploy_render(_deploy_environment(MINIO_EGRESS_CIDRS=TEST_NET_CIDR))
    assert result.returncode != 0
    assert "ELASTICSEARCH_URL is external; set ELASTICSEARCH_EGRESS_CIDRS" in (
        result.stderr
    )


def test_deploy_passes_declared_cidrs_to_both_policies() -> None:
    from tests.test_mfa_helm_contract import _bash

    # Traced run: the renderer continues into helm after the CIDR gate, and helm
    # may still reject unrelated MFA staging inputs. The trace proves pass-through.
    result = subprocess.run(  # noqa: S603 - fixed repository deploy renderer
        [_bash(), "-x", str(DEPLOY_SCRIPT), "render"],
        cwd=ROOT,
        env={
            **os.environ,
            **_deploy_environment(
                MINIO_EGRESS_CIDRS=f" {TEST_NET_CIDR} ",
                ELASTICSEARCH_EGRESS_CIDRS="198.51.100.0/24, 2001:db8::/32",
            ),
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert "is external; set" not in result.stderr
    assert (
        "networkPolicy.fileProcessorHTTPSEgress.egressCIDRs[0]=192.0.2.0/24"
        in result.stderr
    )
    assert (
        "networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs[0]=198.51.100.0/24"
        in result.stderr
    )
    assert (
        "networkPolicy.outboxWorkerHTTPSEgress.egressCIDRs[1]=2001:db8::/32"
        in result.stderr
    )
