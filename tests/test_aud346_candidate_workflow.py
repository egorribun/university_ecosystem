from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _canonical_backend_python_image() -> str:
    dockerfile = (ROOT / "backend.Dockerfile").read_text(encoding="utf-8")
    references = re.findall(
        r"^FROM\s+(python:3\.14\.8-slim-bookworm@sha256:[0-9a-f]{64})"
        r"(?:\s+AS\s+\w+)?\s*$",
        dockerfile,
        re.MULTILINE,
    )
    assert references and len(set(references)) == 1
    return references[0]


def test_candidate_workflow_keeps_offline_validation_then_runs_live_proof() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/nightly-full-gate.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["chaos-loadtest-orchestrator"]
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 10
    assert job["permissions"] == {"contents": "read"}

    steps = job["steps"]
    dry_run = next(
        step for step in steps if step["name"] == "Run chaos loadtest dry-runs"
    )
    calls = [
        line.strip()
        for line in dry_run["run"].splitlines()
        if "run_chaos_loadtest.py" in line
    ]
    assert len(calls) == 3
    assert all("--dry-run" in call for call in calls)
    assert all("--require-fault-impact" not in call for call in calls)
    live = next(
        step
        for step in steps
        if step["name"] == "Run owned Kind Chaos Mesh fault and recovery proof"
    )
    assert steps.index(live) > steps.index(dry_run)
    assert live["timeout-minutes"] == 9
    assert live["run"] == "bash scripts/chaos/aud346_live_kind_proof.sh"


def test_candidate_live_setup_uses_owned_and_bounded_targets() -> None:
    script = (ROOT / "scripts/chaos/aud346_live_kind_proof.sh").read_text(
        encoding="utf-8"
    )
    assert "kindest/node:v1\\.36\\.4@sha256:" in script
    assert 'KIND_VERSION="v0.31.0"' in script
    assert 'KUBECTL_VERSION="v1.36.4"' in script
    assert 'HELM_VERSION="v4.2.4"' in script
    assert 'CHAOS_MESH_VERSION="2.8.7"' in script
    assert "RUN_BUDGET_SECONDS=480" in script
    assert "CLEANUP_RESERVE_SECONDS=60" in script
    assert "timeout --signal=TERM --kill-after=2s" in script
    assert '"${DOCKER_HOST}" != "unix:///var/run/docker.sock"' in script
    assert '"${DOCKER_CONTEXT}" != "default"' in script
    assert 'export DOCKER_CONFIG="${WORK_DIR}/docker"' in script
    assert "unset DOCKER_HOST DOCKER_TLS_VERIFY DOCKER_CERT_PATH" in script
    assert "export DOCKER_CONTEXT=default" in script
    assert "[[ ! -S /var/run/docker.sock ]]" in script
    assert "docker context inspect default --format" in script
    assert '"$DOCKER_ENDPOINT" != "unix:///var/run/docker.sock"' in script
    assert "docker version --format" in script
    assert script.index("trap cleanup EXIT") < script.index("docker context inspect")
    runner = (ROOT / "scripts/chaos/run_chaos_loadtest.py").read_text(encoding="utf-8")
    assert '"university-ecosystem/aud346-live-success-receipt/v1"' in runner
    assert '"AUD346_SUCCESS_RECEIPT %s"' in runner
    assert 'export UV_CACHE_DIR="${WORK_DIR}/uv-cache"' in script
    assert 'WORK_DIR="$(mktemp -d "${WORK_PREFIX}XXXXXX")"' in script
    assert "controllerManager.enableFilterNamespace=true" in script
    assert "chaos-mesh.org/inject: enabled" in (
        ROOT / "k8s/chaos/fixtures/aud346-target.yaml"
    ).read_text(encoding="utf-8")
    assert (
        "controllerManager.podChaos.podFailure.pauseImage=registry.k8s.io/pause:3.10.1"
        in script
    )
    assert (
        'docker update --cpus=2 --memory=4g --memory-swap=4g "$NODE_CONTAINER"'
        in script
    )
    assert '"io.x-k8s.kind.cluster"' in script
    assert "2000000000|4294967296|4294967296" in script
    assert (
        "{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}"
        in script
    )
    assert "setsid timeout --signal=TERM --kill-after=2s" in script
    assert "kind-create.log" in script
    assert "port-forward --address 127.0.0.1" in script
    assert "--duration 25" in script
    assert "--require-fault-impact" in script
    assert "trap cleanup EXIT" in script
    assert "trap 'exit 130' INT" in script
    assert "trap 'exit 143' TERM" in script
    assert 'run_kind_owner_cleanup teardown --run-id "$RUN_ID"' in script
    assert 'run_kind_owner_cleanup recover --run-id "$RUN_ID"' in script
    assert (
        '--state-dir "$STATE_DIR" create --run-id "$RUN_ID" --node-image "$NODE_IMAGE"'
        in script
    )
    assert "kind delete cluster" not in script
    assert "docker system prune" not in script
    assert "docker rm" not in script
    assert "~/.kube" not in script


