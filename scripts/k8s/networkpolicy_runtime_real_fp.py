"""Optional actual-FP phase of the existing runner, after its unchanged 40 rows.

All state belongs to the caller's disposable cluster. No production policies,
receipts, dependencies, or identities are created by a separate framework.
"""

from __future__ import annotations

import base64
import copy
import datetime
import json
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from networkpolicy_runtime_app import generate_signing_key, jwks_document, publish_jwks
from networkpolicy_runtime_kube import (
    Pod,
    apply_objects,
    find,
    kubectl,
    kubectl_json,
    run_command,
    run_in_pod,
)
from networkpolicy_runtime_processor import (
    grpc_probe_input,
    grpc_probe_verdict,
    processor_token,
    real_processor_deployment,
)
from networkpolicy_runtime_standins import PROBE_SRC
from networkpolicy_runtime_temporal import (
    _key_pem,
    _mount,
    _object,
    bootstrap_temporal,
    compose_image,
    secret_volume,
    wire_processor_temporal,
)

NATS_INIT = r"""
import json, socket
from pathlib import Path
password = Path('/auth/password').read_text()
s = socket.create_connection(('127.0.0.1',4222), timeout=5)
s.settimeout(5)
f = s.makefile('rb')
if not f.readline(16385).startswith(b'INFO '): raise SystemExit(1)
connect = json.dumps({'user':'netpol','pass':password,'verbose':False}).encode()
s.sendall(b'CONNECT '+connect+b'\r\nSUB _INBOX.netpol 1\r\n')
config = json.dumps({'name':'FILES_PROCESS','subjects':['files.process'],'storage':'memory','retention':'workqueue'}).encode()
s.sendall(b'PUB $JS.API.STREAM.CREATE.FILES_PROCESS _INBOX.netpol '+str(len(config)).encode()+b'\r\n'+config+b'\r\nPING\r\n')
for _ in range(32):
    line = f.readline(16385)
    if line == b'PING\r\n': s.sendall(b'PONG\r\n'); continue
    if line.startswith(b'-ERR'): raise SystemExit(1)
    if line.startswith(b'MSG '):
        size=int(line.split()[-1])
        if not 0 < size < 65536: raise SystemExit(1)
        data=f.read(size)
        if len(data)!=size or f.read(2)!=b'\r\n': raise SystemExit(1)
        response=json.loads(data)
        if response.get('error') or response.get('config',{}).get('subjects') != ['files.process']: raise SystemExit(1)
        print('{"result":"ready"}'); break
else: raise SystemExit(1)
"""
REDIS_REVOKE = r"""
import json, socket, sys
args = json.load(sys.stdin)
def command(*parts):
    raw=[str(p).encode() for p in parts]
    return b'*%d\r\n'%len(raw)+b''.join(b'$%d\r\n%s\r\n'%(len(p),p) for p in raw)
with socket.create_connection((args['host'],6379),timeout=3) as s:
    s.settimeout(3)
    reader=s.makefile('rb')
    s.sendall(command('AUTH',args['password']))
    if reader.readline(512)!=b'+OK\r\n': raise SystemExit(1)
    if args.get('action') == 'check':
        s.sendall(command('GET','revoked:jti:'+args['jti']))
        if reader.readline(512)!=b'$-1\r\n': raise SystemExit(1)
    else:
        s.sendall(command('SET','revoked:jti:'+args['jti'],'1','EX',600))
        if reader.readline(512)!=b'+OK\r\n': raise SystemExit(1)
print(json.dumps({'result':'unrevoked' if args.get('action') == 'check' else 'revoked'}))
"""


