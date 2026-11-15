"""Source-bound ws-hub positive scrape in the existing disposable kind proof.

The matrix remains a stand-in policy proof. This separate phase only requests
metrics from actual chart-selected ws-hub replicas through the Prometheus-labelled
probe pod; it does not test denied peers or run a Prometheus server.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml
from networkpolicy_runtime_kube import (
    Pod,
    apply_objects,
    find,
    kubectl,
    kubectl_json,
    run_command,
    run_in_pod,
)
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
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
        SystemExit,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ):
        return {"verdict": "inconclusive", "stage": stage, "checks": checks}
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
        "source": "Prometheus-labelled Python probe",
        "scope": "authorized positive HTTP scrape only",
    }
