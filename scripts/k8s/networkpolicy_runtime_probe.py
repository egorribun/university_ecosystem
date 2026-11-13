"""Runtime NetworkPolicy probes for AUD-169, AUD-188, AUD-189 and AUD-438.

Run only against a disposable kind cluster created by
scripts/k8s/networkpolicy_runtime_proof.sh. The script:

1. renders the real university-ecosystem and revocation-store NetworkPolicies
   with the same staging-contract arguments the render tests use, for two
   releases (probe-a, probe-b), each in its own namespace;
2. deploys the revocation Redis StatefulSet from the store chart with a generated
   password Secret, and stand-in pods that carry the rendered pod-template labels
   of the file-processor, backend and ws-hub workloads, plus unrelated,
   monitoring, Prometheus-labelled and ingress-labelled sources;
3. proves every probe target is reachable before any policy is applied
   (baseline), applies the rendered policies, then runs the probe matrix with a
   same-destination control before and after every denied attempt;
4. runs the application-level checks (authenticated Redis PING, and RS256 JWKS
   acceptance across rotation) in the same enforced cluster;
5. writes a JSON receipt and exits non-zero on any mismatch or inconclusive row.

The file-processor and backend images are not run. The receipt's not_run list
states what remains unproven.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from networkpolicy_runtime_app import (
    all_passed,
    jwks_rotation_checks,
    new_redis_password,
    redis_checks,
    redis_ping,
)
from networkpolicy_runtime_kube import (
    Pod,
    apply_objects,
    find,
    helm_template,
    kubectl,
    kubectl_json,
    pod_template_labels,
    probe_connection,
)
from networkpolicy_runtime_rows import (
    BACKEND_PORT,
    PUBLIC_HTTPS_TARGET,
    REDIS_PORT,
    ROWS,
    WS_METRICS_PORT,
    WS_PUBLIC_PORT,
    Execute,
    evaluate_rows,
    make_executor,
    measure_baseline,
)
from networkpolicy_runtime_standins import service, stand_in_pod

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DOCKERFILE = ROOT / "backend.Dockerfile"
# The runtime stage of the backend image is the base for every stand-in pod.
RUNTIME_FROM = re.compile(
    r"^FROM (python:\S+@sha256:[0-9a-f]{64}) AS runtime[ \t]*\r?$", re.MULTILINE
)
RELEASES = ("probe-a", "probe-b")
UNRELATED_NS = "probe-unrelated"
MONITORING_NS = "monitoring"
INGRESS_NS = "ingress-nginx"
REDIS_AUTH_OBJECT_NAME = "revocation-redis-credentials"
REDIS_CREDENTIAL_ITEM_REF = "revocation-redis-password"
EXPORTER_INIT = "redis-exporter-password-file"
EXPORTER_CONTAINER = "metrics"
EXPORTER_VOLUME = "redis-exporter-auth"
RECEIPT_SCHEMA = "aud169-188-189-aud438-kind-networkpolicy-receipt/v2"

Rendered = dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]


def runtime_base_image() -> str:
    """Return the backend runtime stage's digest-pinned Python image, fail closed."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    matches = RUNTIME_FROM.findall(text)
    if len(matches) != 1:
        raise SystemExit(
            f"backend.Dockerfile must have exactly one python runtime FROM, found {len(matches)}"
        )
    return matches[0]


def load_render_contracts() -> tuple[Any, Any]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    app = importlib.import_module("tests.test_helm_staging_contract")
    store = importlib.import_module("tests.test_revocation_store_security_contract")
    return app, store


def real_redis_digest(store_contract: Any) -> str:
    """Return the store chart's pinned Redis digest, not the test placeholder."""
    values = yaml.safe_load(Path(store_contract.VALUES).read_text(encoding="utf-8"))
    digest: str = values["redis"]["image"]["digest"]
    return digest