def bootstrap_nats(root: Path, namespace: str, python_image: str) -> str:
    """Return PRIVATE URL only after a real authenticated JetStream response."""
    image = compose_image(root, "nats")
    password = secrets.token_hex(32)
    config = json.dumps(
        {
            "port": 4222,
            "jetstream": {"store_dir": "/data"},
            "authorization": {"user": "netpol", "password": password},
        }
    )
    objects = [
        _object(
            "Secret",
            "netpol-nats-auth",
            namespace,
            stringData={"password": password, "nats.conf": config},
        ),
        _object(
            "Service",
            "netpol-nats",
            namespace,
            spec={"selector": {"netpol-fixture": "nats"}, "ports": [{"port": 4222}]},
        ),
        _object(
            "Pod",
            "netpol-nats",
            namespace,
            spec={
                "automountServiceAccountToken": False,
                "containers": [
                    {
                        "name": "nats",
                        "image": image,
                        "command": ["nats-server", "-c", "/auth/nats.conf"],
                        "volumeMounts": [
                            _mount("auth", "/auth"),
                            {"name": "data", "mountPath": "/data"},
                        ],
                        "readinessProbe": {
                            "tcpSocket": {"port": 4222},
                            "periodSeconds": 2,
                        },
                    },
                    {
                        "name": "probe",
                        "image": python_image,
                        "command": ["sleep", "infinity"],
                        "volumeMounts": [_mount("auth", "/auth")],
                    },
                ],
                "volumes": [
                    secret_volume("auth", "netpol-nats-auth"),
                    {"name": "data", "emptyDir": {}},
                ],
            },
        ),
    ]
    objects[-1]["metadata"]["labels"] = {
        "app.kubernetes.io/name": "nats",
        "netpol-fixture": "nats",
    }
    apply_objects(objects)
    kubectl(
        "-n",
        namespace,
        "wait",
        "--for=condition=Ready",
        "pod/netpol-nats",
        "--timeout=120s",
    )
    result = run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            "netpol-nats",
            "-c",
            "probe",
            "--",
            "python3",
            "-I",
            "-c",
            NATS_INIT,
        ],
        timeout=30,
    )
    if json.loads(result.stdout).get("result") != "ready":
        raise ValueError("JetStream not ready")
    return f"nats://netpol:{password}@netpol-nats:4222"


