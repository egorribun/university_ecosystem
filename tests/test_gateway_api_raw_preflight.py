"""Contracts for the read-only Envoy Gateway raw-manifest preflight."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
BASH = shutil.which("bash") if os.name != "nt" else None
HELM = shutil.which("helm")
POSIX_BASH_AVAILABLE = BASH is not None
CUSTOM_GATEWAY_CLASS_NAME = "envoy-gateway-contract"
GATEWAY_API_VERSIONS = (
    "gateway.networking.k8s.io/v1/Gateway",
    "gateway.networking.k8s.io/v1/HTTPRoute",
    "gateway.envoyproxy.io/v1alpha1/ClientTrafficPolicy",
    "gateway.envoyproxy.io/v1alpha1/BackendTrafficPolicy",
    "cert-manager.io/v1/Certificate",
)


def _fake_kubectl_bin(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "gatewayclass.yaml"
    (bin_dir / "envsubst").write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "value = sys.stdin.read()\n"
        "value = value.replace('${GATEWAY_CLASS_NAME}', os.environ.get('GATEWAY_CLASS_NAME', ''))\n"
        "sys.stdout.write(value)\n",
        encoding="utf-8",
    )
    (bin_dir / "kubectl").write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['KUBECTL_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write(' '.join(args) + '\\n')\n"
        "if args[:1] == ['version']:\n"
        "    print(os.environ.get('KUBE_VERSION', '1.34'))\n"
        "elif args[:2] == ['get', 'crd']:\n"
        "    name = args[2]\n"
        "    template = args[-1]\n"
        "    if 'bundle-version' in template:\n"
        "        bundle_env = {'gatewayclasses.gateway.networking.k8s.io': 'GATEWAYCLASS_BUNDLE', 'gateways.gateway.networking.k8s.io': 'GATEWAY_BUNDLE', 'httproutes.gateway.networking.k8s.io': 'HTTPROUTE_BUNDLE'}.get(name, 'GATEWAY_BUNDLE')\n"
        "        channel_env = {'gatewayclasses.gateway.networking.k8s.io': 'GATEWAYCLASS_CHANNEL', 'gateways.gateway.networking.k8s.io': 'GATEWAY_CHANNEL', 'httproutes.gateway.networking.k8s.io': 'HTTPROUTE_CHANNEL'}.get(name, 'GATEWAY_CHANNEL')\n"
        "        print(os.environ.get(bundle_env, 'v1.6.1') + '|' + os.environ.get(channel_env, 'standard'))\n"
        "    elif name == 'clienttrafficpolicies.gateway.envoyproxy.io':\n"
        "        print(os.environ.get('ENVOY_POLICY_CRD_VERSIONS', 'v1alpha1'))\n"
        "    elif name == 'backendtrafficpolicies.gateway.envoyproxy.io':\n"
        "        if os.environ.get('BACKEND_POLICY_CRD_MISSING') == '1':\n"
        "            raise SystemExit(1)\n"
        "        print(os.environ.get('BACKEND_POLICY_CRD_VERSIONS', 'v1alpha1'))\n"
        "    else:\n"
        "        print(os.environ.get('GATEWAY_CRD_VERSIONS', 'v1'))\n"
        "elif args[:2] == ['get', 'deployment']:\n"
        "    print(os.environ.get('ENVOY_GATEWAY_VERSION', 'v1.9.2'))\n"
        "elif args[:2] == ['get', 'gatewayclass']:\n"
        "    if os.environ.get('GATEWAYCLASS_LOOKUP_ERROR') == '1':\n"
        "        raise SystemExit(1)\n"
        "    controller = os.environ.get('EXISTING_CONTROLLER', '')\n"
        "    if not controller:\n"
        "        raise SystemExit(0)\n"
        "    if args[-1] == 'name':\n"
        "        print('GatewayClass/' + args[2])\n"
        "    else:\n"
        "        print(controller)\n"
        "elif args[:2] == ['create', '-f']:\n"
        "    pathlib.Path(os.environ['KUBECTL_CAPTURE']).write_text(sys.stdin.read(), encoding='utf-8')\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )
    for executable in (bin_dir / "envsubst", bin_dir / "kubectl"):
        executable.chmod(0o755)
    return bin_dir, capture


def _run_gatewayclass_wrapper(
    tmp_path: Path, *, overrides: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    assert BASH is not None, "POSIX shell tests must be marked at collection"

    bin_dir, capture = _fake_kubectl_bin(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(bin_dir), environment["PATH"])),
            "KUBECTL_LOG": str(tmp_path / "kubectl.log"),
            "KUBECTL_CAPTURE": str(capture),
            "GATEWAY_CLASS_NAME": "eg",
        }
    )
    if overrides:
        environment.update(overrides)
    result = subprocess.run(  # noqa: S603 - fixed local wrapper and test-only tools
        [
            BASH,
            str(ROOT / "scripts/apply_raw_k8s.sh"),
            "k8s/gateway-api/gatewayclass.yaml",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, capture, Path(environment["KUBECTL_LOG"])


def _render_gateway_api_template(tmp_path: Path, class_name: str) -> str:
    assert HELM is not None, "Helm-dependent tests must be marked at collection"

    chart = tmp_path / "chart"
    templates = chart / "templates"
    templates.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: university-ecosystem\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    for filename in ("values.yaml", "values.schema.json"):
        shutil.copy2(CHART / filename, chart / filename)
    for filename in ("_helpers.tpl", "gateway-api.yaml", "ingress.yaml"):
        shutil.copy2(CHART / "templates" / filename, templates / filename)

    command = [
        HELM,
        "template",
        "raw-connectivity-contract",
        str(chart),
        "--namespace",
        "university-ecosystem",
        "--set-string",
        "applicationSecrets.existingSecret=raw-connectivity-existing-secret",
        "--set",
        "gatewayApi.enabled=true",
        "--set",
        "ingress.enabled=false",
        "--set-string",
        f"gatewayApi.gatewayClassName={class_name}",
    ]
    for api_version in GATEWAY_API_VERSIONS:
        command.extend(("--api-versions", api_version))
    result = subprocess.run(  # noqa: S603 - fixed local Helm template contract
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_raw_gatewayclass_is_an_allowlisted_cluster_scoped_bootstrap() -> None:
    wrapper = (ROOT / "scripts/apply_raw_k8s.sh").read_text(encoding="utf-8")
    manifest_path = ROOT / "k8s/gateway-api/gatewayclass.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert "k8s/gateway-api/gatewayclass.yaml)" in wrapper
    assert "check_gateway_api_prerequisites.sh" in wrapper
    assert manifest["apiVersion"] == "gateway.networking.k8s.io/v1"
    assert manifest["kind"] == "GatewayClass"
    assert "namespace" not in manifest["metadata"]
    assert manifest["metadata"]["name"] == "${GATEWAY_CLASS_NAME}"
    assert manifest["spec"]["controllerName"] == (
        "gateway.envoyproxy.io/gatewayclass-controller"
    )
    assert (
        manifest["metadata"]["annotations"]["university-ecosystem.dev/managed-by"]
        == "apply_raw_k8s.sh"
    )
    assert "kubectl create -f -" in wrapper


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_raw_gatewayclass_connects_to_gateway_and_its_http_routes(
    tmp_path: Path,
) -> None:
    class_name = CUSTOM_GATEWAY_CLASS_NAME
    manifest_text = (ROOT / "k8s/gateway-api/gatewayclass.yaml").read_text(
        encoding="utf-8"
    )
    bootstrap = yaml.safe_load(
        manifest_text.replace("${GATEWAY_CLASS_NAME}", class_name)
    )
    resources = [
        resource
        for resource in yaml.safe_load_all(
            _render_gateway_api_template(tmp_path, class_name)
        )
        if isinstance(resource, dict)
    ]
    gateway = next(
        resource for resource in resources if resource.get("kind") == "Gateway"
    )
    routes = [resource for resource in resources if resource.get("kind") == "HTTPRoute"]

    assert bootstrap["metadata"]["name"] == gateway["spec"]["gatewayClassName"]
    assert routes
    listener_names = {listener["name"] for listener in gateway["spec"]["listeners"]}
    for route in routes:
        for parent in route["spec"]["parentRefs"]:
            assert parent["name"] == gateway["metadata"]["name"]
            assert parent["sectionName"] in listener_names
    assert not any(resource.get("kind") == "Ingress" for resource in resources)


def test_gateway_api_preflight_is_read_only_and_version_pinned() -> None:
    source = (ROOT / "scripts/check_gateway_api_prerequisites.sh").read_text(
        encoding="utf-8"
    )

    assert "1.33|1.34|1.35|1.36" in source
    assert '"v1.6.1|standard"' in source
    assert '"v1.9.2"' in source
    for crd in (
        "gatewayclasses.gateway.networking.k8s.io",
        "gateways.gateway.networking.k8s.io",
        "httproutes.gateway.networking.k8s.io",
    ):
        assert f"require_gateway_api_bundle {crd}" in source
    assert "gatewayclasses.gateway.networking.k8s.io v1" in source
    assert "gateways.gateway.networking.k8s.io v1" in source
    assert "httproutes.gateway.networking.k8s.io v1" in source
    assert "clienttrafficpolicies.gateway.envoyproxy.io v1alpha1" in source
    assert "backendtrafficpolicies.gateway.envoyproxy.io v1alpha1" in source
    assert "certificates.cert-manager.io v1" in source
    chart_template = (
        ROOT / "charts/university-ecosystem/templates/gateway-api.yaml"
    ).read_text(encoding="utf-8")
    assert (
        "apiVersion: gateway.envoyproxy.io/v1alpha1\nkind: ClientTrafficPolicy"
        in chart_template
    )
    assert (
        "apiVersion: gateway.envoyproxy.io/v1alpha1\nkind: BackendTrafficPolicy"
        in chart_template
    )
    assert "kubectl apply" not in source
    assert "kubectl create" not in source
    assert "kubectl delete" not in source


def test_gateway_api_raw_path_is_documented_as_single_resource_bootstrap() -> None:
    readme = (ROOT / "k8s/README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split()).lower()

    assert "gatewayclass bootstrap" in normalized
    assert (
        "do not install, update, or delete crds, controllers, or other cluster resources"
        in normalized
    )
    assert "gateway_class_name=eg" in normalized
    assert "envoy gateway v1.9.2" in normalized
    assert "gateway api standard bundle v1.6.1" in normalized
    assert "--set crds.gatewayapi.channel=standard" in normalized
    assert "--set crds.enabled=false" in normalized
    assert "do not install a second gateway api bundle" in normalized


@pytest.mark.skipif(not POSIX_BASH_AVAILABLE, reason="requires a POSIX shell and bash")
def test_gatewayclass_wrapper_preflights_versions_before_create(tmp_path: Path) -> None:
    class_name = CUSTOM_GATEWAY_CLASS_NAME
    result, capture, log_path = _run_gatewayclass_wrapper(
        tmp_path, overrides={"GATEWAY_CLASS_NAME": class_name}
    )

    assert result.returncode == 0, result.stderr
    created = yaml.safe_load(capture.read_text(encoding="utf-8"))
    assert created["kind"] == "GatewayClass"
    assert created["metadata"]["name"] == class_name

    calls = log_path.read_text(encoding="utf-8").splitlines()
    create_at = next(
        index for index, call in enumerate(calls) if call.startswith("create ")
    )
    assert any(call.startswith("version ") for call in calls[:create_at])
    assert any(
        "gatewayclasses.gateway.networking.k8s.io" in call for call in calls[:create_at]
    )
    assert any(
        "gateways.gateway.networking.k8s.io" in call for call in calls[:create_at]
    )
    assert any(
        "httproutes.gateway.networking.k8s.io" in call for call in calls[:create_at]
    )
    assert any(
        "clienttrafficpolicies.gateway.envoyproxy.io" in call
        for call in calls[:create_at]
    )
    assert any(
        "backendtrafficpolicies.gateway.envoyproxy.io" in call
        for call in calls[:create_at]
    )
    assert any("certificates.cert-manager.io" in call for call in calls[:create_at])
    assert any(
        call.startswith("get deployment envoy-gateway") for call in calls[:create_at]
    )


@pytest.mark.skipif(not POSIX_BASH_AVAILABLE, reason="requires a POSIX shell and bash")
def test_gatewayclass_wrapper_rejects_symlinked_manifest_parent(
    tmp_path: Path,
) -> None:
    assert BASH is not None

    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    k8s = repo / "k8s"
    outside = tmp_path / "outside"
    scripts.mkdir(parents=True)
    k8s.mkdir()
    outside.mkdir()
    shutil.copy2(ROOT / "scripts/apply_raw_k8s.sh", scripts / "apply_raw_k8s.sh")
    shutil.copy2(
        ROOT / "scripts/check_gateway_api_prerequisites.sh",
        scripts / "check_gateway_api_prerequisites.sh",
    )
    shutil.copy2(
        ROOT / "k8s/gateway-api/gatewayclass.yaml", outside / "gatewayclass.yaml"
    )
    (k8s / "gateway-api").symlink_to(outside, target_is_directory=True)

    bin_dir, capture = _fake_kubectl_bin(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": os.pathsep.join((str(bin_dir), environment["PATH"])),
            "KUBECTL_LOG": str(tmp_path / "kubectl.log"),
            "KUBECTL_CAPTURE": str(capture),
            "GATEWAY_CLASS_NAME": "eg",
        }
    )
    result = subprocess.run(  # noqa: S603 - fixed local wrapper and test-only tools
        [
            BASH,
            str(scripts / "apply_raw_k8s.sh"),
            "k8s/gateway-api/gatewayclass.yaml",
        ],
        cwd=repo,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "manifest path resolves outside the repository" in result.stderr
    assert not capture.exists()
    log_path = Path(environment["KUBECTL_LOG"])
    calls = (
        log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    )
    assert not any(call.startswith("create ") for call in calls)


@pytest.mark.skipif(not POSIX_BASH_AVAILABLE, reason="requires a POSIX shell and bash")
@pytest.mark.parametrize(
    ("environment", "expected_error"),
    [
        ({"KUBE_VERSION": "1.37"}, "Kubernetes server version"),
        ({"GATEWAY_BUNDLE": "v1.5.1"}, "Gateway API bundle"),
        (
            {"GATEWAYCLASS_BUNDLE": "v1.5.1"},
            "Gateway API bundle for CRD 'gatewayclasses.gateway.networking.k8s.io'",
        ),
        (
            {"HTTPROUTE_CHANNEL": "experimental"},
            "Gateway API bundle for CRD 'httproutes.gateway.networking.k8s.io'",
        ),
        ({"GATEWAY_CHANNEL": "experimental"}, "Standard channel"),
        ({"GATEWAY_CRD_VERSIONS": "v1beta1"}, "does not serve required version"),
        (
            {"ENVOY_POLICY_CRD_VERSIONS": "v1alpha1=false"},
            "does not serve required version",
        ),
        (
            {"BACKEND_POLICY_CRD_MISSING": "1"},
            "required CRD 'backendtrafficpolicies.gateway.envoyproxy.io' is unavailable",
        ),
        (
            {"BACKEND_POLICY_CRD_VERSIONS": "v1alpha2"},
            "does not serve required version",
        ),
        ({"ENVOY_GATEWAY_VERSION": "v1.8.4"}, "Envoy Gateway version"),
    ],
)
def test_gatewayclass_wrapper_fails_closed_on_incompatible_prerequisites(
    tmp_path: Path, environment: dict[str, str], expected_error: str
) -> None:
    result, capture, log_path = _run_gatewayclass_wrapper(
        tmp_path, overrides=environment
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert not capture.exists()
    assert not any(
        call.startswith("create ")
        for call in log_path.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.skipif(not POSIX_BASH_AVAILABLE, reason="requires a POSIX shell and bash")
def test_gatewayclass_wrapper_never_takes_over_an_existing_class(
    tmp_path: Path,
) -> None:
    result, capture, log_path = _run_gatewayclass_wrapper(
        tmp_path,
        overrides={
            "EXISTING_CONTROLLER": "other.example/controller",
        },
    )

    assert result.returncode != 0
    assert "existing GatewayClass uses a different controller" in result.stderr
    assert not capture.exists()
    assert not any(
        call.startswith("create ")
        for call in log_path.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.skipif(not POSIX_BASH_AVAILABLE, reason="requires a POSIX shell and bash")
def test_gatewayclass_wrapper_leaves_compatible_existing_class_untouched(
    tmp_path: Path,
) -> None:
    result, capture, log_path = _run_gatewayclass_wrapper(
        tmp_path,
        overrides={
            "EXISTING_CONTROLLER": "gateway.envoyproxy.io/gatewayclass-controller",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "leaving it unchanged" in result.stdout
    assert not capture.exists()
    assert not any(
        call.startswith(("create ", "apply "))
        for call in log_path.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.skipif(not POSIX_BASH_AVAILABLE, reason="requires a POSIX shell and bash")
def test_gatewayclass_wrapper_fails_closed_when_existing_state_cannot_be_read(
    tmp_path: Path,
) -> None:
    result, capture, log_path = _run_gatewayclass_wrapper(
        tmp_path,
        overrides={"GATEWAYCLASS_LOOKUP_ERROR": "1"},
    )

    assert result.returncode != 0
    assert "could not safely inspect the existing GatewayClass" in result.stderr
    assert not capture.exists()
    assert not any(
        call.startswith("create ")
        for call in log_path.read_text(encoding="utf-8").splitlines()
    )