def strip_metrics_exporter(store: list[dict[str, Any]]) -> None:
    """Remove the exporter sidecar and its password-file init from the rendered StatefulSet.

    The chart requires that init to use the private backend image, which kind cannot
    pull. The Redis server, the redis-auth-acl init that installs the password, the
    password Secret and the master Service are left exactly as rendered.
    """
    statefulsets = [r for r in store if r.get("kind") == "StatefulSet"]
    if len(statefulsets) != 1:
        raise SystemExit("expected exactly one revocation Redis StatefulSet")
    spec = statefulsets[0]["spec"]["template"]["spec"]
    spec["initContainers"] = [
        c for c in spec.get("initContainers", []) if c["name"] != EXPORTER_INIT
    ]
    spec["containers"] = [
        c for c in spec["containers"] if c["name"] != EXPORTER_CONTAINER
    ]
    spec["volumes"] = [v for v in spec["volumes"] if v["name"] != EXPORTER_VOLUME]
    if [c["name"] for c in spec["containers"]] != ["redis"]:
        raise SystemExit("revocation Redis pod must keep exactly the redis container")
    if "redis-auth-acl" not in [c["name"] for c in spec["initContainers"]]:
        raise SystemExit("revocation Redis pod lost its redis-auth-acl init container")


def render_release(
    release: str, app_contract: Any, store_contract: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    app = helm_template(
        release,
        app_contract.CHART,
        app_contract.STAGING_VALUES,
        [
            *app_contract._resolved_staging_args("192.0.2.0/24"),
            "--set-string",
            f"fullnameOverride={release}",
        ],
        release,
    )
    store = helm_template(
        f"{release}-bootstrap",
        store_contract.CHART,
        store_contract.VALUES,
        [
            *store_contract._resolved_args(release),
            "--set-string",
            f"redis.image.digest={real_redis_digest(store_contract)}",
        ],
        release,
    )
    strip_metrics_exporter(store)
    return app, store


def assert_rendered_ports(
    app: list[dict[str, Any]], store: list[dict[str, Any]], release: str
) -> None:
    """Fail closed if the rendered chart no longer matches the probe ports."""
    ws_policy = find(app, "NetworkPolicy", f"{release}-ws-hub-policy")
    ws_ports = {
        port["port"]
        for rule in ws_policy["spec"]["ingress"]
        for port in rule.get("ports", [])
    }
    if not {WS_PUBLIC_PORT, WS_METRICS_PORT} <= ws_ports:
        raise SystemExit(
            f"rendered ws-hub ingress ports {sorted(ws_ports)} differ from probe ports"
        )
    backend_policy = find(app, "NetworkPolicy", f"{release}-backend-policy")
    backend_ports = {
        port["port"]
        for rule in backend_policy["spec"]["ingress"]
        for port in rule.get("ports", [])
    }
    if BACKEND_PORT not in backend_ports:
        raise SystemExit(
            "rendered backend ingress does not admit the probe backend port"
        )
    find(store, "StatefulSet", f"{release}-revocation-redis-master")
    find(store, "Service", f"{release}-revocation-redis-master")


def render_all() -> Rendered:
    app_contract, store_contract = load_render_contracts()
    rendered: Rendered = {}
    for release in RELEASES:
        app, store = render_release(release, app_contract, store_contract)
        assert_rendered_ports(app, store, release)
        rendered[release] = (app, store)
    return rendered


def namespace_objects() -> list[dict[str, Any]]:
    names = [*RELEASES, UNRELATED_NS, MONITORING_NS, INGRESS_NS]
    return [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": name,
                "labels": {
                    "probe-run": "aud169-188-189",
                    "kubernetes.io/metadata.name": name,
                },
            },
        }
        for name in names
    ]


def credential_secret(namespace: str, password: str) -> dict[str, Any]:
    # The value is passed through the API only; it is never printed or recorded.
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": REDIS_AUTH_OBJECT_NAME, "namespace": namespace},
        "type": "Opaque",
        "stringData": {REDIS_CREDENTIAL_ITEM_REF: password},
    }


def apply_store_workloads(release: str, store: list[dict[str, Any]]) -> None:
    """Apply the real revocation Redis workloads, without their NetworkPolicies."""
    workloads = [r for r in store if r.get("kind") != "NetworkPolicy"]
    apply_objects(workloads)
    kubectl(
        "-n",
        release,
        "rollout",
        "status",
        f"statefulset/{release}-revocation-redis-master",
        "--timeout=300s",
    )