def test_candidate_manifests_select_only_one_aud346_target() -> None:
    documents = list(
        yaml.safe_load_all(
            (ROOT / "k8s/chaos/fixtures/aud346-target.yaml").read_text(encoding="utf-8")
        )
    )
    namespace, deployment, service, policy = documents
    assert namespace["metadata"]["name"] == "aud346"
    assert namespace["metadata"]["annotations"] == {"chaos-mesh.org/inject": "enabled"}
    assert deployment["metadata"]["namespace"] == "aud346"
    assert deployment["spec"]["replicas"] == 1
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == _canonical_backend_python_image()
    assert service["metadata"]["namespace"] == "aud346"
    assert policy["kind"] == "NetworkPolicy"

    chaos_doc = yaml.safe_load(
        (ROOT / "k8s/chaos/aud346-pod-failure.yaml").read_text(encoding="utf-8")
    )
    assert chaos_doc["kind"] == "PodChaos"
    assert chaos_doc["metadata"]["namespace"] == "aud346"
    assert chaos_doc["spec"]["action"] == "pod-failure"
    assert chaos_doc["spec"]["mode"] == "all"
    assert chaos_doc["spec"]["duration"] == "45s"
    assert chaos_doc["spec"]["selector"]["namespaces"] == ["aud346"]
    assert chaos_doc["spec"]["selector"]["labelSelectors"] == {
        "app.kubernetes.io/name": "aud346-chaos-target"
    }


def test_fixture_liveness_does_not_mask_the_bounded_chaos_fault() -> None:
    documents = list(
        yaml.safe_load_all((ROOT / "k8s/chaos/fixtures/aud346-target.yaml").read_text())
    )
    deployment = next(
        document for document in documents if document["kind"] == "Deployment"
    )
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    readiness = container["readinessProbe"]
    liveness = container["livenessProbe"]
    assert liveness == {
        "httpGet": {"path": "/health", "port": "http"},
        "periodSeconds": 10,
        "timeoutSeconds": 1,
        "failureThreshold": 7,
    }
    assert readiness == {
        "httpGet": {"path": "/health", "port": "http"},
        "periodSeconds": 1,
        "timeoutSeconds": 1,
        "failureThreshold": 2,
    }
    assert container["ports"] == [{"name": "http", "containerPort": 8080}]
    chaos = yaml.safe_load((ROOT / "k8s/chaos/aud346-pod-failure.yaml").read_text())
    duration = int(chaos["spec"]["duration"].removesuffix("s"))
    # A first failed probe may coincide with injection; the seventh must still
    # be after the entire declared fault plus a bounded recovery margin.
    assert (liveness["failureThreshold"] - 1) * liveness[
        "periodSeconds"
    ] >= duration + 15
    assert readiness["periodSeconds"] * readiness["failureThreshold"] < duration
    # The observed fault window must end before the PodChaos lifetime, leaving time
    # to confirm injection first; otherwise the fault could expire mid-measurement.
    script = (ROOT / "scripts/chaos/aud346_live_kind_proof.sh").read_text(
        encoding="utf-8"
    )
    window = int(re.search(r"--duration (\d+) \\", script).group(1))
    assert window + 15 <= duration


def test_fixture_stops_promptly_when_pod_failure_swaps_the_image() -> None:
    # The server runs as PID 1, where an unhandled SIGTERM is ignored: three
    # nightlies saw 100% success under an injected fault because the old
    # container served through the 30 s default grace, longer than the window.
    documents = list(
        yaml.safe_load_all((ROOT / "k8s/chaos/fixtures/aud346-target.yaml").read_text())
    )
    deployment = next(
        document for document in documents if document["kind"] == "Deployment"
    )
    pod = deployment["spec"]["template"]["spec"]
    (container,) = pod["containers"]
    assert container["command"] == ["python", "-B", "-c"]
    (program,) = container["args"]
    assert "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))" in program
    assert program.index("signal.signal(") < program.index("serve_forever()")
    script = (ROOT / "scripts/chaos/aud346_live_kind_proof.sh").read_text(
        encoding="utf-8"
    )
    window = int(re.search(r"--duration (\d+) \\", script).group(1))
    assert 1 <= pod["terminationGracePeriodSeconds"] <= 2
    assert pod["terminationGracePeriodSeconds"] * 5 <= window


def test_live_proof_keeps_forwarding_through_the_fault_and_recovery() -> None:
    script = (ROOT / "scripts/chaos/aud346_live_kind_proof.sh").read_text(
        encoding="utf-8"
    )
    start = script.index("supervise_port_forward() {")
    body = script[start : script.index("\n}\n", start)]
    # kubectl exits on the first refused in-pod connection; the supervisor
    # restarts it on the same local port so recovery stays observable.
    assert "while true; do" in body
    assert 'port-forward --address 127.0.0.1 "service/${TARGET_SERVICE}"' in body
    assert 'wait "$child" || true' in body
    assert (
        'trap \'[[ -n "$child" ]] && kill "$child" >/dev/null 2>&1; exit 0\' TERM'
        in body
    )
    launch = 'supervise_port_forward >"${DIAG_DIR}/port-forward.log" 2>&1 &\n'
    assert script.count(launch) == 1
    assert script.index(launch) < script.index("--require-fault-impact")
    assert 'kill "$PORT_FORWARD_PID"' in script


def test_fixture_network_policy_is_exact_and_default_deny() -> None:
    documents = list(
        yaml.safe_load_all((ROOT / "k8s/chaos/fixtures/aud346-target.yaml").read_text())
    )
    deployment = next(
        document for document in documents if document["kind"] == "Deployment"
    )
    service = next(document for document in documents if document["kind"] == "Service")
    policies = [
        document for document in documents if document["kind"] == "NetworkPolicy"
    ]
    assert len(policies) == 1
    policy = policies[0]
    assert policy["apiVersion"] == "networking.k8s.io/v1"
    assert (
        policy["metadata"]["namespace"]
        == deployment["metadata"]["namespace"]
        == "aud346"
    )
    labels = {"app.kubernetes.io/name": "aud346-chaos-target"}
    assert deployment["spec"]["template"]["metadata"]["labels"] == labels
    assert service["spec"]["selector"] == labels
    assert policy["spec"] == {
        "podSelector": {"matchLabels": labels},
        "policyTypes": ["Ingress", "Egress"],
        "ingress": [],
        "egress": [],
    }
