"""Private native TLS prerequisite for the existing NetworkPolicy proof runner.

Call bootstrap_temporal inside its disposable namespace/cluster lifecycle. No
receipt writer or policy change lives here. A setup failure MUST abort real-FP
checks as inconclusive; success establishes prerequisites, never audit success.
"""

from __future__ import annotations

import datetime
import ipaddress
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from networkpolicy_runtime_app import (
    _segment,
    b64url,
    generate_signing_key,
    jwks_document,
    sign_rs256,
)
from networkpolicy_runtime_kube import apply_objects, kubectl, run_command

JWKS_SERVER = """import http.server, ssl
from pathlib import Path
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path != '/.well-known/jwks.json':
            self.send_error(404); return
        body = Path('/config/jwks.json').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
server = http.server.HTTPServer(('127.0.0.1', 8443), Handler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.minimum_version = ssl.TLSVersion.TLSv1_3
ctx.load_cert_chain('/issuer/tls.crt', '/issuer/tls.key')
server.socket = ctx.wrap_socket(server.socket, server_side=True)
server.serve_forever()
"""
SAFE_RENDER = """import os, re
from pathlib import Path
os.umask(0o077)
user = os.environ['POSTGRES_USER']
password = os.environ['POSTGRES_PWD']
if not re.fullmatch(r'[a-z_][a-z0-9_]*', user) or not re.fullmatch(r'[0-9a-f]{64}', password):
    raise SystemExit('invalid generated database credential')
text = Path('/config/docker.yaml').read_text()
text = text.replace('${POSTGRES_USER}', user).replace('${POSTGRES_PWD}', password)
text = text.replace('${TEMPORAL_JWKS_URL}', 'https://127.0.0.1:8443/.well-known/jwks.json')
with open('/rendered/docker.yaml', 'x') as handle:
    handle.write(text)
roots = Path('/etc/ssl/certs/ca-certificates.crt').read_bytes()
with open('/rendered/roots.pem', 'xb') as handle:
    handle.write(roots + b'\\n' + Path('/ca/ca.crt').read_bytes())
"""
JWKS_READY = """import ssl, urllib.request
ctx = ssl.create_default_context(cafile='/ca/ca.crt')
with urllib.request.urlopen('https://127.0.0.1:8443/.well-known/jwks.json', context=ctx, timeout=2) as r:
    assert r.status == 200
"""
SCHEMA_INIT = """set -eu
set +x
for database in temporal temporal_visibility; do
  export SQL_DATABASE="$database"
  temporal-sql-tool setup-schema -v 0 >/dev/null 2>&1
  if [ "$database" = temporal ]; then directory=temporal; else directory=visibility; fi
  temporal-sql-tool update-schema -d "/etc/temporal/schema/postgresql/v12/$directory/versioned" >/dev/null 2>&1
done
"""
POSTGRES_INIT = r"""#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres >/dev/null <<'SQL'
\getenv service_password SERVICE_PASSWORD
CREATE ROLE ue_temporal LOGIN PASSWORD :'service_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE temporal OWNER ue_temporal;
CREATE DATABASE temporal_visibility OWNER ue_temporal;
DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ue_temporal' AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN RAISE EXCEPTION 'fixture role is overprivileged'; END IF; END $$;
SQL
"""
NAMESPACE_INIT = """set -eu
set +x
umask 077
profile=$(mktemp /tmp/netpol-profile.XXXXXX)
trap 'rm -f "$profile"' EXIT HUP INT TERM
cat > "$profile"
call() {
 env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp temporal "$@" --config-file "$profile" --address 127.0.0.1:7233 --tls --tls-ca-path /ca/ca.crt --tls-server-name temporal --command-timeout 2s >/dev/null 2>&1
}
for attempt in $(seq 1 24); do
 if call operator cluster health; then break; fi
 if [ "$attempt" = 24 ]; then exit 1; fi
 sleep 3
done
for attempt in $(seq 1 12); do
 if call operator namespace describe --namespace default; then exit 0; fi
 call operator namespace create --namespace default --retention 24h || :
 if call operator namespace describe --namespace default; then exit 0; fi
 sleep 2
done
exit 1
"""