def standin_objects(
    rendered: Rendered, base_image: str
) -> tuple[list[dict[str, Any]], dict[str, Pod]]:
    objects: list[dict[str, Any]] = []
    specs: dict[str, Pod] = {}

    def add_pod(
        key: str, namespace: str, name: str, labels: dict[str, str], **listen: str
    ) -> None:
        objects.append(
            stand_in_pod(
                namespace,
                name,
                {**labels, "probe-role": key},
                base_image,
                listen.get("tcp", ""),
                listen.get("udp", ""),
            )
        )
        specs[key] = Pod(namespace, name)

    for release in RELEASES:
        app, _store = rendered[release]
        short = release.split("-")[-1]
        add_pod(
            f"{short}-fp",
            release,
            f"{release}-file-processor",
            pod_template_labels(app, "Deployment", f"{release}-file-processor"),
        )
        add_pod(
            f"{short}-backend",
            release,
            f"{release}-backend",
            pod_template_labels(app, "Deployment", f"{release}-backend"),
            tcp=str(BACKEND_PORT),
        )
        add_pod(
            f"{short}-ws",
            release,
            f"{release}-ws-hub",
            pod_template_labels(app, "Deployment", f"{release}-ws-hub"),
            tcp=f"{WS_PUBLIC_PORT},{WS_METRICS_PORT}",
        )
        objects.append(
            service(
                release,
                f"{short}-backend-svc",
                {"probe-role": f"{short}-backend"},
                BACKEND_PORT,
            )
        )
    # Other chart workloads in probe-a: each is selected by the release default-deny,
    # so its public egress is governed by the rendered policy and not by the namespace.
    app_a, _store_a = rendered["probe-a"]
    for component in ("gateway", "frontend", "outbox-worker"):
        add_pod(
            f"a-{component.split('-')[0]}",
            "probe-a",
            f"probe-a-{component}-stand-in",
            pod_template_labels(app_a, "Deployment", f"probe-a-{component}"),
        )
    add_pod("unrelated", UNRELATED_NS, "untrusted-source", {"app": "untrusted"})
    add_pod(
        "decoy",
        UNRELATED_NS,
        "decoy-listener",
        {"app": "decoy"},
        tcp="443,53",
        udp="53",
    )
    objects.append(service(UNRELATED_NS, "decoy-443-svc", {"probe-role": "decoy"}, 443))
    add_pod(
        "prometheus",
        MONITORING_NS,
        "prometheus-0",
        {"app.kubernetes.io/name": "prometheus"},
    )
    add_pod("monitoring-other", MONITORING_NS, "other-0", {"app": "other"})
    add_pod(
        "ingress",
        INGRESS_NS,
        "ingress-controller",
        {"app.kubernetes.io/name": "ingress-nginx"},
    )
    return objects, specs


def wait_ready(namespace: str) -> None:
    kubectl(
        "-n",
        namespace,
        "wait",
        "--for=condition=Ready",
        "pod",
        "--all",
        "--timeout=300s",
    )


def resolve_pod(pod: Pod) -> None:
    info = kubectl_json("-n", pod.namespace, "get", "pod", pod.name, "-o", "json")
    pod.ip = info["status"]["podIP"]
    pod.uid = info["metadata"]["uid"]


def cluster_ip(namespace: str, name: str) -> str:
    address: str = kubectl_json("-n", namespace, "get", "service", name, "-o", "json")[
        "spec"
    ]["clusterIP"]
    return address


