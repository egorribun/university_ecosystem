"""Source-bound ws-hub positive scrape in the existing disposable kind proof.

The matrix remains a stand-in policy proof. This separate phase checks actual
chart-selected ws-hub replicas from the labelled Python probe and a separately
provisioned Prometheus instance; it does not test denied peers.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml
from networkpolicy_runtime_kube import (
    CreatedPod,
    Pod,
    apply_objects,
    find,
    kubectl,
    kubectl_json,
    run_command,
    run_in_pod,
)
from networkpolicy_runtime_standins import stand_in_pod
from networkpolicy_runtime_temporal import _mount, _object, compose_image, secret_volume

# Runs in the authenticated, disposable NATS fixture's Python sidecar. It only
# creates empty streams required by the real hub; it publishes no work or events.
NATS_STREAMS = r"""
import json, socket
from pathlib import Path
token = Path('/auth/token').read_text()
streams = [('CHAT_EVENTS', ['chat.*']), ('NOTIFICATIONS_EVENTS', ['notifications.*']),
           ('CACHE_INVALIDATIONS', ['cache.invalidate', 'cache.revoke'])]
with socket.create_connection(('127.0.0.1', 4222), timeout=5) as s:
    s.settimeout(5)
    f = s.makefile('rb')
    if not f.readline(16385).startswith(b'INFO '): raise SystemExit(1)
    connect = json.dumps({'auth_token': token, 'verbose': False}).encode()
    s.sendall(b'CONNECT ' + connect + b'\r\nSUB _INBOX.netpolws 1\r\n')
    for name, subjects in streams:
        config = json.dumps({'name': name, 'subjects': subjects, 'storage': 'memory'}).encode()
        s.sendall(b'PUB $JS.API.STREAM.CREATE.' + name.encode() + b' _INBOX.netpolws ' +
                  str(len(config)).encode() + b'\r\n' + config + b'\r\nPING\r\n')
        for _ in range(32):
            line = f.readline(16385)
            if line == b'PING\r\n': s.sendall(b'PONG\r\n'); continue
            if line.startswith(b'-ERR') or not line: raise SystemExit(1)
            if line.startswith(b'MSG '):
                size = int(line.split()[-1])
                if not 0 < size < 65536: raise SystemExit(1)
                data = f.read(size)
                if len(data) != size or f.read(2) != b'\r\n': raise SystemExit(1)
                response = json.loads(data)
                if response.get('error') or response.get('config', {}).get('subjects') != subjects:
                    raise SystemExit(1)
                break
        else: raise SystemExit(1)
print('{"result":"ready"}')
"""

# No response body, HTTP error, address or exception message is returned.
SCRAPE = r"""
import http.client, json, re, sys
connection = http.client.HTTPConnection(sys.argv[1], 9108, timeout=3)
connection.request('GET', '/metrics', headers={'Accept': 'text/plain; version=0.0.4'})
response = connection.getresponse()
body = response.read(2000001)
content_type = response.getheader('Content-Type', '').split(';', 1)[0].strip().lower()
connection.close()
text = body.decode('utf-8', errors='replace')
valid = (response.status == 200 and content_type == 'text/plain' and len(body) <= 2000000
         and '# TYPE ws_hub_active_goroutines gauge' in text.splitlines()
         and re.search(r'^ws_hub_active_goroutines [0-9]+(?:\.[0-9]+)?$', text, re.MULTILINE))
print(json.dumps({'result': 'valid-exposition' if valid else 'invalid-exposition'}))
"""

# Runs from the permitted probe to the ClusterIP or, on exhaustion, one bound replica.
HEALTH = r"""
import errno, http.client, json, sys, time
single = len(sys.argv) > 2 and sys.argv[2] == 'single'
deadline = time.monotonic() + (3 if single else 10)
result = 'window-expired'
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0: break
    connection = http.client.HTTPConnection(sys.argv[1], 8081, timeout=min(3, remaining))
    try:
        connection.request('GET', '/health/live')
        response = connection.getresponse()
        if response.status != 200:
            result = 'invalid'
        else:
            body = response.read(1025)
            valid = len(body) <= 1024 and json.loads(body) == {'status': 'alive'}
            result = 'healthy' if valid else 'invalid'
            if valid and time.monotonic() > deadline: result = 'window-expired'
    except OSError as exc:
        if isinstance(exc, (TimeoutError, ConnectionError)) or exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            result = 'transport-unavailable'
        else:
            result = 'exec-error'
    except (ValueError, http.client.HTTPException):
        result = 'invalid'
    finally:
        connection.close()
    if result != 'transport-unavailable' or single: break
    remaining = deadline - time.monotonic()
    if remaining <= 0: break
    time.sleep(min(0.5, remaining))
