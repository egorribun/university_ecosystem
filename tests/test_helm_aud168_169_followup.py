from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import (
    _render_staging,
    _values,
)

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
STAGING_VALUES = CHART / "values-staging.yaml"


@pytest.fixture(scope="module")
def release_resources() -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    release_name = "aud168-169-contract"
    values = _values(STAGING_VALUES)
    values["connections"] = {
        **_values(CHART / "values.yaml")["connections"],
        **values["connections"],
    }
    elasticsearch_url = "https://aud168-169.elasticsearch.staging.internal"
    values["backend"]["config"]["elasticsearchURL"] = elasticsearch_url
    return (
        release_name,
        values,
        _render_staging(
            "--set-string",
            f"backend.config.elasticsearchURL={elasticsearch_url}",
            release_name=release_name,
        ),
    )


def _migration_pod_and_container(
    resources: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    job = next(
        resource
        for resource in resources
        if resource.get("kind") == "Job"
        and resource["metadata"]["name"].endswith("-migrate")
    )
    pod_spec = job["spec"]["template"]["spec"]
    container = next(
        item for item in pod_spec["containers"] if item["name"] == "migrate"
    )
    return pod_spec, container


def _job_environment(resources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    _, container = _migration_pod_and_container(resources)
    return {item["name"]: item for item in container["env"]}


def _assert_projected_secret(
    pod_spec: dict[str, Any],
    container: dict[str, Any],
    *,
    volume_name: str,
    secret_name: str,
    expected_keys: set[str],
) -> None:
    volumes = [
        volume
        for volume in pod_spec.get("volumes", [])
        if volume["name"] == volume_name
    ]
    assert len(volumes) == 1
    secret_volume = volumes[0]["secret"]
    assert secret_volume["secretName"] == secret_name
    assert secret_volume.get("optional", False) is False
    assert secret_volume["defaultMode"] == 0o440
    items = secret_volume["items"]
    assert len(items) == len(expected_keys)
    assert {item["key"]: item["path"] for item in items} == {
        key: key for key in expected_keys
    }

    mounts = [
        mount
        for mount in container.get("volumeMounts", [])
        if mount["name"] == volume_name
    ]
    assert len(mounts) == 1
    mount = mounts[0]
    assert mount["mountPath"] == f"/run/secrets/{secret_name}"
    assert mount["readOnly"] is True
    assert "subPath" not in mount


def test_migration_settings_use_release_environment_and_required_secrets(
    release_resources: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> None:
    release_name, values, resources = release_resources
    pod_spec, container = _migration_pod_and_container(resources)
    environment = {item["name"]: item for item in container["env"]}
    application_secret = values["applicationSecrets"]["existingSecret"] or (
        f"{release_name}-secrets"
    )
    connection_secret = values["connections"]["existingSecret"]

    assert environment["ENVIRONMENT"]["value"] == values["global"]["environment"]
    assert environment["APP_PROCESS_ROLE"]["value"] == "api"
    assert environment["REVOCATION_REDIS_ACCESS_ENABLED"]["value"] == "true"
    assert environment["AUTO_CREATE_SCHEMA"]["value"] == "false"
    assert "CI" not in environment
    assert "GITHUB_ACTIONS" not in environment
    assert (
        environment["EVENT_FILE_SCANNER_ENABLED"]["value"]
        == str(values["backend"]["config"]["eventFileScannerEnabled"]).lower()
    )
    assert (
        environment["MINIO_SECURE"]["value"]
        == str(values["backend"]["config"]["minioSecure"]).lower()
    )
    assert (
        environment["ELASTICSEARCH_URL"]["value"]
        == values["backend"]["config"]["elasticsearchURL"]
    )

    application_key_references = (
        ("SECRET_KEY", "jwt-secret"),
        ("AUDIT_LOG_SECRET", "audit-log-secret"),
        ("ELASTICSEARCH_PASSWORD", "elasticsearch-password"),
        ("INTERNAL_AUTH_TOKEN", "ws-hub-internal-secret"),
        ("INTERNAL_HMAC_SECRET", "internal-hmac-secret"),
        ("SPICEDB_PRESHARED_KEY", "spicedb-preshared-key"),
        ("SPOTIFY_TOKEN_SECRET", "spotify-token-secret"),
        ("TOKEN_HMAC_SECRET", "token-hmac-secret"),
        ("WS_HUB_INTERNAL_SECRET", "ws-hub-internal-secret"),
    )
    expected_application_keys = {key for _, key in application_key_references}
    for environment_name, expected_key in application_key_references:
        file_env = environment[f"{environment_name}_FILE"]
        assert file_env["value"] == f"/run/secrets/{application_secret}/{expected_key}"
        assert "valueFrom" not in file_env
        assert environment_name not in environment

    connection_secret_keys = {
        "DATABASE_URL": values["connections"]["databaseURLKey"],
        "CACHE_REDIS_URL": values["connections"]["redisBackendURLKey"],
        "REVOCATION_REDIS_URL": values["connections"]["redisRevocationURLKey"],
        "NATS_AUTH_TOKEN": values["connections"]["natsAuthTokenKey"],
    }
    for environment_name, secret_key in connection_secret_keys.items():
        file_env = environment[f"{environment_name}_FILE"]
        assert file_env["value"] == f"/run/secrets/{connection_secret}/{secret_key}"
        assert "valueFrom" not in file_env
        assert environment_name not in environment

    expected_secret_volumes = {"secret-application", "secret-connections"}
    assert {
        volume["name"] for volume in pod_spec.get("volumes", []) if "secret" in volume
    } == expected_secret_volumes
    assert {
        mount["name"]
        for mount in container.get("volumeMounts", [])
        if mount["name"] in expected_secret_volumes
    } == expected_secret_volumes
    _assert_projected_secret(
        pod_spec,
        container,
        volume_name="secret-application",
        secret_name=application_secret,
        expected_keys=expected_application_keys,
    )
    _assert_projected_secret(
        pod_spec,
        container,
        volume_name="secret-connections",
        secret_name=connection_secret,
        expected_keys=set(connection_secret_keys.values()),
    )
    assert not any(
        "secretKeyRef" in item.get("valueFrom", {}) for item in container["env"]
    )
    expected_file_paths = {
        f"/run/secrets/{application_secret}/{key}" for key in expected_application_keys
    } | {
        f"/run/secrets/{connection_secret}/{key}"
        for key in connection_secret_keys.values()
    }
    actual_file_paths = {
        item.get("value")
        for item in container["env"]
        if item["name"].endswith("_FILE") or item["name"] == "JWT_PRIVATE_KEY_PATH"
    }
    assert actual_file_paths == expected_file_paths


def _egress_signature(rule: dict[str, Any]) -> tuple[Any, ...]:
    destinations = tuple(
        sorted(
            tuple(sorted(destination["podSelector"]["matchLabels"].items()))
            for destination in rule.get("to", [])
            if "podSelector" in destination
        )
    )
    ip_blocks = tuple(
        sorted(
            destination["ipBlock"]["cidr"]
            for destination in rule.get("to", [])
            if "ipBlock" in destination
        )
    )
    ports = tuple(
        sorted((port["protocol"], int(port["port"])) for port in rule["ports"])
    )
    return destinations, ip_blocks, ports


def test_file_processor_revocation_egress_is_release_scoped(
    release_resources: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> None:
    release_name, _, resources = release_resources
    deployment = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == "file-processor"
    )
    pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert pod_labels[f"{release_name}-nats-client"] == "true"
    assert pod_labels[f"{release_name}-revocation-redis-client"] == "true"

    policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-file-processor-policy"
    )
    revocation_selector = (
        ("app.kubernetes.io/component", "master"),
        ("app.kubernetes.io/name", "revocation-redis"),
        ("university-ecosystem.io/revocation-store-for", release_name),
    )
    backend_selector = tuple(
        sorted(
            {
                "app.kubernetes.io/component": "backend",
                "app.kubernetes.io/name": pod_labels["app.kubernetes.io/name"],
                "app.kubernetes.io/instance": pod_labels["app.kubernetes.io/instance"],
            }.items()
        )
    )
    signatures = {_egress_signature(rule) for rule in policy["spec"]["egress"]}
    assert len(signatures) == len(policy["spec"]["egress"])
    assert signatures == {
        (((("app.kubernetes.io/name", "nats"),),), (), (("TCP", 4222),)),
        (((("app.kubernetes.io/name", "temporal"),),), (), (("TCP", 7233),)),
        (((("app.kubernetes.io/name", "minio"),),), (), (("TCP", 9000),)),
        ((revocation_selector,), (), (("TCP", 6379),)),
        ((backend_selector,), (), (("TCP", 8000),)),
        (((("app.kubernetes.io/name", "otel-collector"),),), (), (("TCP", 4317),)),
        # AUD-189: TCP 443 reaches public destinations only (cluster, private and
        # link-local ranges are excepted), not any address.
        ((), ("0.0.0.0/0", "::/0"), (("TCP", 443),)),
        (((("k8s-app", "kube-dns"),),), (), (("TCP", 53), ("UDP", 53))),
    }


def _edge_proxy_environment(
    resources: list[dict[str, Any]], component: str
) -> dict[str, str]:
    deployment = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == component
    )
    environment = {
        item["name"]: item["value"]
        for container in deployment["spec"]["template"]["spec"]["containers"]
        for item in container.get("env", [])
        if "value" in item
    }
    return environment


def _ingress_backend_names(resources: list[dict[str, Any]]) -> set[str]:
    ingress = next(
        resource for resource in resources if resource.get("kind") == "Ingress"
    )
    return {
        path["backend"]["service"]["name"]
        for rule in ingress["spec"]["rules"]
        for path in rule["http"]["paths"]
    }


def _proxy_list_override(path: str, proxies: tuple[str, ...]) -> tuple[str, str]:
    encoded = json.dumps(list(proxies), separators=(",", ":"))
    return "--set-json", f"{path}={encoded}"


def _assert_staging_proxy_guard_rejects(
    service: str, expected_message: str, *overrides: str
) -> None:
    with pytest.raises(subprocess.CalledProcessError) as failure:
        _render_staging(*overrides, release_name=f"aud167-{service}-proxy-guard")

    output = (failure.value.stderr or "") + (failure.value.stdout or "")
    # Match the intentional template guard, not a schema/type or CLI failure.
    assert expected_message.lower() in output.lower()


GATEWAY_VALID_PROXIES = ("192.0.2.11/32", "2001:db8::11")
WS_HUB_VALID_PROXIES = ("198.51.100.12/32", "2001:db8::12")


@pytest.mark.parametrize(
    ("service", "gateway_proxies", "ws_hub_proxies", "expected_message"),
    [
        (
            "gateway",
            (),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("127.0.0.1",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("   ",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("127.0.0.2/32",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("127.0.0.0/8",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("127.0.0.1", "::1"),
            "wsHub.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("::1/128",),
            "wsHub.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("0.0.0.0/0",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust 0.0.0.0/0 or ::/0; configure explicit ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("127.0.0.1", "::1", "::/0"),
            "wsHub.config.trustedProxies must not trust 0.0.0.0/0 or ::/0; configure explicit ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("192.0.2.7", "::/1"),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust an IPv6 /1 half-space; configure explicit ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("203.0.113.11", "8000:0000::/001"),
            "wsHub.config.trustedProxies must not trust an IPv6 /1 half-space; configure explicit ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("192.0.2.7", "fc00::/7"),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust the IPv6 unique-local block fc00::/7 or a supernet covering it; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("198.51.100.30", "fd12:3456::/07"),
            "wsHub.config.trustedProxies must not trust the IPv6 unique-local block fc00::/7 or a supernet covering it; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("203.0.113.15", "fc00::/6"),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust the IPv6 unique-local block fc00::/7 or a supernet covering it; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("192.0.2.30", "2000::/3"),
            "wsHub.config.trustedProxies must not trust the IPv6 global-unicast block 2000::/3 or a supernet covering it; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("198.51.100.8", "2001:db8::/003"),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust the IPv6 global-unicast block 2000::/3 or a supernet covering it; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("192.0.2.9", "0000::/2"),
            "wsHub.config.trustedProxies must not trust the IPv6 global-unicast block 2000::/3 or a supernet covering it; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("192.0.2.7", "::ffff:0:0/96"),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust the IPv4-mapped IPv6 all-IPv4 range; use native IPv4 addresses or CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("203.0.113.11", "0:0:0:0:0:ffff:0:0/96"),
            "wsHub.config.trustedProxies must not trust the IPv4-mapped IPv6 all-IPv4 range; use native IPv4 addresses or CIDRs",
        ),
        (
            "gateway",
            ("::ffff:0:0/096",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust the IPv4-mapped IPv6 all-IPv4 range; use native IPv4 addresses or CIDRs",
        ),
        (
            "gateway",
            ("::ffff:127.0.0.0/104",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("::0001/128",),
            "wsHub.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("0.0.0.0/00",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust 0.0.0.0/0 or ::/0; configure explicit ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("::/00",),
            "wsHub.config.trustedProxies must not trust 0.0.0.0/0 or ::/0; configure explicit ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("127.0.0.1/032",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("::1/0128",),
            "wsHub.config.trustedProxies requires explicit non-loopback ingress proxy CIDRs",
        ),
        (
            "gateway",
            ("10.0.0.0/8",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("203.0.113.11", "10.0.0.0/8"),
            "wsHub.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("010.000.000.000/08",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("172.16.0.0/12",),
            "wsHub.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("172.31.255.255/012",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("192.168.4.5/016",),
            "wsHub.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("10.0.0.0/07",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("172.16.0.0/011",),
            "wsHub.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "gateway",
            ("192.168.0.0/015",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies must not trust an RFC1918 block or a supernet covering one; use a narrower explicit ingress CIDR",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("203.0.113.11", "::ffff:203.0.113.11/128"),
            "wsHub.config.trustedProxies contains IPv4-mapped IPv6 peers; use native IPv4 addresses or CIDRs",
        ),
        (
            "gateway",
            ("192.0.2.7", "192.0.2.8/33"),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies entries must be valid IP addresses or CIDRs",
        ),
        (
            "ws-hub",
            GATEWAY_VALID_PROXIES,
            ("2001:db8::1/129",),
            "wsHub.config.trustedProxies entries must be valid IP addresses or CIDRs",
        ),
        (
            "gateway",
            ("2001:db8:::1",),
            WS_HUB_VALID_PROXIES,
            "gateway.config.trustedProxies entries must be valid IP addresses or CIDRs",
        ),
    ],
)
def test_staging_ingress_rejects_missing_loopback_or_universal_proxy_trust(
    service: str,
    gateway_proxies: tuple[str, ...],
    ws_hub_proxies: tuple[str, ...],
    expected_message: str,
) -> None:
    # TEST-NET proxy addresses are test fixtures only, never deployment values.
    overrides: list[str] = []
    overrides.extend(
        _proxy_list_override("gateway.config.trustedProxies", gateway_proxies)
    )
    overrides.extend(
        _proxy_list_override("wsHub.config.trustedProxies", ws_hub_proxies)
    )
    _assert_staging_proxy_guard_rejects(service, expected_message, *overrides)


def test_staging_ingress_accepts_explicit_gateway_and_ws_hub_proxy_chains() -> None:
    # TEST-NET and IPv6 documentation addresses are fixtures, not deployment values.
    gateway_proxies = (
        "192.0.2.7",
        "2001:db8::7",
        "::ffff:127.0.0.0/104",
    )
    ws_hub_proxies = (
        "127.0.0.1",
        "::1",
        "::0001/0128",
        "::ffff:127.0.0.0/104",
        "203.0.113.11",
        "2001:db8::b",
    )
    resources = _render_staging(
        *_proxy_list_override("gateway.config.trustedProxies", gateway_proxies),
        *_proxy_list_override("wsHub.config.trustedProxies", ws_hub_proxies),
        release_name="aud167-explicit-proxy-chain",
    )

    gateway_environment = _edge_proxy_environment(resources, "gateway")
    ws_hub_environment = _edge_proxy_environment(resources, "ws-hub")
    assert gateway_environment["GATEWAY_TRUSTED_PROXIES"] == ",".join(gateway_proxies)
    assert ws_hub_environment["TRUSTED_PROXIES"] == ",".join(ws_hub_proxies)

    backend_names = _ingress_backend_names(resources)
    assert any(name.endswith("-gateway") for name in backend_names)
    assert any(name.endswith("-ws-hub") for name in backend_names)


def test_staging_ingress_accepts_narrow_private_proxy_subnets() -> None:
    gateway_proxies = ("10.24.0.0/24", "2001:db8::7/64")
    ws_hub_proxies = ("172.20.4.0/24", "2001:db8::8/128")
    resources = _render_staging(
        *_proxy_list_override("gateway.config.trustedProxies", gateway_proxies),
        *_proxy_list_override("wsHub.config.trustedProxies", ws_hub_proxies),
        release_name="aud167-narrow-private-proxy-peers",
    )

    gateway_environment = _edge_proxy_environment(resources, "gateway")
    ws_hub_environment = _edge_proxy_environment(resources, "ws-hub")
    assert gateway_environment["GATEWAY_TRUSTED_PROXIES"] == ",".join(gateway_proxies)
    assert ws_hub_environment["TRUSTED_PROXIES"] == ",".join(ws_hub_proxies)


def test_staging_ingress_accepts_narrow_ula_and_global_ipv6_proxy_peers() -> None:
    # Synthetic range fixtures exercise address classification, not live topology.
    gateway_proxies = ("fd12:3456:789a::/64", "2606:4700::/48")
    ws_hub_proxies = ("fc12:3456:789a::/64", "2a00:1450::/48")
    resources = _render_staging(
        *_proxy_list_override("gateway.config.trustedProxies", gateway_proxies),
        *_proxy_list_override("wsHub.config.trustedProxies", ws_hub_proxies),
        release_name="aud167-narrow-ula-and-global-ipv6-proxy-peers",
    )

    gateway_environment = _edge_proxy_environment(resources, "gateway")
    ws_hub_environment = _edge_proxy_environment(resources, "ws-hub")
    assert gateway_environment["GATEWAY_TRUSTED_PROXIES"] == ",".join(gateway_proxies)
    assert ws_hub_environment["TRUSTED_PROXIES"] == ",".join(ws_hub_proxies)


def test_ingress_without_gateway_or_ws_hub_routes_needs_no_proxy_ranges(
    tmp_path: Path,
) -> None:
    overlay = tmp_path / "frontend-only-ingress.yaml"
    overlay.write_text(
        """ingress:
  hosts:
    - host: university.staging.example.org
      paths:
        - path: /
          pathType: Prefix
          service: frontend
    - host: api.university.staging.example.org
      paths:
        - path: /
          pathType: Prefix
          service: frontend
""",
        encoding="utf-8",
    )
    resources = _render_staging(
        "--values",
        str(overlay),
        *_proxy_list_override("gateway.config.trustedProxies", ()),
        *_proxy_list_override("wsHub.config.trustedProxies", ("127.0.0.1", "::1")),
        release_name="aud167-no-go-edge-routes",
    )

    backend_names = _ingress_backend_names(resources)
    assert backend_names
    assert all(name.endswith("-frontend") for name in backend_names)


def test_development_ingress_with_loopback_only_proxy_lists_is_allowed() -> None:
    resources = _render_staging(
        "--set-string",
        "global.environment=development",
        *_proxy_list_override("gateway.config.trustedProxies", ("127.0.0.1",)),
        *_proxy_list_override("wsHub.config.trustedProxies", ("127.0.0.1", "::1")),
        release_name="aud167-development-ingress",
    )

    backend_names = _ingress_backend_names(resources)
    assert any(name.endswith("-gateway") for name in backend_names)
    assert any(name.endswith("-ws-hub") for name in backend_names)


def test_development_without_ingress_renders_without_proxy_requirements() -> None:
    resources = _render_staging(
        "--set-string",
        "global.environment=development",
        "--set",
        "ingress.enabled=false",
        *_proxy_list_override("gateway.config.trustedProxies", ()),
        *_proxy_list_override("wsHub.config.trustedProxies", ("127.0.0.1", "::1")),
        release_name="aud167-development-direct",
    )

    assert not any(resource.get("kind") == "Ingress" for resource in resources)