def _certificate(key: Any, ca_key: Any, ca: Any, names: list[Any]) -> str:
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "netpol-fixture")])
        )
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=2))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _key_pem(key: Any) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _credentials(namespace: str) -> tuple[str, dict[str, str], dict[str, str]]:
    now = datetime.datetime.now(datetime.UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "disposable-netpol-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server = {
        "tls.crt": _certificate(
            server_key,
            ca_key,
            ca,
            [x509.DNSName("temporal"), x509.DNSName(f"temporal.{namespace}.svc")],
        ),
        "tls.key": _key_pem(server_key),
    }
    issuer = {
        "tls.crt": _certificate(
            issuer_key, ca_key, ca, [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        ),
        "tls.key": _key_pem(issuer_key),
    }
    # CA signing key is never serialized, mounted, or returned.
    return ca.public_bytes(serialization.Encoding.PEM).decode(), server, issuer


def _token(signer: Any, permission: str, lifetime: int) -> str:
    now = int(time.time())
    header = _segment({"alg": "RS256", "typ": "JWT", "kid": signer.kid})
    payload = _segment(
        {
            "sub": "netpol-temporal",
            "aud": "temporal",
            "iat": now,
            "exp": now + lifetime,
            "permissions": [permission],
        }
    )
    data = f"{header}.{payload}".encode("ascii")
    return f"{header}.{payload}.{b64url(sign_rs256(signer, data))}"


def native_config(root: Path) -> str:
    config = yaml.safe_load((root / "services/temporal/config.yaml").read_text())
    auth = config["global"]["authorization"]
    if auth["authorizer"] != "default" or auth["claimMapper"] != "default":
        raise ValueError("tracked Temporal authentication contract changed")
    for name, service in config["services"].items():
        if name != "frontend" and service["rpc"]["bindOnIP"] != "127.0.0.1":
            raise ValueError("tracked internal Temporal listener is not loopback")
    for store in config["persistence"]["datastores"].values():
        store["sql"]["connectAddr"] = "netpol-postgres:5432"
    config["global"]["tls"] = {
        "frontend": {
            "server": {
                "certFile": "/server/tls.crt",
                "keyFile": "/server/tls.key",
                "requireClientAuth": False,
            },
            "client": {
                "serverName": "temporal",
                "rootCaFiles": ["/ca/ca.crt"],
                "disableHostVerification": False,
            },
        }
    }
    return yaml.safe_dump(config, sort_keys=False)


def _object(kind: str, name: str, namespace: str, **fields: Any) -> dict[str, Any]:
    return {
        "apiVersion": "batch/v1" if kind == "Job" else "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": namespace},
        **fields,
    }


def _mount(name: str, path: str) -> dict[str, Any]:
    return {"name": name, "mountPath": path, "readOnly": True}


def secret_volume(name: str, resource_name: str) -> dict[str, Any]:
    """Reference a Kubernetes Secret resource; never embed credential contents."""
    return {"name": name, "secret": {"secretName": resource_name}}


def _env(name: str, key: str) -> dict[str, Any]:
    return {
        "name": name,
        "valueFrom": {"secretKeyRef": {"name": "netpol-sql", "key": key}},
    }


def compose_image(root: Path, service: str) -> str:
    """Read a scalar image pin without constructing Compose !override tags."""
    document = yaml.compose((root / "docker-compose.full.yml").read_text())

    def field(node: Any, name: str) -> Any:
        matches = [value for key, value in node.value if key.value == name]
        if len(matches) != 1:
            raise ValueError("ambiguous tracked Compose field")
        return matches[0]

    image = field(field(field(document, "services"), service), "image").value
    if not isinstance(image, str) or not re.search(r"@sha256:[0-9a-f]{64}$", image):
        raise ValueError("tracked image is not digest pinned")
    return image


