"""Probe matrix and verdict rules for the AUD-169/188/189/438 NetworkPolicy proof.

A row is one connection attempt from a stand-in source to a named target. An
expected denial passes only when the same-destination control succeeds before and
after the denied attempt; otherwise it is inconclusive, never a pass.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from networkpolicy_runtime_kube import Pod, probe_connection

BACKEND_PORT = 8000
WS_PUBLIC_PORT = 8081
WS_METRICS_PORT = 9108
REDIS_PORT = 6379
TEMPORAL_PORT = 7233
NATS_PORT = 4222
PUBLIC_HTTPS_TARGET = "1.1.1.1"
# Link-local listener address. scripts/k8s/networkpolicy_runtime_proof.sh adds this
# /32 to the kind node's eth0 (LINK_LOCAL_ADDRESS) before any policy is applied.
LINK_LOCAL_ADDRESS = "169.254.10.10"
LINK_LOCAL_PORT = 443
METRICS_PATH = "/metrics"
DNS_NAME = "kubernetes.default.svc.cluster.local"
JWKS_PATH = "/.well-known/jwks.json"


@dataclass(frozen=True)
class Row:
    finding: str
    probe_id: str
    source: str
    target: str  # key into the target map
    mode: str
    port: int
    expect_allow: bool
    description: str
    control: tuple[str, str, str, int] | None = None  # source, target, mode, port
    path: str = ""


Execute = Callable[[str, str, str, str], dict[str, Any]]

ROWS: tuple[Row, ...] = (
    Row(
        "AUD-169",
        "aud169-a-pod",
        "a-fp",
        "a-redis-pod",
        "tcp",
        REDIS_PORT,
        True,
        "file-processor (A) to its own revocation Redis, Pod IP",
    ),
    Row(
        "AUD-169",
        "aud169-a-svc",
        "a-fp",
        "a-redis-svc",
        "tcp",
        REDIS_PORT,
        True,
        "file-processor (A) to its own revocation Redis, Service",
    ),
    Row(
        "AUD-169",
        "aud169-b-own",
        "b-fp",
        "b-redis-pod",
        "tcp",
        REDIS_PORT,
        True,
        "file-processor (B) to its own revocation Redis",
    ),
    Row(
        "AUD-169",
        "aud169-cross-release",
        "a-fp",
        "b-redis-pod",
        "tcp",
        REDIS_PORT,
        False,
        "file-processor (A) to release B revocation Redis",
        control=("b-fp", "b-redis-pod", "tcp", REDIS_PORT),
    ),
    Row(
        "AUD-169",
        "aud169-unrelated",
        "unrelated",
        "a-redis-pod",
        "tcp",
        REDIS_PORT,
        False,
        "unrelated namespace source to release A revocation Redis",
        control=("a-fp", "a-redis-pod", "tcp", REDIS_PORT),
    ),
    Row(
        "AUD-188",
        "aud188-jwks-pod",
        "a-fp",
        "a-backend-pod",
        "http",
        BACKEND_PORT,
        True,
        "file-processor (A) JWKS fetch, Pod IP",
        path=JWKS_PATH,
    ),
    Row(
        "AUD-188",
        "aud188-jwks-svc",
        "a-fp",
        "a-backend-svc",
        "http",
        BACKEND_PORT,
        True,
        "file-processor (A) JWKS fetch, Service",
        path=JWKS_PATH,
    ),
    Row(
        "AUD-188",
        "aud188-jwks-b-own",
        "b-fp",
        "b-backend-pod",
        "http",
        BACKEND_PORT,
        True,
        "file-processor (B) JWKS fetch, own backend",
        path=JWKS_PATH,
    ),
    Row(
        "AUD-188",
        "aud188-jwks-cross",
        "a-fp",
        "b-backend-pod",
        "http",
        BACKEND_PORT,
        False,
        "file-processor (A) JWKS fetch from release B backend",
        path=JWKS_PATH,
        control=("b-fp", "b-backend-pod", "http", BACKEND_PORT),
    ),
    Row(
        "AUD-188",
        "aud188-jwks-unrelated",
        "unrelated",
        "a-backend-pod",
        "http",
        BACKEND_PORT,
        False,
        "unrelated source to release A backend JWKS",
        path=JWKS_PATH,
        control=("a-fp", "a-backend-pod", "http", BACKEND_PORT),
    ),
    Row(
        "AUD-188",
        "aud188-temporal-allow",
        "a-fp",
        "a-temporal-pod",
        "tcp",
        TEMPORAL_PORT,
        True,
        "file-processor (A) to its release Temporal dependency (app.kubernetes.io/name=temporal), Pod IP",
    ),
    Row(
        "AUD-188",
        "aud188-nats-allow",
        "a-fp",
        "a-nats-pod",
        "tcp",
        NATS_PORT,
        True,
        "file-processor (A) to its release NATS dependency (app.kubernetes.io/name=nats), Pod IP",
    ),
    Row(
        "AUD-188",
        "aud188-temporal-decoy",
        "a-fp",
        "decoy-temporal-pod",
        "tcp",
        TEMPORAL_PORT,
        False,
        "file-processor (A) to a Temporal-labelled pod in an unselected namespace",
        control=("unrelated", "decoy-temporal-pod", "tcp", TEMPORAL_PORT),
    ),
    Row(
        "AUD-188",
        "aud188-nats-decoy",
        "a-fp",
        "decoy-nats-pod",
        "tcp",
        NATS_PORT,
        False,
        "file-processor (A) to a NATS-labelled pod in an unselected namespace",
        control=("unrelated", "decoy-nats-pod", "tcp", NATS_PORT),
    ),
    Row(
        "AUD-189",
        "aud189-dns-udp",
        "a-fp",
        "kube-dns-udp",
        "dns-udp",
        53,
        True,
        "file-processor DNS over UDP to the configured resolver",
    ),
    Row(
        "AUD-189",
        "aud189-dns-tcp",
        "a-fp",
        "kube-dns-tcp",
        "dns-tcp",
        53,
        True,
        "file-processor DNS over TCP to the configured resolver",
    ),
    Row(
        "AUD-189",
        "aud189-dns-decoy-tcp",
        "a-fp",
        "decoy-pod-53",
        "tcp",
        53,
        False,
        "file-processor TCP/53 to a non-resolver listener",
        control=("unrelated", "decoy-pod-53", "tcp", 53),
    ),
    Row(
        "AUD-189",
        "aud189-dns-decoy-udp",
        "a-fp",
        "decoy-pod-53",
        "udp-reply",
        53,
        False,
        "file-processor UDP/53 to a non-resolver listener",
        control=("unrelated", "decoy-pod-53", "udp-reply", 53),
    ),
    Row(
        "AUD-189",
        "aud189-443-pod",
        "a-fp",
        "decoy-pod-443",
        "tcp",
        443,
        False,
        "file-processor TCP/443 to an in-cluster Pod IP",
        control=("unrelated", "decoy-pod-443", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-443-svc",
        "a-fp",
        "decoy-svc-443",
        "tcp",
        443,
        False,
        "file-processor TCP/443 to an in-cluster ClusterIP",
        control=("unrelated", "decoy-svc-443", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-443-public",
        "a-fp",
        "public-https",
        "tcp",
        443,
        False,
        "file-processor TCP/443 to a public address (no exception for this workload)",
        control=("a-backend", "public-https", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-public-backend",
        "a-backend",
        "public-https",
        "tcp",
        443,
        True,
        "backend TCP/443 to a public address (owner-accepted exception, ADR-054 addendum)",
    ),
    Row(
        "AUD-189",
        "aud189-public-ws",
        "a-ws",
        "public-https",
        "tcp",
        443,
        False,
        "ws-hub TCP/443 to a public address",
        control=("a-backend", "public-https", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-public-gateway",
        "a-gateway",
        "public-https",
        "tcp",
        443,
        False,
        "gateway TCP/443 to a public address (JWKS egress needs owner CIDRs)",
        control=("a-backend", "public-https", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-public-frontend",
        "a-frontend",
        "public-https",
        "tcp",
        443,
        False,
        "frontend TCP/443 to a public address",
        control=("a-backend", "public-https", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-public-outbox",
        "a-outbox",
        "public-https",
        "tcp",
        443,
        False,
        "outbox-worker TCP/443 to a public address (no public destination granted)",
        control=("a-backend", "public-https", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-backup-public",
        "a-backup",
        "public-https",
        "tcp",
        443,
        True,
        "backup job TCP/443 to a public address (backup.enabled=true, the only backup public allowance)",
    ),
    Row(
        "AUD-189",
        "aud189-backup-decoy-443",
        "a-backup",
        "decoy-pod-443",
        "tcp",
        443,
        False,
        "backup job TCP/443 to an in-cluster Pod IP (cluster ranges are excepted)",
        control=("unrelated", "decoy-pod-443", "tcp", 443),
    ),
    Row(
        "AUD-189",
        "aud189-backup-decoy-80",
        "a-backup",
        "decoy-pod-80",
        "tcp",
        80,
        False,
        "backup job TCP/80 to an in-cluster listener (no port other than 443 is granted)",
        control=("unrelated", "decoy-pod-80", "tcp", 80),
    ),
    Row(
        "AUD-189",
        "aud189-backup-backend-8000",
        "a-backup",
        "a-backend-pod",
        "tcp",
        BACKEND_PORT,
        False,
        "backup job TCP/8000 to the release backend (no ingress grant to the backup workload)",
        control=("a-fp", "a-backend-pod", "tcp", BACKEND_PORT),
    ),
    Row(
        "AUD-189",
        "aud189-linklocal-fp",
        "a-fp",
        "link-local-443",
        "tcp",
        LINK_LOCAL_PORT,
        False,
        "file-processor TCP/443 to a link-local listener (169.254.0.0/16)",
        control=("linklocal", "link-local-443", "tcp", LINK_LOCAL_PORT),
    ),
    Row(
        "AUD-189",
        "aud189-linklocal-backend",
        "a-backend",
        "link-local-443",
        "tcp",
        LINK_LOCAL_PORT,
        False,
        "backend TCP/443 to a link-local listener: excepted from the public exception",
        control=("linklocal", "link-local-443", "tcp", LINK_LOCAL_PORT),
    ),
    Row(
        "AUD-189",
        "aud189-linklocal-backup",
        "a-backup",
        "link-local-443",
        "tcp",
        LINK_LOCAL_PORT,
        False,
        "backup job TCP/443 to a link-local listener: excepted from the public exception",
        control=("linklocal", "link-local-443", "tcp", LINK_LOCAL_PORT),
    ),
    Row(
        "AUD-438",
        "aud438-metrics-prometheus",
        "prometheus",
        "a-ws-metrics",
        "http",
        WS_METRICS_PORT,
        True,
        "Prometheus pod: HTTP GET /metrics to the ws-hub metrics listener",
        path=METRICS_PATH,
    ),
    Row(
        "AUD-438",
        "aud438-metrics-other",
        "monitoring-other",
        "a-ws-metrics",
        "http",
        WS_METRICS_PORT,
        False,
        "non-Prometheus pod in monitoring: HTTP GET /metrics to the ws-hub metrics listener",
        control=("prometheus", "a-ws-metrics", "http", WS_METRICS_PORT),
        path=METRICS_PATH,
    ),
    Row(
        "AUD-438",
        "aud438-metrics-unrelated",
        "unrelated",
        "a-ws-metrics",
        "http",
        WS_METRICS_PORT,
        False,
        "unselected namespace: HTTP GET /metrics to the ws-hub metrics listener",
        control=("prometheus", "a-ws-metrics", "http", WS_METRICS_PORT),
        path=METRICS_PATH,
    ),
    Row(
        "AUD-438",
        "aud438-metrics-ingress",
        "ingress",
        "a-ws-metrics",
        "http",
        WS_METRICS_PORT,
        False,
        "ingress controller: HTTP GET /metrics to the ws-hub metrics listener",
        control=("prometheus", "a-ws-metrics", "http", WS_METRICS_PORT),
        path=METRICS_PATH,
    ),
    Row(
        "AUD-438",
        "aud438-public-prometheus",
        "prometheus",
        "a-ws-public",
        "tcp",
        WS_PUBLIC_PORT,
        False,
        "Prometheus pod to the public ws-hub WebSocket port",
        control=("ingress", "a-ws-public", "tcp", WS_PUBLIC_PORT),
    ),
    Row(
        "AUD-438",
        "aud438-public-unrelated",
        "unrelated",
        "a-ws-public",
        "tcp",
        WS_PUBLIC_PORT,
        False,
        "unrelated source to the public ws-hub WebSocket port",
        control=("ingress", "a-ws-public", "tcp", WS_PUBLIC_PORT),
    ),
    Row(
        "AUD-438",
        "aud438-public-ingress",
        "ingress",
        "a-ws-public",
        "tcp",
        WS_PUBLIC_PORT,
        True,
        "ingress controller to the public ws-hub WebSocket port",
    ),
)


def make_executor(pods: dict[str, Pod], targets: dict[str, tuple[str, int]]) -> Execute:
    def execute(
        source_key: str, target_key: str, mode: str, path: str = ""
    ) -> dict[str, Any]:
        host, port = targets[target_key]
        if mode == "http":
            extra: tuple[str, ...] = (path,)
        elif mode in ("dns-udp", "dns-tcp"):
            extra = (DNS_NAME,)
        else:
            extra = ()
        return probe_connection(pods[source_key], mode, host, port, extra)

    return execute


def is_success(mode: str, observed: dict[str, Any], expected_answer: str = "") -> bool:
    result = observed.get("result")
    if mode == "tcp":
        return result == "connected"
    if mode == "http":
        return result == "http" and observed.get("status") == "200"
    if mode in ("dns-udp", "dns-tcp"):
        return result == "dns-answer" and expected_answer in observed.get("answers", [])
    if mode == "udp-reply":
        return result == "udp-reply"
    return False


def _row_success(row: Row, observed: dict[str, Any], dns_answer: str) -> bool:
    return is_success(
        row.mode, observed, dns_answer if row.mode.startswith("dns") else ""
    )


def measure_baseline(
    rows: tuple[Row, ...], execute: Execute, dns_answer: str
) -> dict[str, dict[str, Any]]:
    """Prove every target and control is reachable before any policy is applied."""
    baseline: dict[str, dict[str, Any]] = {}
    for row in rows:
        target_observed = execute(row.source, row.target, row.mode, row.path)
        entry: dict[str, Any] = {
            "target": target_observed,
            "target_ok": _row_success(row, target_observed, dns_answer),
        }
        if row.control:
            c_src, c_dst, c_mode, _c_port = row.control
            control_observed = execute(
                c_src, c_dst, c_mode, row.path if c_mode == "http" else ""
            )
            entry["control"] = control_observed
            entry["control_ok"] = is_success(c_mode, control_observed)
        baseline[row.probe_id] = entry
    return baseline


def evaluate_row(
    row: Row,
    baseline: dict[str, Any],
    execute: Execute,
    dns_answer: str,
) -> dict[str, Any]:
    """Return one receipt entry with a pass, fail or inconclusive verdict."""
    entry: dict[str, Any] = {
        "finding": row.finding,
        "probe_id": row.probe_id,
        "description": row.description,
        "source": row.source,
        "destination": row.target,
        "protocol": "UDP" if row.mode in ("udp-reply", "dns-udp") else "TCP",
        "port": row.port,
        "expected": "allow" if row.expect_allow else "deny",
        "baseline": baseline,
    }
    if not baseline["target_ok"] or not baseline.get("control_ok", True):
        entry["verdict"] = "inconclusive"
        entry["reason"] = "baseline reachability failed before policy"
        return entry
    if row.expect_allow:
        observed = execute(row.source, row.target, row.mode, row.path)
        entry["observed"] = observed
        entry["verdict"] = "pass" if _row_success(row, observed, dns_answer) else "fail"
        return entry
    if row.control is None:
        raise SystemExit(f"denial row {row.probe_id} has no control")
    c_src, c_dst, c_mode, _c_port = row.control
    c_path = row.path if c_mode == "http" else ""
    control_before = execute(c_src, c_dst, c_mode, c_path)
    observed = execute(row.source, row.target, row.mode, row.path)
    control_after = execute(c_src, c_dst, c_mode, c_path)
    entry["observed"] = observed
    entry["control"] = {
        "before": control_before,
        "after": control_after,
        "source": c_src,
        "destination": c_dst,
    }
    controls_ok = is_success(c_mode, control_before) and is_success(
        c_mode, control_after
    )
    if _row_success(row, observed, dns_answer):
        entry["verdict"] = "fail"
        entry["reason"] = "destination reachable through policy"
    elif observed.get("result") == "timeout" and controls_ok:
        entry["verdict"] = "pass"
    else:
        entry["verdict"] = "inconclusive"
        entry["reason"] = "denial not attributable with a live same-destination control"
    return entry


def evaluate_rows(
    rows: tuple[Row, ...],
    baseline: dict[str, dict[str, Any]],
    execute: Execute,
    dns_answer: str,
) -> list[dict[str, Any]]:
    return [
        evaluate_row(row, baseline[row.probe_id], execute, dns_answer) for row in rows
    ]
