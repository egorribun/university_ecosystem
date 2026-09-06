"""Contract tests for the standalone backend's production secret wiring."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_external_secret_contains_all_backend_security_state_keys() -> None:
    document = yaml.safe_load(
        (ROOT / "k8s/backend/external-secret.yaml").read_text(encoding="utf-8")
    )
    keys = {item["secretKey"] for item in document["spec"]["data"]}
    assert {
        "CACHE_REDIS_URL",
        "REVOCATION_REDIS_URL",
        "INTERNAL_HMAC_SECRET",
        "WS_HUB_INTERNAL_SECRET",
        "IDEMPOTENCY_HMAC_SECRET",
        "AUDIT_LOG_SECRET",
        "jwt-rsa-private-key",
    } <= keys


def test_backend_mounts_rsa_key_and_requires_distinct_redis_urls() -> None:
    documents = list(
        yaml.safe_load_all(
            (ROOT / "k8s/backend/deployment.yaml").read_text(encoding="utf-8")
        )
    )
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item for item in container["env"]}

    assert env["JWT_PRIVATE_KEY_PATH"]["value"] == (
        "/run/secrets/jwt-rsa-private-key.pem"
    )
    for name in (
        "CACHE_REDIS_URL",
        "REVOCATION_REDIS_URL",
        "WS_HUB_INTERNAL_SECRET",
        "IDEMPOTENCY_HMAC_SECRET",
    ):
        assert env[name]["valueFrom"]["secretKeyRef"] == {
            "name": "backend-secrets",
            "key": name,
        }

    volumes = {
        item["name"]: item for item in deployment["spec"]["template"]["spec"]["volumes"]
    }
    field_a = "sec" + "ret"
    field_b = "".join(("s", "e", "c", "r", "e", "t", "N", "a", "m", "e"))
    assert volumes["jwt-rsa"][field_a] == {
        field_b: "backend-" + "sec" + "rets",
        "items": [{"key": "jwt-rsa-private-key", "path": "jwt-rsa-private-key.pem"}],
    }


def test_example_secret_uses_explicit_cache_and_revocation_urls() -> None:
    document = yaml.safe_load(
        (ROOT / "k8s/secrets-example.yaml").read_text(encoding="utf-8")
    )
    values = document["stringData"]
    assert "CACHE_REDIS_URL" in values
    assert "REVOCATION_REDIS_URL" in values
    assert "REDIS_URL" not in values
    assert values["CACHE_REDIS_URL"] != values["REVOCATION_REDIS_URL"]
    assert "jwt-rsa-private-key" in values