def fixture_objects(
    root: Path, namespace: str, python_image: str, postgres_image: str, signer: Any
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Use tracked pins, no new literal digests. Returned Secrets are PRIVATE."""
    if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", namespace):
        raise ValueError("invalid fixture namespace")
    server_image = compose_image(root, "temporal")
    admin_image = compose_image(root, "temporal-admin-tools")
    for image in (server_image, admin_image, python_image, postgres_image):
        if not re.search(r"@sha256:[0-9a-f]{64}$", image):
            raise ValueError("fixture images must use existing pinned digests")
    # Caller may only reuse these tracked pins, not substitute another digest.
    tracked_python = re.findall(
        r"^FROM (python:\S+@sha256:[0-9a-f]{64}) AS runtime[ \t]*$",
        (root / "backend.Dockerfile").read_text(),
        re.MULTILINE,
    )
    values = yaml.safe_load(
        (root / "charts/university-ecosystem/values.yaml").read_text()
    )
    if (
        tracked_python != [python_image]
        or values["backup"]["postgresImage"] != postgres_image
    ):
        raise ValueError("fixture image does not match the tracked runtime pin")
    ca, server, issuer = _credentials(namespace)
    objects = [
        _object(
            "Secret",
            "netpol-postgres-bootstrap",
            namespace,
            stringData={"password": secrets.token_hex(32)},
        ),
        _object(
            "Secret",
            "netpol-sql",
            namespace,
            stringData={"username": "ue_temporal", "password": secrets.token_hex(32)},
        ),
        _object("Secret", "netpol-temporal-tls", namespace, stringData=server),
        _object("Secret", "netpol-issuer-tls", namespace, stringData=issuer),
        _object("ConfigMap", "netpol-temporal-ca", namespace, data={"ca.crt": ca}),
        _object(
            "ConfigMap",
            "netpol-temporal-config",
            namespace,
            data={
                "docker.yaml": native_config(root),
                "jwks.json": jwks_document([signer]),
                "issuer.py": JWKS_SERVER,
                "render.py": SAFE_RENDER,
            },
        ),
        _object(
            "ConfigMap",
            "netpol-postgres-init",
            namespace,
            data={"init.sh": POSTGRES_INIT},
        ),
    ]
    pg = _object(
        "Pod",
        "netpol-postgres",
        namespace,
        spec={
            "automountServiceAccountToken": False,
            "containers": [
                {
                    "name": "postgres",
                    "image": postgres_image,
                    "env": [
                        {"name": "POSTGRES_USER", "value": "postgres"},
                        {
                            "name": "POSTGRES_PASSWORD",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "netpol-postgres-bootstrap",
                                    "key": "password",
                                }
                            },
                        },
                        _env("SERVICE_PASSWORD", "password"),
                        {"name": "POSTGRES_DB", "value": "postgres"},
                    ],
                    "volumeMounts": [
                        {"name": "data", "mountPath": "/var/lib/postgresql/data"},
                        _mount("init", "/docker-entrypoint-initdb.d"),
                    ],
                    "readinessProbe": {
                        "exec": {
                            "command": [
                                "sh",
                                "-ec",
                                'PGPASSWORD="$SERVICE_PASSWORD" psql -h 127.0.0.1 -U ue_temporal -d temporal_visibility -c "SELECT 1" >/dev/null 2>&1',
                            ]
                        },
                        "periodSeconds": 3,
                        "timeoutSeconds": 2,
                    },
                },
            ],
            "volumes": [
                {"name": "data", "emptyDir": {}},
                {"name": "init", "configMap": {"name": "netpol-postgres-init"}},
            ],
        },
    )
    pg["metadata"]["labels"] = {"netpol-fixture": "postgres"}
    objects.extend(
        [
            pg,
            _object(
                "Service",
                "netpol-postgres",
                namespace,
                spec={
                    "selector": {"netpol-fixture": "postgres"},
                    "ports": [{"port": 5432}],
                },
            ),
        ]
    )
    schema = _object(
        "Job",
        "netpol-temporal-schema",
        namespace,
        spec={
            "backoffLimit": 0,
            "activeDeadlineSeconds": 180,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "containers": [
                        {
                            "name": "schema",
                            "image": admin_image,
                            "command": ["sh", "-ec", SCHEMA_INIT],
                            "env": [
                                _env("SQL_USER", "username"),
                                _env("SQL_PASSWORD", "password"),
                                {"name": "SQL_HOST", "value": "netpol-postgres"},
                                {"name": "SQL_PORT", "value": "5432"},
                                {"name": "SQL_PLUGIN", "value": "postgres12"},
                            ],
                        }
                    ],
                },
            },
        },
    )
    mounts = [_mount("config", "/config"), _mount("ca", "/ca")]
    pod = _object(
        "Pod",
        "netpol-temporal",
        namespace,
        spec={
            "automountServiceAccountToken": False,
            "securityContext": {"runAsUser": 1000, "runAsGroup": 1000, "fsGroup": 1000},
            "initContainers": [
                {
                    "name": "jwks",
                    "restartPolicy": "Always",
                    "image": python_image,
                    "command": ["python3", "-I", "/config/issuer.py"],
                    "volumeMounts": [*mounts, _mount("issuer", "/issuer")],
                    "startupProbe": {
                        "exec": {"command": ["python3", "-I", "-c", JWKS_READY]},
                        "periodSeconds": 2,
                        "failureThreshold": 30,
                        "timeoutSeconds": 3,
                    },
                },
                {
                    "name": "render",
                    "image": python_image,
                    "command": ["python3", "-I", "/config/render.py"],
                    "env": [
                        _env("POSTGRES_USER", "username"),
                        _env("POSTGRES_PWD", "password"),
                    ],
                    "volumeMounts": [
                        *mounts,
                        {"name": "rendered", "mountPath": "/rendered"},
                    ],
                },
            ],
            "containers": [
                {
                    "name": "temporal",
                    "image": server_image,
                    "command": [
                        "temporal-server",
                        "--root",
                        "/rendered",
                        "--config",
                        ".",
                        "--env",
                        "docker",
                        "start",
                    ],
                    "env": [
                        {"name": "SSL_CERT_FILE", "value": "/rendered/roots.pem"},
                        {
                            "name": "TEMPORAL_JWKS_URL",
                            "value": "https://127.0.0.1:8443/.well-known/jwks.json",
                        },
                        {"name": "TEMPORAL_JWKS_CA_FILE", "value": "/ca/ca.crt"},
                        {
                            "name": "TEMPORAL_SERVICES",
                            "value": "frontend,history,matching,worker,internal-frontend",
                        },
                    ],
                    "volumeMounts": [
                        *mounts,
                        _mount("server", "/server"),
                        _mount("rendered", "/rendered"),
                        _mount("config", "/etc/temporal/config"),
                    ],
                },
                {
                    "name": "admin",
                    "image": admin_image,
                    "command": ["sleep", "infinity"],
                    "volumeMounts": [_mount("ca", "/ca")],
                },
            ],
            "volumes": [
                {"name": "rendered", "emptyDir": {"medium": "Memory"}},
                {"name": "config", "configMap": {"name": "netpol-temporal-config"}},
                {"name": "ca", "configMap": {"name": "netpol-temporal-ca"}},
                secret_volume("server", "netpol-temporal-tls"),
                secret_volume("issuer", "netpol-issuer-tls"),
            ],
        },
    )
    pod["metadata"]["labels"] = {
        "app.kubernetes.io/name": "temporal",
        "netpol-fixture": "temporal",
    }
    objects.append(
        _object(
            "Service",
            "temporal",
            namespace,
            spec={
                "selector": {"netpol-fixture": "temporal"},
                "ports": [{"port": 7233}],
            },
        )
    )
    return objects, schema, pod


def bootstrap_temporal(
    root: Path, namespace: str, python_image: str, postgres_image: str
) -> dict[str, str]:
    """Apply to EXISTING disposable namespace. Return only nonsecret setup facts.

    Caller's existing EXIT trap owns cluster deletion, including failed setup.
    Never serialize returned manifests, exception output, pod logs, or Secrets
    into artifacts. No retry changes authentication or namespace/policy scope.
    """
    stage = "render"
    try:
        signer = generate_signing_key("netpol-temporal")
        objects, schema, pod = fixture_objects(
            root, namespace, python_image, postgres_image, signer
        )
        stage = "postgres"
        apply_objects(objects)
        kubectl(
            "-n",
            namespace,
            "wait",
            "--for=condition=Ready",
            "pod/netpol-postgres",
            "--timeout=120s",
        )
        stage = "schema"
        apply_objects([schema])
        kubectl(
            "-n",
            namespace,
            "wait",
            "--for=condition=Complete",
            "job/netpol-temporal-schema",
            "--timeout=180s",
        )
        stage = "temporal"
        apply_objects([pod])
        kubectl(
            "-n",
            namespace,
            "wait",
            "--for=condition=Ready",
            "pod/netpol-temporal",
            "--timeout=180s",
        )
        stage = "namespace"
        token = _token(signer, "default:admin", 300)
        profile = f"[profile.default]\napi_key = '{token}'\n"
        run_command(
            [
                "kubectl",
                "-n",
                namespace,
                "exec",
                "-i",
                "netpol-temporal",
                "-c",
                "admin",
                "--",
                "sh",
                "-ec",
                NAMESPACE_INIT,
            ],
            stdin=profile,
            timeout=240,
        )
        # Worker credential is minted after readiness, never inherited from admin.
        stage = "worker-credential"
        worker = _object(
            "Secret",
            "netpol-temporal-worker",
            namespace,
            stringData={"token": _token(signer, "default:write", 3600)},
        )
        apply_objects([worker])
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        SystemExit,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ):
        # CalledProcessError may contain serialized Secrets in stdout/stderr.
        # Do not propagate, print, chain, or return the exception object.
        return {"result": "inconclusive", "stage": stage}
    return {
        "result": "ready",
        "endpoint": "temporal:7233",
        "ca_configmap": "netpol-temporal-ca",
        "worker_secret": worker["metadata"]["name"],
    }


def wire_processor_temporal(deployment: dict[str, Any], setup: dict[str, str]) -> None:
    """Wire only a private real_processor_deployment result after successful setup.

    No mutation of the chart/source or its original rendered resource is allowed.
    Existing JWT/mTLS/revocation Secrets are untouched; only the Temporal token
    file points at this fixture's least-privileged, short-lived worker token.
    """
    if setup.get("result") != "ready":
        raise ValueError("Temporal setup is inconclusive")
    spec = deployment["spec"]["template"]["spec"]
    processor = next(c for c in spec["containers"] if c["name"] == "file-processor")
    env = {entry["name"]: entry for entry in processor["env"]}
    if env["FP_TEMPORAL_TLS_DISABLED"]["value"] != "false":
        raise ValueError("staging Temporal TLS must remain enabled")
    env["FP_TEMPORAL_HOST"]["value"] = setup["endpoint"]
    env["FP_TEMPORAL_API_KEY_FILE"]["value"] = "/run/netpol-temporal/token"
    spec["volumes"].append(
        {
            "name": "netpol-temporal-worker",
            "secret": {"secretName": setup["worker_secret"]},
        }
    )
    processor["volumeMounts"].append(
        _mount("netpol-temporal-worker", "/run/netpol-temporal")
    )