print(json.dumps({'result': result}))
"""

# Verify the processor phase's final JWKS in place without returning it.
VERIFY_JWKS = r"""
import json
from pathlib import Path
document = json.loads(Path('/tmp/jwks.json').read_text())
keys = document.get('keys') if isinstance(document, dict) else None
valid = isinstance(keys, list) and any(
    isinstance(key, dict) and key.get('kty') == 'RSA' and key.get('kid')
    and key.get('n') and key.get('e') for key in keys)
print(json.dumps({'result': 'valid' if valid else 'invalid'}))
"""


def ws_deployment(
    resources: list[dict[str, Any]], image: str, source_sha: str
) -> dict[str, Any]:
    """Copy the rendered staging deployment, changing only image provenance."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not re.fullmatch(
        rf"ue-netpol-ws:{source_sha}-[0-9a-f]{{12}}", image
    ):
        raise ValueError("ws-hub image must carry the full source SHA")
    deployment = copy.deepcopy(find(resources, "Deployment", "probe-a-ws-hub"))
    template = deployment["spec"]["template"]
    container = next(c for c in template["spec"]["containers"] if c["name"] == "ws-hub")
    env = {item["name"]: item.get("value") for item in container["env"]}
    if any(
        env.get(name) != value
        for name, value in {
            "VITE_ENVIRONMENT": "staging",
            "WS_HUB_METRICS_ADDR": ":9108",
            "ENABLE_JETSTREAM": "true",
        }.items()
    ):
        raise ValueError("rendered staging or metrics settings changed")
    for name in (
        "JWT_SECRET_FILE",
        "WS_HUB_INTERNAL_SECRET_FILE",
        "INTERNAL_AUTH_TOKEN_FILE",
        "NATS_URL_FILE",
        "NATS_AUTH_TOKEN_FILE",
        "REDIS_URL_FILE",
        "REVOCATION_REDIS_URL_FILE",
    ):
        if not env.get(name):
            raise ValueError("rendered credential reference missing")
    if env.get("SPIFFE_ENABLED") == "true":
        raise ValueError("SPIFFE workload fixture required")
    container["image"] = image
    container["imagePullPolicy"] = "Never"
    template["metadata"].setdefault("annotations", {})[
        "university-ecosystem.io/source-sha"
    ] = source_sha
    return deployment


def ws_secrets(
    deployment: dict[str, Any], values: dict[str, str]
) -> list[dict[str, Any]]:
    """Populate only rendered file references. Return private Kubernetes Secrets."""
    spec = deployment["spec"]["template"]["spec"]
    container = next(c for c in spec["containers"] if c["name"] == "ws-hub")
    mounts = {item["name"]: item["mountPath"] for item in container["volumeMounts"]}
    env = {item["name"]: item.get("value") for item in container["env"]}
    documents: dict[str, dict[str, str]] = {}
    used: set[str] = set()
    for volume in spec["volumes"]:
        secret = volume.get("secret")
        if not secret:
            continue
        data = documents.setdefault(secret["secretName"], {})
        for item in secret["items"]:
            path = mounts[volume["name"]] + "/" + item["path"]
            names = [name for name, ref in env.items() if ref == path]
            if not names or any(
                name not in values or not values[name] for name in names
            ):
                raise ValueError("unmapped or empty rendered credential")
            contents = {values[name] for name in names}
            if len(contents) != 1:
                raise ValueError("conflicting shared credential references")
            data[item["key"]] = contents.pop()
            used.update(names)
    if used != set(values):
        raise ValueError("credential values do not match rendered references")
    return [
        _object("Secret", name, "probe-a", stringData=data)
        for name, data in documents.items()
    ]


def nats_fixture(root: Path, python_image: str, token: str) -> list[dict[str, Any]]:
    """Authenticated NATS fixture selected by the existing release policy."""
    config = json.dumps(
        {
            "port": 4222,
            "jetstream": {"store_dir": "/data"},
            "authorization": {"token": token},
        }
    )
    secret = _object(
        "Secret",
        "netpol-ws-nats-auth",
        "probe-a",
        stringData={"token": token, "nats.conf": config},
    )
    service = _object(
        "Service",
        "netpol-ws-nats",
        "probe-a",
        spec={"selector": {"netpol-fixture": "ws-nats"}, "ports": [{"port": 4222}]},
    )
    pod = _object(
        "Pod",
        "netpol-ws-nats",
        "probe-a",
        spec={
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "name": "nats",
                    "image": compose_image(root, "nats"),
                    "command": ["nats-server", "-c", "/auth/nats.conf"],
                    "volumeMounts": [
                        _mount("auth", "/auth"),
                        {"name": "data", "mountPath": "/data"},
                    ],
                    "readinessProbe": {"tcpSocket": {"port": 4222}, "periodSeconds": 2},
                },
                {
                    "name": "probe",
                    "image": python_image,
                    "command": ["sleep", "infinity"],
                    "volumeMounts": [_mount("auth", "/auth")],
                },
            ],
            "volumes": [
                secret_volume("auth", "netpol-ws-nats-auth"),
                {"name": "data", "emptyDir": {}},
            ],
        },
    )
    pod["metadata"]["labels"] = {
        "app.kubernetes.io/name": "nats",
        "app.kubernetes.io/instance": "probe-a",
        "netpol-fixture": "ws-nats",
    }
    return [secret, service, pod]


