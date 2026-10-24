"""AUD-493: preserve the canonical 40-hex release contract at both Helm gates.

Schema bypass below is test-only boundary isolation, not a deployment mode.
SHA-256 Git release support is not part of the current release contract.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

import pytest
from jsonschema import Draft7Validator

from tests.test_helm_staging_contract import (
    CHART,
    _component_resource,
    _render_staging,
    _values,
)
from tests.test_mfa_helm_contract import _render

RELEASE_SHA = "0123456789abcdef" * 2 + "01234567"


@pytest.fixture(scope="module")
def values_validator() -> Draft7Validator:
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def _cwv_values(release_sha: object) -> dict[str, Any]:
    return {"cwv": {**_values(CHART / "values.yaml")["cwv"], "releaseSHA": release_sha}}


@pytest.mark.parametrize("release_sha", [RELEASE_SHA, "REQUIRED_GIT_SHA"])
def test_schema_preserves_current_release_identity_and_placeholder(
    values_validator: Draft7Validator, release_sha: str
) -> None:
    values_validator.validate(_cwv_values(release_sha))


@pytest.mark.parametrize(
    "release_sha",
    [
        pytest.param("", id="empty"),
        pytest.param("a" * 39, id="short"),
        pytest.param("a" * 41, id="long"),
        pytest.param("a" * 63, id="63-hex"),
        pytest.param("a" * 64, id="unsupported-64-hex"),
        pytest.param("a" * 65, id="65-hex"),
        pytest.param("A" * 40, id="uppercase"),
        pytest.param("a" * 39 + "g", id="non-hex"),
        pytest.param(" " + "a" * 40, id="leading-whitespace"),
        pytest.param("a" * 40 + " ", id="trailing-whitespace"),
        pytest.param("sha256:" + "a" * 64, id="image-digest"),
        pytest.param("REQUIRED_GIT_SHA_extra", id="placeholder-suffix"),
        pytest.param(None, id="null"),
        pytest.param(123, id="integer"),
    ],
)
def test_schema_rejects_unsupported_release_identities(
    values_validator: Draft7Validator, release_sha: object
) -> None:
    errors = list(values_validator.iter_errors(_cwv_values(release_sha)))

    assert errors
    assert all(list(error.absolute_path) == ["cwv", "releaseSHA"] for error in errors)


@pytest.fixture(params=["staging", "production"])
def release_environment(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture(params=[False, True], ids=["ordinary-schema", "template-only"])
def isolate_template(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


def _render_release(
    environment: str,
    image_tag: str,
    release_sha: str,
    *,
    isolate_template: bool,
) -> list[dict[str, Any]]:
    assert shutil.which("helm") is not None, "Actual Helm rendering is required"
    args = [
        "--set-string",
        f"global.environment={environment}",
        "--set-string",
        f"global.imageTag={image_tag}",
        "--set-string",
        f"cwv.releaseSHA={release_sha}",
    ]
    if environment == "production":
        args.extend(
            (
                "--set-string",
                "ingress.issuer.kind=ClusterIssuer",
                "--set-string",
                "ingress.issuer.name=letsencrypt-prod",
                "--set",
                "cwv.rumEnabled=false",
                "--set",
                "cwv.exportOIDC.enabled=false",
            )
        )
    if isolate_template:
        # Exercise the independent template guard without the schema masking it.
        args.append("--skip-schema-validation")
    return _render_staging(*args, release_name="release-sha-contract")


def test_release_renders_matching_40_hex_identity(
    release_environment: str, isolate_template: bool
) -> None:
    resources = _render_release(
        release_environment,
        RELEASE_SHA,
        RELEASE_SHA,
        isolate_template=isolate_template,
    )
    backend = _component_resource(resources, "Deployment", "backend")
    pod = backend["spec"]["template"]
    env = {entry["name"]: entry for entry in pod["spec"]["containers"][0]["env"]}

    assert env["CWV_RELEASE_SHA"]["value"] == RELEASE_SHA
    assert pod["metadata"]["annotations"]["university-ecosystem.io/source-sha"] == (
        RELEASE_SHA
    )


@pytest.mark.parametrize(
    "release_sha",
    [
        pytest.param("a" * 64, id="unsupported-64-hex"),
        pytest.param("mutable-tag", id="malformed"),
    ],
)
def test_release_rejects_unsupported_sha_at_each_validation_boundary(
    release_environment: str, isolate_template: bool, release_sha: str
) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_release(
            release_environment,
            release_sha,
            release_sha,
            isolate_template=isolate_template,
        )

    assert error.value.returncode == 1
    if isolate_template:
        assert "global.imageTag must be" in error.value.stderr
    else:
        assert "cwv" in error.value.stderr and "releaseSHA" in error.value.stderr


def test_release_rejects_unresolved_placeholder(
    release_environment: str, isolate_template: bool
) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_release(
            release_environment,
            "REQUIRED_GIT_SHA",
            "REQUIRED_GIT_SHA",
            isolate_template=isolate_template,
        )

    assert error.value.returncode == 1
    assert "unresolved REQUIRED_ marker" in error.value.stderr


def test_release_rejects_mismatched_valid_40_hex_identities(
    release_environment: str, isolate_template: bool
) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_release(
            release_environment,
            RELEASE_SHA,
            "b" * 40,
            isolate_template=isolate_template,
        )

    assert error.value.returncode == 1
    assert "cwv.releaseSHA must exactly equal global.imageTag" in error.value.stderr


def test_development_preserves_schema_placeholder_without_release_gate() -> None:
    assert shutil.which("helm") is not None, "Actual Helm rendering is required"
    resources = _render("--set-string", "cwv.releaseSHA=REQUIRED_GIT_SHA")
    backend = _component_resource(resources, "Deployment", "backend")
    env = {
        entry["name"]: entry
        for entry in backend["spec"]["template"]["spec"]["containers"][0]["env"]
    }

    assert env["CWV_RUM_ENABLED"]["value"] == "false"
    assert env["CWV_RELEASE_SHA"]["value"] == "REQUIRED_GIT_SHA"