def grpc_credentials(
    server_name: str, identity_uri: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Only the caller-provided, already-rendered client URI is certified."""
    now = datetime.datetime.now(datetime.UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "netpol-grpc")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(ca_key, hashes.SHA256())
    )
    public = ca.public_bytes(serialization.Encoding.PEM).decode()

    def leaf(client: bool) -> dict[str, str]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(hours=2))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.UniformResourceIdentifier(identity_uri)]
                    if client
                    else [x509.DNSName(server_name)]
                ),
                False,
            )
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        ExtendedKeyUsageOID.CLIENT_AUTH
                        if client
                        else ExtendedKeyUsageOID.SERVER_AUTH
                    ]
                ),
                False,
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .sign(ca_key, hashes.SHA256())
        )
        return {
            "tls.crt": cert.public_bytes(serialization.Encoding.PEM).decode(),
            "tls.key": _key_pem(key),
            "ca.crt": public,
        }

    return leaf(False), leaf(True)


def materialize_processor_secrets(
    deployment: dict[str, Any],
    namespace: str,
    values: dict[str, str],
    grpc: dict[str, str],
) -> None:
    """Populate exactly the rendered Secret/key references; no auth env downgrade."""
    spec = deployment["spec"]["template"]["spec"]
    container = next(c for c in spec["containers"] if c["name"] == "file-processor")
    mounts = {mount["name"]: mount["mountPath"] for mount in container["volumeMounts"]}
    environment = {e["name"]: e.get("value") for e in container["env"]}
    generated: dict[str, dict[str, str]] = {}
    for volume in spec["volumes"]:
        secret = volume.get("secret")
        if not secret or volume["name"] == "netpol-temporal-worker":
            continue
        data = generated.setdefault(secret["secretName"], {})
        mount = mounts[volume["name"]]
        for item in secret.get("items", []):
            path = mount + "/" + item["path"]
            names = [k for k, v in environment.items() if v == path]
            if len(names) != 1:
                raise ValueError("unmapped rendered Secret item")
            name = names[0]
            if name in values:
                data[item["key"]] = values[name]
            elif name in {
                "FP_GRPC_TLS_CERT_FILE",
                "FP_GRPC_TLS_KEY_FILE",
                "FP_GRPC_CLIENT_CA_FILE",
            }:
                key = {
                    "FP_GRPC_TLS_CERT_FILE": "tls.crt",
                    "FP_GRPC_TLS_KEY_FILE": "tls.key",
                    "FP_GRPC_CLIENT_CA_FILE": "ca.crt",
                }[name]
                data[item["key"]] = grpc[key]
            else:
                raise ValueError("required fixture credential missing")
    apply_objects(
        [
            _object("Secret", name, namespace, stringData=data)
            for name, data in generated.items()
        ]
    )


def replica_state(namespace: str, labels: dict[str, str]) -> list[dict[str, Any]]:
    selector = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    pods = kubectl_json("-n", namespace, "get", "pods", "-l", selector, "-o", "json")[
        "items"
    ]
    result = []
    for pod in pods:
        status = next(
            (
                s
                for s in pod.get("status", {}).get("containerStatuses", [])
                if s["name"] == "file-processor"
            ),
            None,
        )
        if status is None:
            continue  # original40-row stand-in is not a real replica
        if not status.get("ready") or not status.get("containerID"):
            raise ValueError("replica not ready")
        result.append(
            {
                "name": pod["metadata"]["name"],
                "uid": pod["metadata"]["uid"],
                "ip": pod["status"]["podIP"],
                "container_id": status["containerID"],
                "image_id": status.get("imageID", ""),
                "restarts": status["restartCount"],
            }
        )
    return sorted(result, key=lambda item: item["name"])


def call_processor(
    namespace: str, replica: dict[str, Any], server_name: str, token: str
) -> dict[str, str]:
    payload = grpc_probe_input(
        address=replica["ip"] + ":50051",
        server_name=server_name,
        token=token,
        ca_file="/grpc/ca.crt",
        certificate_file="/grpc/tls.crt",
        key_file="/grpc/tls.key",
    )
    try:
        out = run_command(
            [
                "kubectl",
                "-n",
                namespace,
                "exec",
                "-i",
                "netpol-grpc-client",
                "--",
                "/usr/local/bin/networkpolicy-probe",
            ],
            stdin=payload,
            timeout=20,
        )
        parsed = json.loads(out.stdout)
        return parsed if isinstance(parsed, dict) else {"result": "setup-error"}
    except (subprocess.SubprocessError, ValueError, OSError):
        return {"result": "setup-error"}


def validate_fixture_token(
    signer: Any, bearer: str, env: dict[str, Any], jti: str
) -> None:
    """Independent signature/claims check, never serializing bearer or payload."""
    header, payload, signature = bearer.split(".")

    def decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    signer.private_key.public_key().verify(
        decode(signature),
        f"{header}.{payload}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    claims = json.loads(decode(payload))
    if (
        claims.get("iss") != env["FP_JWT_ISSUER"]
        or claims.get("aud") != env["FP_JWT_AUDIENCE"]
        or claims.get("jti") != jti
        or claims.get("is_active") is not True
        or claims.get("exp", 0) < time.time() + 30
        or claims.get("iat", 0) > time.time()
    ):
        raise ValueError("fixture token is not valid for this proof")


def actual_processor_phase(
    root: Path,
    rendered: dict[str, Any],
    pods: dict[str, Pod],
    passwords: dict[str, str],
    *,
    python_image: str,
    processor_image: str,
    diagnostic_image: str,
    source_sha: str,
) -> dict[str, Any]:
    """Additional receipt section; original baseline/40 rows already completed.

    Test both replicas of probe-a, preserving the rendered original
    labels, policies, transport flags, refresh interval and replica count. Real
    probe-b is not claimed; both namespaces stay covered by the original matrix.
    A fixed stage marker is the only setup-error detail allowed into receipts.
    """
    checks = []
    rotations = []
    stage = "inputs"
    try:
        chart_values = yaml.safe_load(
            (root / "charts/university-ecosystem/values.yaml").read_text()
        )
        for release, (resources, _) in [("probe-a", rendered["probe-a"])]:
            short = release.split("-")[-1]
            stage = f"{release}:temporal"
            setup = bootstrap_temporal(
                root, release, python_image, chart_values["backup"]["postgresImage"]
            )
            if setup.get("result") != "ready":
                return {"verdict": "inconclusive", "stage": stage, "checks": checks}
            stage = f"{release}:nats"
            nats_url = bootstrap_nats(root, release, python_image)
            old = generate_signing_key("primary")
            new = generate_signing_key("netpol-rotated")
            stage = f"{release}:processor-config"
            deployment = real_processor_deployment(
                resources,
                release,
                image=processor_image,
                diagnostic_image=diagnostic_image,
                source_sha=source_sha,
                temporal_endpoint=setup["endpoint"],
                temporal_ca_configmap=setup["ca_configmap"],
            )
            spec = deployment["spec"]["template"]["spec"]
            processor = next(
                c for c in spec["containers"] if c["name"] == "file-processor"
            )
            env = {e["name"]: e.get("value") for e in processor["env"]}
            if env.get("FP_INTERNAL_HTTP_MTLS_ENABLED") == "true":
                raise ValueError("SPIFFE fixture required by rendered profile")
            server_name = f"{release}-file-processor.{release}.svc"
            uris = env["FP_GRPC_ALLOWED_CLIENT_URIS"].split(",")
            if len(uris) != 1:
                raise ValueError("ambiguous rendered client identity")
            server, client = grpc_credentials(server_name, uris[0])
            public = (
                old.private_key.public_key()
                .public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                .decode()
            )
            redis_host = pods[short + "-redis"].ip
            values = {
                "FP_NATS_URL_FILE": nats_url,
                "FP_MINIO_ACCESS_KEY_FILE": secrets.token_hex(16),
                "FP_MINIO_SECRET_KEY_FILE": secrets.token_hex(32),
                "FP_PROCESSING_CAPABILITY_SECRET_FILE": secrets.token_hex(32),
                "FP_RSA_PUBLIC_KEY_FILE": public,
                "FP_TEMPORAL_API_KEY_FILE": secrets.token_urlsafe(32),
                "FP_REVOCATION_REDIS_URL_FILE": f"redis://:{quote(passwords[release], safe='')}@{release}-revocation-redis-master:6379/0",
            }
            materialize_processor_secrets(deployment, release, values, server)
            wire_processor_temporal(deployment, setup)
            # Existing backend-labelled publisher stays unchanged; Service uses
            # its exact probe role, so real calls traverse the rendered policy.
            jwks = urlparse(env["FP_JWKS_URL"])
            if (
                jwks.scheme != "http"
                or jwks.port != 8000
                or jwks.path != "/.well-known/jwks.json"
            ):
                raise ValueError("rendered JWKS transport requires a different fixture")
            apply_objects(
                [
                    _object(
                        "Service",
                        jwks.hostname,
                        release,
                        spec={
                            "selector": {"probe-role": short + "-backend"},
                            "ports": [{"port": 8000}],
                        },
                    ),
                    find(resources, "ServiceAccount", spec["serviceAccountName"]),
                ]
            )
            if (
                publish_jwks(pods[short + "-backend"], jwks_document([old])).get(
                    "result"
                )
                != "published"
            ):
                raise ValueError("JWKS publication failed")
            gateway = find(resources, "Deployment", release + "-gateway")["spec"][
                "template"
            ]["metadata"]["labels"]
            client_pod = _object(
                "Pod",
                "netpol-grpc-client",
                release,
                spec={
                    "automountServiceAccountToken": False,
                    "containers": [
                        {
                            "name": "probe",
                            "image": diagnostic_image,
                            "imagePullPolicy": "Never",
                            "command": ["sleep", "infinity"],
                            "volumeMounts": [_mount("grpc", "/grpc")],
                        }
                    ],
                    "volumes": [secret_volume("grpc", "netpol-grpc-client")],
                },
            )
            client_pod["metadata"]["labels"] = copy.deepcopy(gateway)
            apply_objects(
                [
                    _object("Secret", "netpol-grpc-client", release, stringData=client),
                    client_pod,
                    deployment,
                ]
            )
            stage = f"{release}:processor-ready"
            kubectl(
                "-n",
                release,
                "rollout",
                "status",
                "deployment/" + deployment["metadata"]["name"],
                "--timeout=180s",
            )
            kubectl(
                "-n",
                release,
                "wait",
                "--for=condition=Ready",
                "pod/netpol-grpc-client",
                "--timeout=60s",
            )
            labels = deployment["spec"]["selector"]["matchLabels"]
            before = replica_state(release, labels)
            if len(before) != deployment["spec"].get("replicas", 1):
                raise ValueError("replica count mismatch")
            stage = f"{release}:real-network-paths"
            for replica in before:
                for mode, host, port, extra, expected in [
                    ("redis-ping", redis_host, 6379, [], "redis-pong"),
                    (
                        "redis-ping",
                        f"{release}-revocation-redis-master",
                        6379,
                        [],
                        "redis-pong",
                    ),
                    (
                        "http",
                        pods[short + "-backend"].ip,
                        8000,
                        ["/.well-known/jwks.json"],
                        "http",
                    ),
                    ("http", jwks.hostname, 8000, ["/.well-known/jwks.json"], "http"),
                ]:
                    output = run_command(
                        [
                            "kubectl",
                            "-n",
                            release,
                            "exec",
                            "-i",
                            replica["name"],
                            "-c",
                            "probe",
                            "--",
                            "python3",
                            "-I",
                            "-c",
                            PROBE_SRC,
                            mode,
                            host,
                            str(port),
                            "3",
                            *extra,
                        ],
                        stdin=passwords[release] if mode == "redis-ping" else "",
                        timeout=20,
                    )
                    observed = json.loads(output.stdout)
                    passed = observed.get("result") == expected and (
                        observed.get("status") == "200"
                        if mode == "http"
                        else observed.get("auth") == "+OK"
                    )
                    checks.append(
                        {
                            "check_id": "actual-network-" + mode,
                            "namespace": release,
                            "timestamp_utc": datetime.datetime.now(
                                datetime.UTC
                            ).isoformat(),
                            "pod_uid": replica["uid"],
                            "destination": host,
                            "observed": observed,
                            "verdict": "pass" if passed else "inconclusive",
                        }
                    )
                    if not passed:
                        raise ValueError("real network prerequisite failed")

            def token(key: Any, jti: str, *, env: dict[str, Any] = env) -> str:
                return processor_token(
                    key,
                    issuer=env["FP_JWT_ISSUER"],
                    audience=env["FP_JWT_AUDIENCE"],
                    session_id=jti,
                )

            def check_all(
                check_id: str,
                bearer: str,
                expected: str,
                *,
                before: list[dict[str, Any]] = before,
                release: str = release,
                server_name: str = server_name,
            ) -> None:
                for replica in before:
                    observed = call_processor(release, replica, server_name, bearer)
                    checks.append(
                        {
                            "check_id": check_id,
                            "namespace": release,
                            "timestamp_utc": datetime.datetime.now(
                                datetime.UTC
                            ).isoformat(),
                            "pod_uid": replica["uid"],
                            "observed": observed,
                            "expected": expected,
                            "verdict": grpc_probe_verdict(observed, expected),
                        }
                    )

            stage = f"{release}:revocation"
            jti = secrets.token_hex(16)
            issued = time.monotonic()
            bearer = token(old, jti)
            check_all("unrevoked-accepted", bearer, "InvalidArgument")
            revoke = run_in_pod(
                pods[short + "-fp"],
                REDIS_REVOKE,
                [],
                stdin=json.dumps(
                    {"host": redis_host, "password": passwords[release], "jti": jti}
                ),
                timeout=5,
            )
            if revoke.get("result") != "revoked" or time.monotonic() - issued > 540:
                raise ValueError("revocation precondition failed")
            check_all("revoked-rejected", bearer, "Unauthenticated")
            check_all(
                "unrevoked-control",
                token(old, secrets.token_hex(16)),
                "InvalidArgument",
            )
            refresh = int(env["FP_JWKS_REFRESH_INTERVAL"])
            if not 1 <= refresh <= 300:
                raise ValueError("refresh exceeds existing proof budget")
            stage = f"{release}:unpublished-key"
            new_jti = secrets.token_hex(16)
            new_issued = time.monotonic()
            new_token = token(new, new_jti)
            validate_fixture_token(new, new_token, env, new_jti)
            independent = run_in_pod(
                pods[short + "-fp"],
                REDIS_REVOKE,
                [],
                stdin=json.dumps(
                    {
                        "host": redis_host,
                        "password": passwords[release],
                        "jti": new_jti,
                        "action": "check",
                    }
                ),
                timeout=5,
            )
            if independent.get("result") != "unrevoked":
                raise ValueError("new token revocation precondition failed")
            check_all("unpublished-new-rejected", new_token, "Unauthenticated")
            stage = f"{release}:rotation-overlap"
            publication = datetime.datetime.now(datetime.UTC).isoformat()

            if (
                publish_jwks(pods[short + "-backend"], jwks_document([old, new])).get(
                    "result"
                )
                != "published"
            ):
                raise ValueError("publish failed")
            time.sleep(refresh + 10)
            if time.monotonic() - new_issued > 540:
                raise ValueError("new-key token expiry margin exhausted")
            validate_fixture_token(new, new_token, env, new_jti)
            rotations.append(
                {
                    "namespace": release,
                    "published_utc": publication,
                    "refresh_interval_seconds": refresh,
                    "key_ids": [old.kid, new.kid],
                    "required_observation": "same fresh unrevoked token rejected before publication and accepted by each unchanged replica after refresh",
                }
            )
            check_all(
                "overlap-old-accepted",
                token(old, secrets.token_hex(16)),
                "InvalidArgument",
            )
            check_all(
                "overlap-new-accepted",
                new_token,
                "InvalidArgument",
            )
            stage = f"{release}:rotation-retirement"
            if (
                publish_jwks(pods[short + "-backend"], jwks_document([new])).get(
                    "result"
                )
                != "published"
            ):
                raise ValueError("publish failed")
            time.sleep(refresh + 10)
            # Fresh old-key token rules out expiry as a false retirement pass.
            check_all(
                "retired-old-rejected",
                token(old, secrets.token_hex(16)),
                "Unauthenticated",
            )
            check_all(
                "retirement-new-control",
                token(new, secrets.token_hex(16)),
                "InvalidArgument",
            )
            if replica_state(release, labels) != before:
                raise ValueError("replica restarted during proof")
            # Matrix cross-release checks already finished against the unchanged
            # original targets. Retire only actual phase workloads before the
            # next namespace, bounding peak runtime memory to one real stack.
            stage = f"{release}:cleanup"
            kubectl(
                "-n",
                release,
                "delete",
                "deployment",
                deployment["metadata"]["name"],
                "--cascade=foreground",
                "--wait=true",
                "--timeout=60s",
            )
            kubectl(
                "-n",
                release,
                "delete",
                "pod",
                "netpol-temporal",
                "netpol-postgres",
                "netpol-nats",
                "netpol-grpc-client",
                "--wait=true",
                "--timeout=60s",
            )
            kubectl(
                "-n",
                release,
                "delete",
                "job",
                "netpol-temporal-schema",
                "--wait=true",
                "--timeout=60s",
            )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
        SystemExit,
        yaml.YAMLError,
        InvalidSignature,
        subprocess.SubprocessError,
    ):
        return {"verdict": "inconclusive", "stage": stage, "checks": checks}
    return {
        "verdict": "pass"
        if checks and all(c["verdict"] == "pass" for c in checks)
        else "fail",
        "checks": checks,
        "source_sha": source_sha,
        "tested_deployment": "probe-a/probe-a-file-processor",
        "real_probe_b": "not_run; namespace isolation remains the original 40-row matrix",
        "rotations": rotations,
        "replicas": before,
        "replica_state_unchanged": True,
    }