def build_targets(pods: dict[str, Pod], kube_dns_ip: str) -> dict[str, tuple[str, int]]:
    redis_service = {
        release: cluster_ip(release, f"{release}-revocation-redis-master")
        for release in RELEASES
    }
    return {
        "a-backend-pod": (pods["a-backend"].ip, BACKEND_PORT),
        "b-backend-pod": (pods["b-backend"].ip, BACKEND_PORT),
        "a-backend-svc": (cluster_ip("probe-a", "a-backend-svc"), BACKEND_PORT),
        "a-redis-pod": (pods["a-redis"].ip, REDIS_PORT),
        "b-redis-pod": (pods["b-redis"].ip, REDIS_PORT),
        "a-redis-svc": (redis_service["probe-a"], REDIS_PORT),
        "a-ws-public": (pods["a-ws"].ip, WS_PUBLIC_PORT),
        "a-ws-metrics": (pods["a-ws"].ip, WS_METRICS_PORT),
        "decoy-pod-443": (pods["decoy"].ip, 443),
        "decoy-pod-53": (pods["decoy"].ip, 53),
        "decoy-svc-443": (cluster_ip(UNRELATED_NS, "decoy-443-svc"), 443),
        "kube-dns-udp": (kube_dns_ip, 53),
        "kube-dns-tcp": (kube_dns_ip, 53),
        "public-https": (PUBLIC_HTTPS_TARGET, 443),
    }


def set_up_cluster(
    base_image: str, rendered: Rendered, passwords: dict[str, str]
) -> dict[str, Pod]:
    apply_objects(namespace_objects())
    for release in RELEASES:
        apply_objects([credential_secret(release, passwords[release])])
        apply_store_workloads(release, rendered[release][1])
    objects, pods = standin_objects(rendered, base_image)
    apply_objects(objects)
    for namespace in [*RELEASES, UNRELATED_NS, MONITORING_NS, INGRESS_NS]:
        wait_ready(namespace)
    for release in RELEASES:
        pods[release.split("-")[-1] + "-redis"] = Pod(
            release, f"{release}-revocation-redis-master-0"
        )
    for pod in pods.values():
        resolve_pod(pod)
    return pods


def apply_policies(rendered: Rendered) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for release in RELEASES:
        app, store = rendered[release]
        for policy in [r for r in app + store if r.get("kind") == "NetworkPolicy"]:
            policy["metadata"]["namespace"] = release
            applied.append(policy)
    apply_objects(applied)
    time.sleep(10)  # Calico programs policy asynchronously; this fixed wait is bounded.
    return applied


def policy_summary(applied: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "namespace": policy["metadata"]["namespace"],
            "name": policy["metadata"]["name"],
            "spec_sha256": hashlib.sha256(
                json.dumps(policy["spec"], sort_keys=True).encode()
            ).hexdigest(),
        }
        for policy in applied
    ]


def resolver_status(
    pods: dict[str, Pod], kube_dns_ip: str, kubernetes_ip: str, execute: Execute
) -> dict[str, Any]:
    dns_observed = execute("a-fp", "kube-dns-udp", "dns-udp", "")
    resolver = probe_connection(pods["a-fp"], "tcp", kube_dns_ip, 53)
    resolv = kubectl(
        "-n", "probe-a", "exec", pods["a-fp"].name, "--", "cat", "/etc/resolv.conf"
    ).stdout
    nameservers = [
        line.split()[1] for line in resolv.splitlines() if line.startswith("nameserver")
    ]
    ok = (
        nameservers == [kube_dns_ip]
        and resolver.get("result") == "connected"
        and dns_observed.get("result") == "dns-answer"
        and kubernetes_ip in dns_observed.get("answers", [])
    )
    return {
        "nameservers": nameservers,
        "expected": kube_dns_ip,
        "verdict": "pass" if ok else "fail",
    }


def not_run_items() -> list[dict[str, str]]:
    return [
        {
            "finding": "AUD-188",
            "check": "file-processor process JWKS refresher and gRPC ProcessFile acceptance",
            "reason": (
                "the file-processor cannot reach its serving state in kind: "
                "cmd/file-processor/main.go requires Temporal and NATS at startup. "
                "The stand-in consumer verifies the same RS256 and JWKS contract, "
                "without the refresher"
            ),
        },
        {
            "finding": "AUD-169",
            "check": "revoked and unrevoked token pair through the file-processor",
            "reason": "requires the file-processor process (see AUD-188)",
        },
        {
            "finding": "AUD-189",
            "check": "link-local TCP/443 destination",
            "reason": "no owned link-local listener in kind",
        },
        {
            "finding": "AUD-189",
            "check": "backup public TCP/443 allowance",
            "reason": "backup.enabled is false in the staging values; the backup policy is not rendered here",
        },
    ]


