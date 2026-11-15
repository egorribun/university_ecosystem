"""Prepared real-process slice of the existing NetworkPolicy harness.

No cluster actions occur here. The caller must supply locally built source-bound
images and pre-provisioned staging TLS dependencies. The existing runner, matrix,
collectors and receipt remain authoritative; these helpers do not accept audits.
"""

from __future__ import annotations

import copy
import json
import re
import time
from typing import Any

from networkpolicy_runtime_app import SigningKey, _segment, b64url, sign_rs256
from networkpolicy_runtime_kube import find


def processor_token(
    signer: SigningKey,
    *,
    issuer: str,
    audience: str,
    session_id: str,
    subject: str = "networkpolicy-probe",
    now: int | None = None,
) -> str:
    """Mint a short-lived, full-claim token for the real FP, never for a real user."""
    if not all((issuer, audience, session_id, subject)):
        raise ValueError("all probe token identity fields must be nonempty")
    issued = int(time.time()) if now is None else now
    header = _segment({"alg": "RS256", "kid": signer.kid, "typ": "JWT"})
    payload = _segment(
        {
            "iss": issuer,
            "aud": audience,
            "sub": subject,
            "jti": session_id,
            "is_active": True,
            "iat": issued,
            "exp": issued + 600,
        }
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    return f"{header}.{payload}.{b64url(sign_rs256(signer, signing_input))}"


def real_processor_deployment(
    resources: list[dict[str, Any]],
    release: str,
    *,
    image: str,
    diagnostic_image: str,
    source_sha: str,
    temporal_endpoint: str,
    temporal_ca_configmap: str,
) -> dict[str, Any]:
    """Preserve rendered staging workload/mTLS/Secret refs; add same-pod diagnostics.

    Dependency TLS is a required input, not bypassed via a development profile.
    The CA ConfigMap contains only the public certificate. Secret values are not
    accepted by this helper and must be generated privately by the existing runner.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source SHA must be full length")
    if not all((image, diagnostic_image, temporal_endpoint, temporal_ca_configmap)):
        raise ValueError("source-bound images and staging Temporal TLS inputs required")
    if not image.endswith(":" + source_sha) or not diagnostic_image.endswith(
        ":" + source_sha
    ):
        raise ValueError("local probe images must be tagged with the exact source SHA")
    deployment = copy.deepcopy(
        find(resources, "Deployment", f"{release}-file-processor")
    )
    spec = deployment["spec"]["template"]["spec"]
    containers = spec["containers"]
    processor = next(c for c in containers if c["name"] == "file-processor")
    env = {item["name"]: item for item in processor["env"]}
    required = {
        "FP_ENVIRONMENT": "staging",
        "FP_TEMPORAL_TLS_DISABLED": "false",
        "FP_MINIO_SECURE": "true",
        "FP_OTLP_INSECURE": "false",
    }
    if any(
        str(env.get(key, {}).get("value", "")).lower() != value
        for key, value in required.items()
    ):
        raise ValueError("rendered staging transport requirements were weakened")
    for key in (
        "FP_GRPC_TLS_CERT_FILE",
        "FP_GRPC_TLS_KEY_FILE",
        "FP_GRPC_CLIENT_CA_FILE",
        "FP_GRPC_ALLOWED_CLIENT_URIS",
        "FP_REVOCATION_REDIS_URL_FILE",
        "FP_JWKS_URL",
    ):
        if not env.get(key, {}).get("value"):
            raise ValueError("rendered staging auth or mTLS input missing")
    processor["image"] = image
    processor["imagePullPolicy"] = "Never"
    env["FP_TEMPORAL_HOST"]["value"] = temporal_endpoint
    # Do not silently shorten the chart's refresh interval. Tests must wait the
    # rendered bound, unless a separately recorded fixture override is agreed.
    processor["env"].append({"name": "SSL_CERT_FILE", "value": "/run/probe-ca/ca.crt"})
    spec.setdefault("volumes", []).append(
        {"name": "probe-temporal-ca", "configMap": {"name": temporal_ca_configmap}}
    )
    processor.setdefault("volumeMounts", []).append(
        {"name": "probe-temporal-ca", "mountPath": "/run/probe-ca", "readOnly": True}
    )
    containers.append(
        {
            "name": "probe",
            "image": diagnostic_image,
            "imagePullPolicy": "Never",
            "command": ["sleep", "infinity"],
            "securityContext": {
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
            },
        }
    )
    deployment["spec"]["template"]["metadata"].setdefault("annotations", {})[
        "university-ecosystem.io/source-sha"
    ] = source_sha
    return deployment


def grpc_probe_input(
    *,
    address: str,
    server_name: str,
    token: str,
    ca_file: str,
    certificate_file: str,
    key_file: str,
) -> str:
    """Private stdin payload. Never write this string into receipt/logs/argv."""
    return json.dumps(
        {
            "address": address,
            "server_name": server_name,
            "token": token,
            "ca_file": ca_file,
            "certificate_file": certificate_file,
            "key_file": key_file,
        },
        separators=(",", ":"),
    )


def grpc_probe_verdict(observed: dict[str, Any], expected: str) -> str:
    """Transport/setup failures cannot masquerade as authentication rejection."""
    if expected not in {"InvalidArgument", "Unauthenticated"}:
        raise ValueError("unsupported authentication proof status")
    if observed.get("result") != "grpc-status":
        return "inconclusive"
    code = observed.get("code")
    if code in {
        "Unavailable",
        "DeadlineExceeded",
        "Unknown",
        "Internal",
        "Canceled",
    } or not isinstance(code, str):
        return "inconclusive"
    return "pass" if code == expected else "fail"