def cache_fixture(
    app: list[dict[str, Any]], store: list[dict[str, Any]], password: str
) -> list[dict[str, Any]]:
    """Use the rendered cache Redis and its policy, distinct from revocation Redis."""
    from networkpolicy_runtime_probe import strip_metrics_exporter

    cache = copy.deepcopy(find(app, "StatefulSet", "probe-a-redis-master"))
    redis = find(store, "StatefulSet", "probe-a-revocation-redis-master")
    image = next(
        c["image"]
        for c in redis["spec"]["template"]["spec"]["containers"]
        if c["name"] == "redis"
    )
    if not re.search(r"@sha256:[0-9a-f]{64}$", image):
        raise ValueError("Redis fixture image is not pinned")
    strip_metrics_exporter([cache])
    spec = cache["spec"]["template"]["spec"]
    for container in [*spec["containers"], *spec["initContainers"]]:
        container["image"] = image
    credential = next(
        v["secret"] for v in spec["volumes"] if v["name"] == "redis-password"
    )
    key = next(
        item["key"] for item in credential["items"] if item["path"] == "password"
    )
    resources = [
        find(app, kind, name)
        for kind, name in (
            ("ServiceAccount", "probe-a-redis-master"),
            ("ConfigMap", "probe-a-redis-configuration"),
            ("Service", "probe-a-redis-headless"),
            ("Service", "probe-a-redis-master"),
        )
    ]
    return [
        *copy.deepcopy(resources),
        _object(
            "Secret", credential["secretName"], "probe-a", stringData={key: password}
        ),
        cache,
    ]


def replicas(
    deployment: dict[str, Any], image: str, source_sha: str
) -> list[dict[str, Any]]:
    """Inventory only pods owned by the live Deployment's ReplicaSets."""
    selector = ",".join(
        f"{k}={v}"
        for k, v in sorted(deployment["spec"]["selector"]["matchLabels"].items())
    )
    current = kubectl_json(
        "-n", "probe-a", "get", "deployment", "probe-a-ws-hub", "-o", "json"
    )
    deployment_uid = current["metadata"]["uid"]
    sets = kubectl_json(
        "-n", "probe-a", "get", "replicasets", "-l", selector, "-o", "json"
    )["items"]
    owned = {
        item["metadata"]["uid"]
        for item in sets
        if any(
            owner.get("controller") is True
            and owner.get("kind") == "Deployment"
            and owner.get("uid") == deployment_uid
            for owner in item["metadata"].get("ownerReferences", [])
        )
    }
    pods = kubectl_json("-n", "probe-a", "get", "pods", "-l", selector, "-o", "json")[
        "items"
    ]
    result = []
    for pod in pods:
        if not any(
            owner.get("controller") is True
            and owner.get("kind") == "ReplicaSet"
            and owner.get("uid") in owned
            for owner in pod["metadata"].get("ownerReferences", [])
        ):
            continue
        container = next(c for c in pod["spec"]["containers"] if c["name"] == "ws-hub")
        status = next(
            c for c in pod["status"]["containerStatuses"] if c["name"] == "ws-hub"
        )
        if (
            container["image"] != image
            or container["imagePullPolicy"] != "Never"
            or pod["metadata"]
            .get("annotations", {})
            .get("university-ecosystem.io/source-sha")
            != source_sha
            or not status.get("ready")
            or not status.get("containerID")
            or not status.get("imageID")
        ):
            raise ValueError("unready or unbound ws-hub replica")
        address = pod["status"]["podIP"]
        if ipaddress.ip_address(address).version != 4:
            raise ValueError("ws-hub pod address must be IPv4")
        result.append(
            {
                "name": pod["metadata"]["name"],
                "uid": pod["metadata"]["uid"],
                "ip": address,
                "container_id": status["containerID"],
                "image_id": status["imageID"],
                "restarts": status["restartCount"],
            }
        )
    if len(result) != deployment["spec"]["replicas"]:
        raise ValueError("ws-hub replica count mismatch")
    return sorted(result, key=lambda item: item["name"])