def run_app_checks(
    pods: dict[str, Pod],
    passwords: dict[str, str],
    redis_ips: dict[str, str],
) -> dict[str, Any]:
    def live_control() -> dict[str, Any]:
        return redis_ping(pods["a-fp"], redis_ips["probe-a"], passwords["probe-a"])

    aud169 = redis_checks(
        pods["a-fp"],
        pods["unrelated"],
        redis_ips["probe-a"],
        passwords["probe-a"],
        live_control,
    )
    aud188 = jwks_rotation_checks(
        pods["a-fp"],
        pods["a-backend"],
        f"http://{pods['a-backend'].ip}:{BACKEND_PORT}/.well-known/jwks.json",
    )
    return {
        "AUD-169": {
            "checks": aud169,
            "verdict": "pass" if all_passed(aud169) else "fail",
        },
        "AUD-188": {
            "checks": aud188,
            "verdict": "pass" if all_passed(aud188) else "fail",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--kubernetes-version", required=True)
    parser.add_argument("--node-image", required=True)
    parser.add_argument("--calico-sha256", required=True)
    args = parser.parse_args()

    started = datetime.now(UTC).isoformat()
    base_image = runtime_base_image()
    rendered = render_all()
    passwords = {release: new_redis_password() for release in RELEASES}
    pods = set_up_cluster(base_image, rendered, passwords)

    kube_dns_ip = cluster_ip("kube-system", "kube-dns")
    kubernetes_ip = cluster_ip("default", "kubernetes")
    targets = build_targets(pods, kube_dns_ip)
    execute = make_executor(pods, targets)
    rows_baseline = measure_baseline(ROWS, execute, kubernetes_ip)
    redis_ip = {"probe-a": pods["a-redis"].ip, "probe-b": pods["b-redis"].ip}
    app_baseline = redis_ping(pods["a-fp"], redis_ip["probe-a"], passwords["probe-a"])

    applied = apply_policies(rendered)
    results = evaluate_rows(ROWS, rows_baseline, execute, kubernetes_ip)
    resolver = resolver_status(pods, kube_dns_ip, kubernetes_ip, execute)
    app_level = run_app_checks(pods, passwords, redis_ip)

    rows_pass = all(entry["verdict"] == "pass" for entry in results)
    app_pass = all(section["verdict"] == "pass" for section in app_level.values())
    baseline_pass = app_baseline.get("result") == "redis-pong"
    all_pass = (
        rows_pass and app_pass and baseline_pass and resolver["verdict"] == "pass"
    )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "started_utc": started,
        "finished_utc": datetime.now(UTC).isoformat(),
        "cluster": {
            "kubernetes": args.kubernetes_version,
            "node_image": args.node_image,
            "cni": "calico",
            "calico_manifest_sha256": args.calico_sha256,
            "ip_family": "ipv4",
            "stand_in_image": base_image,
            "workloads": (
                "revocation Redis from the store chart (metrics init on the Python base image); "
                "file-processor, backend and ws-hub are stand-in pods with rendered labels"
            ),
        },
        "redis": {
            "credential_secret": f"{REDIS_AUTH_OBJECT_NAME}/{REDIS_CREDENTIAL_ITEM_REF}",
            "credential_value": "generated per run and not recorded",
            "baseline_authenticated_ping": app_baseline.get("result"),
        },
        "resolver": resolver,
        "kubernetes_service_answer": kubernetes_ip,
        "pods": {
            key: {"namespace": p.namespace, "name": p.name, "ip": p.ip, "uid": p.uid}
            for key, p in pods.items()
        },
        "policies": policy_summary(applied),
        "probes": results,
        "app_level": app_level,
        "not_run": not_run_items(),
        "verdict": "pass" if all_pass else "fail",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    failed = [r["probe_id"] for r in results if r["verdict"] != "pass"]
    print(
        f"probes={len(results)} failed_or_inconclusive={len(failed)} verdict={receipt['verdict']}"
    )
    for probe_id in failed:
        print(f"  not pass: {probe_id}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