def authorized_source(app: list[dict[str, Any]], source: Pod) -> None:
    """Require the original monitoring pod identity and the rendered policy grant."""
    if (source.namespace, source.name) != (
        "monitoring",
        "prometheus-0",
    ) or not source.uid:
        raise ValueError("unexpected monitoring source")
    namespace = kubectl_json("get", "namespace", source.namespace, "-o", "json")
    pod = kubectl_json("-n", source.namespace, "get", "pod", source.name, "-o", "json")
    if pod["metadata"]["uid"] != source.uid:
        raise ValueError("monitoring pod identity changed")
    policy = find(app, "NetworkPolicy", "probe-a-ws-hub-policy")
    grants = [
        peer
        for rule in policy["spec"]["ingress"]
        if {"protocol": "TCP", "port": 9108} in rule.get("ports", [])
        for peer in rule.get("from", [])
    ]
    if len(grants) != 1:
        raise ValueError("metrics grant is ambiguous")
    namespace_labels = grants[0]["namespaceSelector"]["matchLabels"]
    pod_labels = grants[0]["podSelector"]["matchLabels"]
    if (
        not namespace_labels
        or not pod_labels
        or any(
            namespace["metadata"]["labels"].get(key) != value
            for key, value in namespace_labels.items()
        )
        or any(
            pod["metadata"]["labels"].get(key) != value
            for key, value in pod_labels.items()
        )
    ):
        raise ValueError("monitoring pod does not match rendered policy")


def bounded_kubectl_json(*args: str) -> dict[str, Any]:
    """Keep Service and source identity reads within a fixed local deadline."""
    result = run_command(["kubectl", *args], timeout=10)
    document = json.loads(result.stdout)
    if not isinstance(document, dict):
        raise ValueError("non-object Kubernetes response")
    return document


def authorized_ingress_source(app: list[dict[str, Any]], source: Pod) -> dict[str, Any]:
    """Bind the existing ingress-labelled probe to the rendered 8081 grant."""
    if (source.namespace, source.name) != (
        "ingress-nginx",
        "ingress-controller",
    ) or not source.uid:
        raise ValueError("unexpected ingress-labelled source")
    namespace = bounded_kubectl_json("get", "namespace", source.namespace, "-o", "json")
    pod = bounded_kubectl_json(
        "-n", source.namespace, "get", "pod", source.name, "-o", "json"
    )
    meta, spec, status = pod["metadata"], pod["spec"], pod["status"]
    grants = [
        peer
        for rule in find(app, "NetworkPolicy", "probe-a-ws-hub-policy")["spec"][
            "ingress"
        ]
        if {"protocol": "TCP", "port": 8081} in rule.get("ports", [])
        for peer in rule.get("from", [])
    ]
    if len(grants) != 1:
        raise ValueError("public-port grant is ambiguous")
    ns_labels = grants[0]["namespaceSelector"]["matchLabels"]
    pod_labels = grants[0]["podSelector"]["matchLabels"]
    container = next(
        item for item in status["containerStatuses"] if item["name"] == "probe"
    )
    if (
        namespace["metadata"].get("name") != source.namespace
        or (meta.get("namespace"), meta.get("name"), meta.get("uid"))
        != (source.namespace, source.name, source.uid)
        or status.get("podIP") != source.ip
        or spec.get("hostNetwork", False) is not False
        or [item["name"] for item in spec["containers"]] != ["probe"]
        or container.get("ready") is not True
        or not container.get("containerID")
        or type(container.get("restartCount")) is not int
        or container["restartCount"] < 0
        or not ns_labels
        or not pod_labels
        or any(
            namespace["metadata"].get("labels", {}).get(k) != v
            for k, v in ns_labels.items()
        )
        or any(meta.get("labels", {}).get(k) != v for k, v in pod_labels.items())
    ):
        raise ValueError("ingress-labelled source identity or grant changed")
    return {
        "uid": source.uid,
        "container_id": container["containerID"],
        "restarts": container["restartCount"],
    }


def check_ws_service_shape(service: dict[str, Any], selector: dict[str, str]) -> None:
    """Check the rendered or live public-port-only ClusterIP Service."""
    meta, spec = service["metadata"], service["spec"]
    if (
        service.get("apiVersion") != "v1"
        or service.get("kind") != "Service"
        or (meta.get("namespace"), meta.get("name")) != ("probe-a", "probe-a-ws-hub")
        or spec.get("type") != "ClusterIP"
        or spec.get("selector") != selector
        or spec.get("ports")
        != [{"name": "http", "port": 8081, "targetPort": "http", "protocol": "TCP"}]
        or spec.get("externalIPs")
        or spec.get("externalName")
        or spec.get("publishNotReadyAddresses", False) is not False
    ):
        raise ValueError("unexpected ws-hub Service")


def ws_service_identity(
    service: dict[str, Any], selector: dict[str, str]
) -> dict[str, str]:
    """Check the Service and return its allocated identity."""
    check_ws_service_shape(service, selector)
    meta, spec = service["metadata"], service["spec"]
    uid = meta.get("uid")
    ip = ipaddress.ip_address(spec.get("clusterIP", ""))
    private = any(
        ip in ipaddress.ip_network(net)
        for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    )
    if (
        not isinstance(uid, str)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", uid)
        or ip.version != 4
        or not private
    ):
        raise ValueError("invalid ws-hub Service identity")
    return {"uid": uid, "cluster_ip": str(ip)}


def create_ws_service(
    app: list[dict[str, Any]], deployment: dict[str, Any]
) -> dict[str, str]:
    """Create the unmodified rendered Service; an existing name is a failure."""
    service = find(app, "Service", "probe-a-ws-hub")
    selector = deployment["spec"]["selector"]["matchLabels"]
    container = next(
        c
        for c in deployment["spec"]["template"]["spec"]["containers"]
        if c["name"] == "ws-hub"
    )
    if (
        service["metadata"].get("uid")
        or not selector
        or {"name": "http", "containerPort": 8081, "protocol": "TCP"}
        not in container.get("ports", [])
    ):
        raise ValueError("unexpected rendered ws-hub Service target")
    check_ws_service_shape(service, selector)
    result = run_command(
        ["kubectl", "create", "-f", "-", "-o", "json"],
        stdin=json.dumps(service),
        timeout=30,
    )
    created = json.loads(result.stdout)
    if not isinstance(created, dict):
        raise ValueError("invalid created Service")
    return ws_service_identity(created, selector)


def ws_service_snapshot(
    deployment: dict[str, Any], identity: dict[str, str], replicas: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Bind ready EndpointSlices to the created Service and real replica UIDs."""
    service = bounded_kubectl_json(
        "-n", "probe-a", "get", "service", "probe-a-ws-hub", "-o", "json"
    )
    if (
        ws_service_identity(service, deployment["spec"]["selector"]["matchLabels"])
        != identity
    ):
        raise ValueError("ws-hub Service identity changed")
    expected = {
        replica["uid"]: (replica["name"], replica["ip"]) for replica in replicas
    }
    if not expected or len(expected) != len(replicas):
        raise ValueError("ambiguous real ws-hub replicas")
    slices = bounded_kubectl_json(
        "-n",
        "probe-a",
        "get",
        "endpointslices",
        "-l",
        "kubernetes.io/service-name=probe-a-ws-hub",
        "-o",
        "json",
    )["items"]
    seen: set[str] = set()
    slice_uids: list[str] = []
    ready = True
    for item in slices:
        meta = item["metadata"]
        endpoints = item.get("endpoints")
        ports = item.get("ports")
        if endpoints is None:
            endpoints = []
        if ports is None:
            ports = []
        if (
            meta.get("namespace") != "probe-a"
            or meta.get("labels", {}).get("kubernetes.io/service-name")
            != "probe-a-ws-hub"
            or not meta.get("uid")
            or not any(
                ref.get("kind") == "Service"
                and ref.get("name") == "probe-a-ws-hub"
                and ref.get("uid") == identity["uid"]
                and ref.get("controller") is True
                for ref in meta.get("ownerReferences", [])
            )
            or item.get("addressType") != "IPv4"
            or not isinstance(endpoints, list)
            or not isinstance(ports, list)
            or len(ports) > 1
            or (bool(endpoints) and len(ports) != 1)
            or (
                ports
                and (ports[0].get("name"), ports[0].get("protocol")) != ("http", "TCP")
            )
            or (
                ports
                and ports[0].get("port") not in ((8081,) if endpoints else (None, 8081))
            )
        ):
            raise ValueError("unexpected ws-hub EndpointSlice")
        slice_uids.append(meta["uid"])
        if not endpoints:
            ready = False
        for endpoint in endpoints:
            ref = endpoint["targetRef"]
            uid = ref.get("uid")
            if (
                uid not in expected
                or uid in seen
                or (ref.get("kind"), ref.get("namespace"), ref.get("name"))
                != ("Pod", "probe-a", expected[uid][0])
                or endpoint.get("addresses") != [expected[uid][1]]
            ):
                raise ValueError("unexpected ws-hub endpoint")
            seen.add(uid)
            conditions = endpoint.get("conditions", {})
            ready = (
                ready
                and conditions.get("ready") is True
                and conditions.get("serving", True) is not False
                and conditions.get("terminating", False) is not True
            )
    if len(set(slice_uids)) != len(slice_uids):
        raise ValueError("duplicate EndpointSlice identity")
    if seen != set(expected) or not ready:
        return None
    return {
        "service_uid": identity["uid"],
        "slice_uids": sorted(slice_uids),
        "replica_uids": sorted(seen),
    }


def prove_ws_service(
    app: list[dict[str, Any]],
    deployment: dict[str, Any],
    replicas: list[dict[str, Any]],
    source: Pod,
    *,
    progress: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Prove only the in-cluster Service's ordinary public-port health route."""
    progress = progress if progress is not None else {}
    progress["stage"] = "source-before"
    source_before = authorized_ingress_source(app, source)
    progress["stage"] = "create-service"
    identity = create_ws_service(app, deployment)
    progress["stage"] = "endpoints-before"
    deadline = time.monotonic() + 30
    while True:
        snapshot = ws_service_snapshot(deployment, identity, replicas)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("ws-hub Service endpoints not ready")
        if snapshot is not None:
            break
        time.sleep(min(1.0, remaining))
    progress["stage"] = "source-pre-health"
    if authorized_ingress_source(app, source) != source_before:
        raise ValueError("service probe source changed")
    progress["stage"] = "health-request"
    observed = run_in_pod(source, HEALTH, [identity["cluster_ip"]], timeout=10)
    direct_result = None
    if observed == {"result": "transport-unavailable"}:
        progress["stage"] = "health-direct"
        direct = run_in_pod(source, HEALTH, [replicas[0]["ip"], "single"], timeout=3)
        direct_result = next(
            (
                category
                for category in (
                    "healthy",
                    "transport-unavailable",
                    "invalid",
                    "window-expired",
                )
                if direct == {"result": category}
            ),
            "exec-error",
        )
    elif observed != {"result": "healthy"}:
        progress["stage"] = (
            "health-invalid"
            if observed == {"result": "invalid"}
            else "health-window-expired"
            if observed == {"result": "window-expired"}
            else "health-exec-error"
        )
        raise ValueError("ws-hub Service health check failed")
    progress["stage"] = "source-post-health"
    if authorized_ingress_source(app, source) != source_before:
        raise ValueError("service probe source changed")
    progress["stage"] = "endpoints-after"
    if ws_service_snapshot(deployment, identity, replicas) != snapshot:
        raise ValueError("ws-hub Service endpoints changed")
    if direct_result is not None:
        return {
            "verdict": "inconclusive",
            "reason": "transport-unavailable",
            "direct_health": direct_result,
        }
    return {
        **snapshot,
        "source_uid": source.uid,
        "source": "ingress-labelled Python probe",
        "request": "GET /health/live",
        "verdict": "pass",
    }


def retire_ws_fixture(app: list[dict[str, Any]], pod: Pod, image: str) -> None:
    """Retire only this run's create-only matrix fixture, guarded by its UID."""
    created = pod.created
    if (
        not isinstance(created, CreatedPod)
        or (created.namespace, created.name) != ("probe-a", "probe-a-ws-hub")
        or (pod.namespace, pod.name, pod.uid)
        != (created.namespace, created.name, created.uid)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", created.uid)
    ):
        raise ValueError("ws-hub fixture has no matching creation identity")
    labels = find(app, "Deployment", "probe-a-ws-hub")["spec"]["template"]["metadata"][
        "labels"
    ]
    expected = stand_in_pod(
        "probe-a",
        "probe-a-ws-hub",
        {**labels, "probe-role": "a-ws"},
        image,
        "8081,9108",
    )
    live = kubectl_json("-n", "probe-a", "get", "pod", "probe-a-ws-hub", "-o", "json")
    metadata, spec = live["metadata"], live["spec"]
    if (
        (metadata.get("namespace"), metadata.get("name"), metadata.get("uid"))
        != (created.namespace, created.name, created.uid)
        or metadata.get("ownerReferences")
        or metadata.get("deletionTimestamp")
        or any(
            metadata.get("labels", {}).get(k) != v
            for k, v in expected["metadata"]["labels"].items()
        )
        or live["status"].get("podIP") != pod.ip
        or spec.get("automountServiceAccountToken") is not False
        or spec.get("hostNetwork", False) is not False
        or len(spec.get("containers", [])) != 1
        or any(
            spec["containers"][0].get(key) != value
            for key, value in expected["spec"]["containers"][0].items()
        )
    ):
        raise ValueError("ws-hub fixture identity or specification changed")
    options = {
        "apiVersion": "v1",
        "kind": "DeleteOptions",
        "preconditions": {"uid": created.uid},
    }
    run_command(
        [
            "kubectl",
            "delete",
            "--raw",
            "/api/v1/namespaces/probe-a/pods/probe-a-ws-hub",
            "-f",
            "-",
        ],
        stdin=json.dumps(options),
        timeout=30,
    )
    deadline = time.monotonic() + 45
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("ws-hub fixture deletion timed out")
        observed = run_command(
            [
                "kubectl",
                "-n",
                "probe-a",
                "get",
                "pod",
                "probe-a-ws-hub",
                "--ignore-not-found",
                "-o",
                "json",
            ],
            timeout=min(5.0, remaining),
        )
        if not observed.stdout.strip():
            return
        pending = json.loads(observed.stdout)
        if (
            not isinstance(pending, dict)
            or not isinstance(pending.get("metadata"), dict)
            or pending["metadata"].get("uid") != created.uid
        ):
            raise ValueError("ws-hub fixture was replaced")
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


PROMETHEUS_FAILURE_STAGES = frozenset(
    {
        "input",
        "targets-before",
        "create-config",
        "create-policy",
        "create-pod",
        "pod-ready",
        "source-before",
        "scrape",
        "source-after",
        "targets-after",
    }
)
KUBERNETES_UID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"


def valid_prometheus_proof(
    proof: Any, expected: Any, *, projected: bool = False
) -> bool:
    """Accept only complete sanitized results for exactly the confirmed replicas."""
    if not isinstance(proof, dict) or set(proof) != {"verdict", "source", "checks"}:
        return False
    source, checks = proof["source"], proof["checks"]
    if proof["verdict"] != "pass" or not isinstance(source, dict):
        return False
    fields = {"namespace", "name", "uid"}
    if not projected:
        fields |= {"image_id", "container_id"}
    if set(source) != fields or source["namespace"] != "monitoring":
        return False
    if any(not isinstance(source[key], str) for key in fields):
        return False
    if not (
        re.fullmatch(r"netpol-prom-[0-9a-f]{12}", source["name"])
        and re.fullmatch(KUBERNETES_UID, source["uid"])
    ):
        return False
    if not projected and not (
        re.fullmatch(r"sha256:[0-9a-f]{64}", source["image_id"])
        and re.fullmatch(
            r"(?:containerd|docker)://[0-9a-f]{64}", source["container_id"]
        )
    ):
        return False
    if (
        not isinstance(expected, list)
        or not expected
        or not isinstance(checks, list)
        or len(checks) != len(expected)
        or any(
            not isinstance(replica, dict)
            or not isinstance(replica.get("uid"), str)
            or not re.fullmatch(KUBERNETES_UID, replica["uid"])
            for replica in expected
        )
    ):
        return False
    if any(
        not isinstance(check, dict)
        or set(check) != {"replica_uid", "verdict"}
        or not isinstance(check["replica_uid"], str)
        or check["verdict"] != "pass"
        for check in checks
    ):
        return False
    uids = [replica["uid"] for replica in expected]
    return len(set(uids)) == len(uids) and sorted(
        check["replica_uid"] for check in checks
    ) == sorted(uids)


def actual_ws_phase(
    root: Path,
    rendered: dict[str, Any],
    pods: dict[str, Pod],
    passwords: dict[str, str],
    *,
    python_image: str,
    image: str,
    source_sha: str,
) -> dict[str, Any]:
    """Run only the authorized positive scrape; retain fixed, secret-free failures."""
    stage = "render"
    service_progress = {"stage": "service-start"}
    direct_health = None
    python_scrape = None
    service = None
    prometheus_stage = None
    checks: list[dict[str, str]] = []
    try:
        app, store = rendered["probe-a"]
        deployment = ws_deployment(app, image, source_sha)
        container = next(
            c
            for c in deployment["spec"]["template"]["spec"]["containers"]
            if c["name"] == "ws-hub"
        )
        env = {entry["name"]: entry.get("value") for entry in container["env"]}
        jwks = urlparse(env["JWKS_URL"])
        if (jwks.scheme, jwks.hostname, jwks.port, jwks.path) != (
            "http",
            "probe-a-backend",
            8000,
            "/.well-known/jwks.json",
        ):
            raise ValueError("unexpected JWKS fixture target")
        token, cache_password, shared = (secrets.token_hex(32) for _ in range(3))
        values = {
            "JWT_SECRET_FILE": secrets.token_hex(32),
            "WS_HUB_INTERNAL_SECRET_FILE": shared,
            "INTERNAL_AUTH_TOKEN_FILE": shared,
            "NATS_URL_FILE": "nats://netpol-ws-nats:4222",
            "NATS_AUTH_TOKEN_FILE": token,
            "REDIS_URL_FILE": f"redis://:{quote(cache_password, safe='')}@probe-a-redis-master:6379/0",
            "REVOCATION_REDIS_URL_FILE": f"redis://:{quote(passwords['probe-a'], safe='')}@probe-a-revocation-redis-master:6379/0",
        }
        stage = "cache-redis"
        apply_objects(cache_fixture(app, store, cache_password))
        kubectl(
            "-n",
            "probe-a",
            "rollout",
            "status",
            "statefulset/probe-a-redis-master",
            "--timeout=300s",
        )
        stage = "nats"
        apply_objects(nats_fixture(root, python_image, token))
        kubectl(
            "-n",
            "probe-a",
            "wait",
            "--for=condition=Ready",
            "pod/netpol-ws-nats",
            "--timeout=120s",
        )
        result = run_command(
            [
                "kubectl",
                "-n",
                "probe-a",
                "exec",
                "netpol-ws-nats",
                "-c",
                "probe",
                "--",
                "python3",
                "-I",
                "-c",
                NATS_STREAMS,
            ],
            timeout=30,
        )
        if json.loads(result.stdout).get("result") != "ready":
            raise ValueError("NATS stream fixture unavailable")
        stage = "jwks"
        if run_in_pod(pods["a-backend"], VERIFY_JWKS, []).get("result") != "valid":
            raise ValueError("JWKS fixture unavailable")
        # The real processor phase has already created this backend Service.
        stage = "deployment"
        service_account = find(
            app,
            "ServiceAccount",
            deployment["spec"]["template"]["spec"]["serviceAccountName"],
        )
        apply_objects([*ws_secrets(deployment, values), service_account, deployment])
        kubectl(
            "-n",
            "probe-a",
            "rollout",
            "status",
            "deployment/probe-a-ws-hub",
            "--timeout=180s",
        )
        stage = "replicas"
        before = replicas(deployment, image, source_sha)
        stage = "authorized-scrape"
        authorized_source(app, pods["prometheus"])
        for replica in before:
            observed = run_in_pod(
                pods["prometheus"], SCRAPE, [replica["ip"]], timeout=3
            )
            checks.append(
                {
                    "replica_uid": replica["uid"],
                    "verdict": "pass"
                    if observed == {"result": "valid-exposition"}
                    else "inconclusive",
                }
            )
        authorized_source(app, pods["prometheus"])
        if replicas(deployment, image, source_sha) != before:
            raise ValueError("replica changed during scrape")
        if not checks or any(check["verdict"] != "pass" for check in checks):
            raise ValueError("authorized scrape incomplete")
        python_scrape = {
            "verdict": "pass",
            "source": "Prometheus-labelled Python probe",
        }
        stage = "retire-fixture"
        retire_ws_fixture(app, pods["a-ws"], python_image)
        stage = "service-health"
        service = prove_ws_service(
            app, deployment, before, pods["ingress"], progress=service_progress
        )
        service_progress["stage"] = "service-verdict"
        if service.get("verdict") != "pass":
            if service.get("reason") == "transport-unavailable" and service.get(
                "direct_health"
            ) in (
                "healthy",
                "transport-unavailable",
                "invalid",
                "window-expired",
                "exec-error",
            ):
                service_progress["stage"] = "replica-recheck"
                if replicas(deployment, image, source_sha) != before:
                    raise ValueError("ws-hub replica identity changed")
                service_progress["stage"] = "health-transport-exhausted"
                direct_health = service["direct_health"]
            raise ValueError("ws-hub Service proof or replica identity changed")
        service_progress["stage"] = "replica-recheck"
        if replicas(deployment, image, source_sha) != before:
            raise ValueError("ws-hub Service proof or replica identity changed")
        stage = "real-prometheus"
        authorized_source(app, pods["prometheus"])
        from networkpolicy_runtime_real_prometheus import prove_actual_prometheus

        prometheus_proof = prove_actual_prometheus(root, app, copy.deepcopy(before))
        if not valid_prometheus_proof(prometheus_proof, before):
            if (
                isinstance(prometheus_proof, dict)
                and prometheus_proof.get("verdict") == "inconclusive"
                and prometheus_proof.get("stage") in PROMETHEUS_FAILURE_STAGES
            ):
                prometheus_stage = prometheus_proof["stage"]
            raise ValueError("real Prometheus proof incomplete")
        authorized_source(app, pods["prometheus"])
        if replicas(deployment, image, source_sha) != before:
            raise ValueError("ws-hub replica identity changed")
        prometheus = {
            "verdict": "pass",
            "source": {
                key: prometheus_proof["source"][key]
                for key in ("namespace", "name", "uid")
            },
            "checks": [dict(check) for check in prometheus_proof["checks"]],
        }
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
        SystemExit,
        yaml.YAMLError,
        subprocess.SubprocessError,
        ImportError,
    ):
        failure = {"verdict": "inconclusive", "stage": stage, "checks": checks}
        if python_scrape is not None:
            failure["python_scrape"] = python_scrape
        if (
            stage == "real-prometheus"
            and service is not None
            and service.get("verdict") == "pass"
        ):
            failure["service"] = service
        if stage == "real-prometheus":
            failure["prometheus"] = {"verdict": "inconclusive"}
            if prometheus_stage is not None:
                failure["prometheus"]["stage"] = prometheus_stage
        if stage == "service-health":
            substage = service_progress.get("stage")
            failure["substage"] = (
                substage
                if substage
                in (
                    "service-start",
                    "source-before",
                    "create-service",
                    "endpoints-before",
                    "source-pre-health",
                    "health-request",
                    "health-direct",
                    "health-invalid",
                    "health-window-expired",
                    "health-exec-error",
                    "health-transport-exhausted",
                    "source-post-health",
                    "endpoints-after",
                    "service-verdict",
                    "replica-recheck",
                )
                else "service-unknown"
            )
            if substage == "health-transport-exhausted" and direct_health in (
                "healthy",
                "transport-unavailable",
                "invalid",
                "window-expired",
                "exec-error",
            ):
                failure["direct_health"] = direct_health
        return failure
    return {
        "verdict": "pass"
        if checks and all(check["verdict"] == "pass" for check in checks)
        else "inconclusive",
        "source_sha": source_sha,
        "replicas": [
            {key: value for key, value in replica.items() if key != "ip"}
            for replica in before
        ],
        "checks": checks,
        "python_scrape": python_scrape,
        "prometheus": prometheus,
        "matrix_fixture": {"uid": pods["a-ws"].uid, "verdict": "retired"},
        "service": service,
        "source": "Prometheus-labelled Python probe",
        "scope": "authorized Python and Prometheus scrapes and in-cluster Service health; actual ingress not tested",
    }
