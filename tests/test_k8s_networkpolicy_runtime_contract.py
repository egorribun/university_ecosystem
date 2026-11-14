"""Contract checks for the AUD-169/188/189/438 NetworkPolicy runtime proof.

These tests do not start a cluster. They pin the workflow, the proof script, the
probe modules and the receipt contract, so that a later edit cannot drop Calico
enforcement, a probe, the derived base image, an application-level check, the
public-egress exception scope or the fail-closed verdict.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "k8s-networkpolicy-runtime.yml"
PROOF = ROOT / "scripts" / "k8s" / "networkpolicy_runtime_proof.sh"
PROBE_DIR = ROOT / "scripts" / "k8s"
PROBE = PROBE_DIR / "networkpolicy_runtime_probe.py"
PROBE_MODULES = (
    PROBE,
    PROBE_DIR / "networkpolicy_runtime_kube.py",
    PROBE_DIR / "networkpolicy_runtime_rows.py",
    PROBE_DIR / "networkpolicy_runtime_app.py",
    PROBE_DIR / "networkpolicy_runtime_standins.py",
)
BACKEND_DOCKERFILE = ROOT / "backend.Dockerfile"
HARNESS = ROOT / "docs" / "audits" / "AUD169-188-189-networkpolicy-runtime-harness.md"
ADR_054 = ROOT / "docs" / "adr" / "ADR-054-mvp-docker-compose-deployment-target.md"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
NODE_IMAGE = re.compile(r"^kindest/node:v1\.36\.4@sha256:[0-9a-f]{64}$")

FINDING_PROBES = (
    "aud169-a-pod",
    "aud169-a-svc",
    "aud169-b-own",
    "aud169-cross-release",
    "aud169-unrelated",
    "aud188-jwks-pod",
    "aud188-jwks-svc",
    "aud188-jwks-b-own",
    "aud188-jwks-cross",
    "aud188-jwks-unrelated",
    "aud189-dns-udp",
    "aud189-dns-tcp",
    "aud189-dns-decoy-tcp",
    "aud189-dns-decoy-udp",
    "aud189-443-pod",
    "aud189-443-svc",
    "aud189-443-public",
    "aud189-public-backend",
    "aud189-public-ws",
    "aud189-public-gateway",
    "aud189-public-frontend",
    "aud189-public-outbox",
    "aud189-backup-public",
    "aud189-backup-decoy-443",
    "aud189-backup-decoy-80",
    "aud189-backup-backend-8000",
    "aud189-linklocal-fp",
    "aud189-linklocal-backend",
    "aud189-linklocal-backup",
    "aud188-temporal-allow",
    "aud188-nats-allow",
    "aud188-temporal-decoy",
    "aud188-nats-decoy",
    "aud438-metrics-prometheus",
    "aud438-metrics-other",
    "aud438-metrics-unrelated",
    "aud438-metrics-ingress",
    "aud438-public-prometheus",
    "aud438-public-unrelated",
    "aud438-public-ingress",
)
APP_LEVEL_CHECKS = (
    "aud169-redis-authenticated-ping",
    "aud169-redis-unauthenticated-denied",
    "aud169-redis-wrong-password-denied",
    "aud169-redis-unrelated-labels-denied",
    "aud188-key1-accepted-after-publication",
    "aud188-key2-rejected-before-publication",
    "aud188-key2-accepted-after-rotation",
    "aud188-key1-accepted-during-transition",
    "aud188-unpublished-key3-rejected",
    "aud188-forged-kid-rejected",
    "aud188-alg-none-rejected",
    "aud188-retired-key1-rejected",
    "aud188-key2-accepted-after-retirement",
)
SUPPRESSION_MARKERS = ("noqa", "pragma", "type: ignore", "nosemgrep", "# nosec")


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict[str, Any]]:
    job = _workflow()["jobs"]["networkpolicy-kind-proof"]
    return job["steps"]


def _uses(step: dict[str, Any]) -> str:
    return str(step.get("uses", ""))


def _probe_source() -> str:
    return "\n".join(module.read_text(encoding="utf-8") for module in PROBE_MODULES)


def test_workflow_is_manual_scheduled_and_path_filtered_pr_only() -> None:
    workflow = _workflow()
    triggers = workflow.get(True, workflow.get("on"))
    assert set(triggers) == {"pull_request", "schedule", "workflow_dispatch"}
    paths = set(triggers["pull_request"]["paths"])
    assert {
        "charts/**",
        "k8s/**",
        "backend.Dockerfile",
        "scripts/k8s/networkpolicy_runtime_*.py",
        ".github/workflows/k8s-networkpolicy-runtime.yml",
    } <= paths
    assert "pull_request_target" not in WORKFLOW.read_text(encoding="utf-8")


def test_workflow_has_least_privilege_and_no_persisted_credentials() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["networkpolicy-kind-proof"]
    assert job["permissions"] == {"contents": "read"}
    checkout = next(
        step for step in _steps() if _uses(step).startswith("actions/checkout@")
    )
    assert checkout["with"]["persist-credentials"] is False


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    uses = [_uses(step) for step in _steps() if "uses" in step]
    assert uses, "workflow must use pinned actions"
    for reference in uses:
        _, _, ref = reference.partition("@")
        assert SHA40.match(ref.split(" ")[0]), reference


def test_run_blocks_never_interpolate_expressions() -> None:
    for step in _steps():
        if "run" in step:
            assert "${{" not in step["run"], step.get("name")


def test_artifact_is_retained_for_90_days_and_required_to_exist() -> None:
    upload = next(
        step for step in _steps() if _uses(step).startswith("actions/upload-artifact@")
    )
    assert upload["if"] == "always()"
    assert upload["with"]["retention-days"] == 90
    assert upload["with"]["if-no-files-found"] == "error"


def test_job_timeout_covers_the_catalog_budget() -> None:
    job = _workflow()["jobs"]["networkpolicy-kind-proof"]
    assert job["timeout-minutes"] == 45


def test_workflow_is_not_a_required_check_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "required_status_checks" not in text
    assert "branch_protection" not in text


def test_proof_script_pins_kind_node_image_and_calico_by_digest_and_sha256() -> None:
    text = PROOF.read_text(encoding="utf-8")
    node = re.search(r'NODE_IMAGE="([^"]+)"', text)
    assert node is not None
    assert NODE_IMAGE.match(node.group(1))
    calico = re.search(r'CALICO_SHA256="([0-9a-f]{64})"', text)
    assert calico and SHA256.match(calico.group(1))
    assert "projectcalico/calico/v3.30.3/manifests/calico.yaml" in text
    kubernetes = re.search(r'KUBERNETES_VERSION="v(1\.\d+)\.\d+"', text)
    assert kubernetes and int(kubernetes.group(1).split(".")[1]) >= 33


def test_proof_script_uses_the_same_kind_kubectl_helm_pins_as_aud373() -> None:
    proof = PROOF.read_text(encoding="utf-8")
    aud373 = (ROOT / "scripts" / "kind" / "aud373_internal_mtls_proof.sh").read_text(
        encoding="utf-8"
    )
    for name in ("KIND_VERSION", "KUBECTL_VERSION", "HELM_VERSION"):
        value = re.search(rf'readonly {name}="([^"]+)"', proof)
        assert value, name
        assert f'readonly {name}="{value.group(1)}"' in aud373, name


def test_calico_is_verified_before_apply_and_default_cni_is_disabled() -> None:
    text = PROOF.read_text(encoding="utf-8")
    assert "disableDefaultCNI: true" in text
    verify = text.index('download_pinned "$CALICO_URL"')
    apply = text.index("kubectl apply --server-side --force-conflicts -f")
    assert verify < apply
    assert "calico-node" in text and "rollout status daemonset/calico-node" in text


def test_proof_script_cleans_up_its_own_cluster_and_writes_receipt_to_artifact_dir() -> (
    None
):
    text = PROOF.read_text(encoding="utf-8")
    assert "trap cleanup EXIT" in text
    assert 'kind delete cluster --name "$CLUSTER_NAME"' in text
    assert '--receipt "${DIAG_DIR}/receipt.json"' in text
    assert "--frozen" in text


# The only permitted suppression is the inline S603 marker with a reason on the
# subprocess.run line of networkpolicy_runtime_kube.py. Every other marker fails.
_ALLOWED_KUBE_SUBPROCESS_NOQA = re.compile(
    r"(subprocess\.run\(\s*)# noqa: S603 - \S.*$"
)


def _suppression_hits(module_name: str, text: str) -> list[str]:
    hits: list[str] = []
    for line in text.splitlines():
        remaining = line
        if module_name == "networkpolicy_runtime_kube.py":
            remaining = _ALLOWED_KUBE_SUBPROCESS_NOQA.sub(r"\1", line)
        lowered = remaining.lower()
        hits.extend(marker for marker in SUPPRESSION_MARKERS if marker in lowered)
    return hits


def test_probe_modules_carry_no_suppression_comments() -> None:
    for module in PROBE_MODULES:
        text = module.read_text(encoding="utf-8")
        assert _suppression_hits(module.name, text) == [], module.name


@pytest.mark.parametrize(
    ("module", "mutation"),
    [
        (
            "networkpolicy_runtime_kube.py",
            lambda text: text.replace("# noqa: S603 - ", "# noqa: S603 ", 1),
        ),
        (
            "networkpolicy_runtime_kube.py",
            lambda text: text.replace("# noqa: S603 - ", "# noqa: S101 - ", 1),
        ),
        (
            "networkpolicy_runtime_kube.py",
            lambda text: text + "\nVALUE = 1  # noqa: S603 - reason\n",
        ),
        (
            "networkpolicy_runtime_kube.py",
            lambda text: text + "\n# nosemgrep: rule\n",
        ),
        (
            "networkpolicy_runtime_probe.py",
            lambda text: text + "\nX = subprocess.run(  # noqa: S603 - reason\n",
        ),
    ],
)
def test_suppression_guard_rejects_any_other_marker(module: str, mutation) -> None:
    original = (PROBE_DIR / module).read_text(encoding="utf-8")
    assert _suppression_hits(module, original) == []
    assert _suppression_hits(module, mutation(original)) != []


def test_probe_covers_every_harness_finding_and_the_fail_closed_verdict() -> None:
    text = _probe_source()
    for probe_id in FINDING_PROBES:
        assert f'"{probe_id}"' in text, probe_id
    assert '"verdict": "pass" if all_pass else "fail"' in text
    assert "return 0 if all_pass else 1" in text
    # A denial without a live same-destination control is never a pass.
    assert 'entry["verdict"] = "inconclusive"' in text
    # Baseline reachability is required before any policy is applied.
    assert "baseline reachability failed before policy" in text


def test_application_level_checks_are_present_and_fail_closed() -> None:
    text = _probe_source()
    for check_id in APP_LEVEL_CHECKS:
        assert f'"{check_id}"' in text, check_id
    # The authenticated Redis baseline is part of the fail-closed verdict.
    assert 'baseline_pass = app_baseline.get("result") == "redis-pong"' in text
    assert re.search(r"all_pass = \(?\s*rows_pass and app_pass and baseline_pass", text)


def test_stand_in_base_image_is_read_from_the_backend_dockerfile() -> None:
    text = _probe_source()
    assert "RUNTIME_FROM" in text
    assert "exactly one python runtime FROM" in text
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    runtime = re.findall(
        r"^FROM (python:\S+@sha256:[0-9a-f]{64}) AS runtime\s*$",
        dockerfile,
        re.MULTILINE,
    )
    assert len(runtime) == 1
    # The probe must not duplicate the base digest; it is read from the Dockerfile.
    assert runtime[0].split("@sha256:")[1] not in text


def test_revocation_redis_is_the_chart_workload_with_a_generated_credential() -> None:
    text = _probe_source()
    assert "revocation-redis-master" in text
    assert "def strip_metrics_exporter" in text
    assert "real_redis_digest" in text
    # The Secret value is generated per run and never written to the receipt.
    assert '"credential_value": "generated per run and not recorded"' in text


def _rows_module() -> Any:
    """Import the probe row table without a cluster (pure data and verdict rules)."""
    if str(PROBE_DIR) not in sys.path:
        sys.path.insert(0, str(PROBE_DIR))
    return importlib.import_module("networkpolicy_runtime_rows")


def _rows_by_id() -> dict[str, Any]:
    return {row.probe_id: row for row in _rows_module().ROWS}


def test_public_egress_exception_rows_are_scoped_to_backend_and_backup() -> None:
    rows = _rows_module().ROWS
    allowed = {
        row.probe_id
        for row in rows
        if row.target == "public-https" and row.expect_allow
    }
    assert allowed == {"aud189-public-backend", "aud189-backup-public"}
    denied = {
        row.probe_id
        for row in rows
        if row.target == "public-https" and not row.expect_allow
    }
    assert denied == {
        "aud189-443-public",
        "aud189-public-ws",
        "aud189-public-gateway",
        "aud189-public-frontend",
        "aud189-public-outbox",
    }
    assert {row.port for row in rows if row.target == "public-https"} == {443}


def test_every_denial_has_a_live_same_destination_control_and_ids_are_unique() -> None:
    rows = _rows_module().ROWS
    ids = [row.probe_id for row in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        if not row.expect_allow:
            assert row.control is not None, row.probe_id


def test_metrics_rows_are_http_get_on_metrics_and_deny_unselected_sources() -> None:
    rows = _rows_by_id()
    module = _rows_module()
    for probe_id in (
        "aud438-metrics-prometheus",
        "aud438-metrics-other",
        "aud438-metrics-unrelated",
        "aud438-metrics-ingress",
    ):
        row = rows[probe_id]
        assert row.mode == "http", probe_id
        assert row.path == "/metrics", probe_id
        assert row.port == module.WS_METRICS_PORT, probe_id
        assert row.target == "a-ws-metrics", probe_id
    assert rows["aud438-metrics-prometheus"].source == "prometheus"
    assert rows["aud438-metrics-prometheus"].expect_allow is True
    assert rows["aud438-metrics-other"].expect_allow is False
    assert rows["aud438-metrics-unrelated"].source == "unrelated"
    assert rows["aud438-metrics-unrelated"].expect_allow is False
    assert rows["aud438-metrics-ingress"].source == "ingress"
    assert rows["aud438-metrics-ingress"].expect_allow is False


def test_file_processor_reaches_only_release_temporal_and_nats() -> None:
    rows = _rows_by_id()
    module = _rows_module()
    temporal = rows["aud188-temporal-allow"]
    nats = rows["aud188-nats-allow"]
    assert (temporal.source, temporal.target, temporal.port) == (
        "a-fp",
        "a-temporal-pod",
        module.TEMPORAL_PORT,
    )
    assert temporal.expect_allow is True
    assert (nats.source, nats.target, nats.port) == (
        "a-fp",
        "a-nats-pod",
        module.NATS_PORT,
    )
    assert nats.expect_allow is True
    for probe_id, decoy in (
        ("aud188-temporal-decoy", "decoy-temporal-pod"),
        ("aud188-nats-decoy", "decoy-nats-pod"),
    ):
        row = rows[probe_id]
        assert row.source == "a-fp" and row.target == decoy, probe_id
        assert row.expect_allow is False
        assert row.control is not None and row.control[0] == "unrelated"


def test_backup_rows_allow_only_public_443_and_deny_other_ports_and_peers() -> None:
    rows = _rows_by_id()
    backup_rows = [row for row in rows.values() if row.source == "a-backup"]
    assert {row.probe_id for row in backup_rows} == {
        "aud189-backup-public",
        "aud189-backup-decoy-443",
        "aud189-backup-decoy-80",
        "aud189-backup-backend-8000",
        "aud189-linklocal-backup",
    }
    allowed = [row for row in backup_rows if row.expect_allow]
    assert [(row.target, row.port) for row in allowed] == [("public-https", 443)]
    for row in backup_rows:
        if not row.expect_allow:
            assert row.control is not None, row.probe_id


def test_link_local_rows_deny_every_workload_against_a_host_network_control() -> None:
    rows = _rows_by_id()
    module = _rows_module()
    linklocal = [row for row in rows.values() if row.target == "link-local-443"]
    assert {row.source for row in linklocal} == {"a-fp", "a-backend", "a-backup"}
    for row in linklocal:
        assert row.expect_allow is False, row.probe_id
        assert row.port == module.LINK_LOCAL_PORT == 443
        assert row.control == ("linklocal", "link-local-443", "tcp", 443), row.probe_id


def test_link_local_address_matches_the_proof_script_and_is_link_local() -> None:
    module = _rows_module()
    assert module.LINK_LOCAL_ADDRESS.startswith("169.254.")
    text = PROOF.read_text(encoding="utf-8")
    match = re.search(r'readonly LINK_LOCAL_ADDRESS="([^"]+)"', text)
    assert match and match.group(1) == module.LINK_LOCAL_ADDRESS


def test_proof_script_adds_link_local_address_before_the_probe_and_fails_closed() -> (
    None
):
    text = PROOF.read_text(encoding="utf-8")
    call = text.index("\n  add_link_local_address\n")
    probe = text.index(
        "uv run --frozen python scripts/k8s/networkpolicy_runtime_probe.py"
    )
    assert call < probe
    assert 'ip addr add "${LINK_LOCAL_ADDRESS}/32" dev eth0' in text
    assert '[[ "$addresses" == *"inet ${LINK_LOCAL_ADDRESS}/32"* ]]' in text


def test_probe_builds_backup_and_host_network_stand_ins_from_rendered_labels() -> None:
    text = _probe_source()
    assert "backup.enabled=true" in text
    assert "cronjob_template_labels(app_a" in text
    assert 'find(app, "CronJob", f"{release}-{BACKUP_CRONJOB}")' in text
    assert "host_network=True" in text
    assert text.count("host_network=True") == 1
    assert '"hostNetwork": host_network' in text
    assert '{"app.kubernetes.io/name": "temporal"}' in text
    assert '{"app.kubernetes.io/name": "nats"}' in text


def test_not_run_keeps_unproven_items_and_drops_the_proven_ones() -> None:
    text = _probe_source()
    # Proven by the probe matrix now, so they are no longer listed as unproven.
    assert "backup public TCP/443 allowance" not in text
    assert "link-local TCP/443 destination" not in text
    # Still unproven, and stated as such.
    assert "file-processor process JWKS refresher" in text
    assert "backup job image behaviour" in text
    assert "metrics exposition content" in text
    assert "authenticated Redis PING and revoked/unrevoked" not in text
    assert "owner-approved public TCP/443 allowance" not in text


def test_probe_asserts_rendered_ports_and_fails_closed_on_drift() -> None:
    text = PROBE.read_text(encoding="utf-8")
    assert "def assert_rendered_ports" in text
    assert "raise SystemExit" in text
    rows = (PROBE_DIR / "networkpolicy_runtime_rows.py").read_text(encoding="utf-8")
    assert "WS_METRICS_PORT = 9108" in rows
    assert "BACKEND_PORT = 8000" in rows


def test_probe_scrapes_only_prometheus_pods_and_limits_public_targets() -> None:
    text = _probe_source()
    assert '"app.kubernetes.io/name": "prometheus"' in text
    assert 'PUBLIC_HTTPS_TARGET = "1.1.1.1"' in (
        PROBE_DIR / "networkpolicy_runtime_rows.py"
    ).read_text(encoding="utf-8")
    assert text.count('"public-https"') >= 4


def test_adr_054_addendum_documents_the_public_egress_exception() -> None:
    text = ADR_054.read_text(encoding="utf-8")
    assert "## Addendum 2026-11-12" in text
    assert "backend" in text and "backup" in text
    assert "public" in text and "TCP/443" in text
    assert "FQDN" in text


def test_harness_status_describes_the_hosted_run_without_accepting_findings() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    assert "k8s-networkpolicy-runtime.yml" in text
    assert "scripts/k8s/networkpolicy_runtime_proof.sh" in text
    assert "not accepted" in text.lower()


@pytest.mark.parametrize(
    "probe_id",
    ("aud189-linklocal-fp", "aud189-linklocal-backend", "aud189-linklocal-backup"),
)
@pytest.mark.parametrize("failed_endpoint", ("target_ok", "control_ok"))
def test_link_local_setup_failure_never_counts_as_policy_denial(
    probe_id: str,
    failed_endpoint: str,
) -> None:
    module = _rows_module()
    baseline = {"target_ok": True, "control_ok": True, failed_endpoint: False}

    def unexpected_probe(*_args: Any) -> dict[str, Any]:
        pytest.fail("An unreachable baseline must not be evaluated as policy denial")

    result = module.evaluate_row(
        _rows_by_id()[probe_id], baseline, unexpected_probe, ""
    )

    assert result["verdict"] == "inconclusive"
    assert result["reason"] == "baseline reachability failed before policy"


@pytest.mark.parametrize(
    "probe_id",
    ("aud189-linklocal-fp", "aud189-linklocal-backend", "aud189-linklocal-backup"),
)
@pytest.mark.parametrize("failed_control", (0, 2))
def test_link_local_denial_requires_both_live_controls(
    probe_id: str,
    failed_control: int,
) -> None:
    module = _rows_module()
    observations = [
        {"result": "connected"},
        {"result": "timeout"},
        {"result": "connected"},
    ]
    observations[failed_control] = {"result": "timeout"}
    pending = iter(observations)

    result = module.evaluate_row(
        _rows_by_id()[probe_id],
        {"target_ok": True, "control_ok": True},
        lambda *_args: next(pending),
        "",
    )

    assert result["verdict"] == "inconclusive"
    assert "live same-destination control" in result["reason"]


# Real file-processor runtime proof: hermetic setup, protocol and fail-closed checks.
def _real_runtime_module(name: str) -> Any:
    import importlib
    import sys

    if str(PROBE_DIR) not in sys.path:
        sys.path.insert(0, str(PROBE_DIR))
    return importlib.import_module(name)


def pins():
    import re

    python = re.findall(
        r"^FROM (python:\S+@sha256:[0-9a-f]{64}) AS runtime$",
        (ROOT / "backend.Dockerfile").read_text(),
        re.M,
    )[0]
    postgres = yaml.safe_load(
        (ROOT / "charts/university-ecosystem/values.yaml").read_text()
    )["backup"]["postgresImage"]
    return python, postgres


def test_native_config_retains_auth_and_loopback():
    m = _real_runtime_module("networkpolicy_runtime_temporal")

    result = yaml.safe_load(m.native_config(ROOT))
    original = yaml.safe_load((ROOT / "services/temporal/config.yaml").read_text())
    assert result["global"]["authorization"] == original["global"]["authorization"]
    assert result["services"] == original["services"]
    assert (
        result["global"]["tls"]["frontend"]["client"]["disableHostVerification"]
        is False
    )
    assert result["global"]["tls"]["frontend"]["server"]["requireClientAuth"] is False


def test_manifests_use_native_server_without_networkpolicy():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    with patch.object(
        m,
        "_credentials",
        return_value=("public-ca", {"tls.key": "server"}, {"tls.key": "issuer"}),
    ):
        objects, job, pod = m.fixture_objects(
            ROOT, "probe-a", *pins(), m.generate_signing_key("fixture")
        )
    assert not any(obj["kind"] == "NetworkPolicy" for obj in objects)
    assert job["spec"]["backoffLimit"] == 0
    assert job["spec"]["activeDeadlineSeconds"] == 180
    assert pod["spec"]["initContainers"][0]["restartPolicy"] == "Always"
    server, admin = pod["spec"]["containers"]
    assert server["command"][0] == "temporal-server"
    assert all(e["name"] != "POSTGRES_PWD" for e in server["env"])
    assert all(v.get("mountPath") != "/issuer" for v in server["volumeMounts"])
    assert admin["volumeMounts"] == [
        {"name": "ca", "mountPath": "/ca", "readOnly": True}
    ]
    config = next(
        x for x in objects if x["metadata"]["name"] == "netpol-temporal-config"
    )
    assert "entrypoint.sh" not in config["data"]
    assert config["data"]["render.py"] == m.SAFE_RENDER
    assert "os.umask(0o077)" in m.SAFE_RENDER
    assert (
        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        in m.POSTGRES_INIT
    )
    assert "rolsuper" in m.POSTGRES_INIT
    assert "tls.key" not in config["data"]


@pytest.mark.parametrize("stage", ["postgres", "schema", "temporal"])
def test_wait_failure_is_inconclusive_and_contains_no_exception(stage):
    import subprocess
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    failures = {"postgres": 0, "schema": 1, "temporal": 2}
    waits = [None] * failures[stage] + [
        subprocess.CalledProcessError(1, ["kubectl"], output="SECRET")
    ]
    with (
        patch.object(m, "fixture_objects", return_value=([], {}, {})),
        patch.object(m, "apply_objects"),
        patch.object(m, "kubectl", side_effect=waits),
    ):
        result = m.bootstrap_temporal(ROOT, "probe-a", *pins())
    assert result == {"result": "inconclusive", "stage": stage}
    assert "SECRET" not in str(result)


def test_namespace_failure_cannot_mint_worker_secret():
    import subprocess
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    with (
        patch.object(m, "fixture_objects", return_value=([], {}, {})),
        patch.object(m, "apply_objects") as apply,
        patch.object(m, "kubectl"),
        patch.object(
            m, "run_command", side_effect=subprocess.TimeoutExpired(["kubectl"], 240)
        ),
    ):
        result = m.bootstrap_temporal(ROOT, "probe-a", *pins())
    assert result == {"result": "inconclusive", "stage": "namespace"}
    assert apply.call_count == 3


def test_success_is_ready_not_pass_and_token_uses_stdin():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    with (
        patch.object(m, "fixture_objects", return_value=([], {}, {})),
        patch.object(m, "apply_objects"),
        patch.object(m, "kubectl"),
        patch.object(m, "run_command") as run,
    ):
        result = m.bootstrap_temporal(ROOT, "probe-a", *pins())
    assert result["result"] == "ready"
    assert "api_key" not in str(result)
    assert "api_key" not in str(run.call_args.args)
    assert "api_key" in run.call_args.kwargs["stdin"]
    assert "--tls=false" not in m.NAMESPACE_INIT
    assert "--tls-ca-path /ca/ca.crt --tls-server-name temporal" in m.NAMESPACE_INIT


def test_untracked_pin_rejected_before_credentials():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    python, postgres = pins()
    with patch.object(m, "_credentials") as credentials, pytest.raises(ValueError):
        m.fixture_objects(
            ROOT, "probe-a", python.replace("python:", "other:"), postgres, None
        )
    credentials.assert_not_called()


def test_safe_renderer_keeps_password_out_of_argv_and_owner_only(tmp_path):
    import subprocess

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    import os
    import stat

    source = tmp_path / "source"
    source.mkdir()
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    (source / "docker.yaml").write_text(
        'user: "${POSTGRES_USER}"\npassword: "${POSTGRES_PWD}"\nurl: "${TEMPORAL_JWKS_URL}"\n'
    )
    (source / "ca.crt").write_text("fixture-public-ca")
    program = (
        m.SAFE_RENDER.replace("/config/", str(source) + "/")
        .replace("/ca/", str(source) + "/")
        .replace("/rendered/", str(rendered) + "/")
    )
    command = [sys.executable, "-I", "-c", program]
    password = "a" * 64
    import shlex

    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=shlex.join(command),
        env={**os.environ, "POSTGRES_USER": "ue_temporal", "POSTGRES_PWD": password},
        capture_output=True,
        text=True,
        check=True,
    )
    assert password not in str(command)
    assert password not in result.stdout + result.stderr
    assert password in (rendered / "docker.yaml").read_text()
    assert stat.S_IMODE((rendered / "docker.yaml").stat().st_mode) == 0o600
    assert stat.S_IMODE((rendered / "roots.pem").stat().st_mode) == 0o600


def test_postgres_bootstrap_credentials_never_given_to_temporal_or_schema():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_temporal")

    with patch.object(m, "_credentials", return_value=("public", {}, {})):
        objects, job, pod = m.fixture_objects(
            ROOT, "probe-a", *pins(), m.generate_signing_key("fixture")
        )
    pg = next(o for o in objects if o["metadata"]["name"] == "netpol-postgres")
    assert any(
        e.get("valueFrom", {}).get("secretKeyRef", {}).get("name")
        == "netpol-postgres-bootstrap"
        for e in pg["spec"]["containers"][0]["env"]
    )
    assert "netpol-postgres-bootstrap" not in str(job)
    assert "netpol-postgres-bootstrap" not in str(pod)
    assert 'PGPASSWORD="$SERVICE_PASSWORD"' in str(pg)


def test_native_setup_failure_inconclusive_not_pass():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    with patch.object(
        m,
        "bootstrap_temporal",
        return_value={"result": "inconclusive", "stage": "schema"},
    ):
        result = m.actual_processor_phase(
            ROOT,
            {"probe-a": ([], [])},
            {},
            {},
            python_image="unused",
            processor_image="unused",
            diagnostic_image="unused",
            source_sha="unused",
        )
    assert result == {
        "verdict": "inconclusive",
        "stage": "probe-a:temporal",
        "checks": [],
    }


def test_actual_client_transport_error_is_not_authentication_rejection():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    import subprocess

    with patch.object(
        m,
        "run_command",
        side_effect=subprocess.CalledProcessError(
            1, ["kubectl"], output="private-output"
        ),
    ):
        result = m.call_processor(
            "probe-a", {"ip": "127.0.0.1"}, "temporal", "private-token"
        )
    assert result == {"result": "setup-error"}
    assert m.grpc_probe_verdict(result, "Unauthenticated") == "inconclusive"


def test_grpc_certificates_only_certify_rendered_identity():
    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    from cryptography import x509
    from cryptography.x509.oid import ExtendedKeyUsageOID

    uri = "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
    server, client = m.grpc_credentials("processor.probe-a.svc", uri)
    server_cert = x509.load_pem_x509_certificate(server["tls.crt"].encode())
    client_cert = x509.load_pem_x509_certificate(client["tls.crt"].encode())
    assert server_cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName) == ["processor.probe-a.svc"]
    assert client_cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.UniformResourceIdentifier) == [uri]
    assert (
        ExtendedKeyUsageOID.CLIENT_AUTH
        in client_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    )
    assert (
        ExtendedKeyUsageOID.SERVER_AUTH
        in server_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    )


def test_rotation_mints_fresh_retired_token_after_wait():
    import ast

    tree = ast.parse(
        (ROOT / "scripts/k8s/networkpolicy_runtime_real_fp.py").read_text()
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    retirement = next(
        node
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "check_all"
        and any(
            isinstance(arg, ast.Constant) and arg.value == "retired-old-rejected"
            for arg in node.args
        )
    )
    mint = next(
        node
        for node in ast.walk(retirement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "token"
    )
    assert isinstance(mint.args[0], ast.Name) and mint.args[0].id == "old"
    assert len(mint.args) == 2 and not mint.keywords
    nonce = mint.args[1]
    assert isinstance(nonce, ast.Call) and isinstance(nonce.func, ast.Attribute)
    assert isinstance(nonce.func.value, ast.Name) and nonce.func.value.id == "secrets"
    assert nonce.func.attr == "token_hex"
    assert len(nonce.args) == 1 and not nonce.keywords
    assert isinstance(nonce.args[0], ast.Constant) and nonce.args[0].value == 16
    waits = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and node.func.attr == "sleep"
    ]
    final_wait = max(waits, key=lambda node: node.lineno)
    assert final_wait.lineno < mint.lineno
    delay = final_wait.args[0]
    assert isinstance(delay, ast.BinOp) and isinstance(delay.op, ast.Add)
    assert isinstance(delay.left, ast.Name) and delay.left.id == "refresh"
    assert isinstance(delay.right, ast.Constant) and delay.right.value == 10


def test_nats_stream_bootstrap_does_not_publish_work():
    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    assert "PUB $JS.API.STREAM.CREATE.FILES_PROCESS" in m.NATS_INIT
    assert "PUB files.process" not in m.NATS_INIT
    assert "socket.create_connection" in m.NATS_INIT


def test_unpublished_token_is_independently_validated():
    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    import pytest

    signer = m.generate_signing_key("new-key")
    env = {
        "FP_JWT_ISSUER": "https://issuer.fixture",
        "FP_JWT_AUDIENCE": "fixture-audience",
    }
    bearer = m.processor_token(
        signer,
        issuer=env["FP_JWT_ISSUER"],
        audience=env["FP_JWT_AUDIENCE"],
        session_id="synthetic-session",
    )
    m.validate_fixture_token(signer, bearer, env, "synthetic-session")
    with pytest.raises(ValueError):
        m.validate_fixture_token(signer, bearer, env, "other-session")
    wrong = dict(env, FP_JWT_AUDIENCE="wrong-audience")
    with pytest.raises(ValueError):
        m.validate_fixture_token(signer, bearer, wrong, "synthetic-session")


def test_same_new_token_checked_before_and_after_publication():
    source = (ROOT / "scripts/k8s/networkpolicy_runtime_real_fp.py").read_text()
    assert (
        'check_all("unpublished-new-rejected", new_token, "Unauthenticated")' in source
    )
    assert '"overlap-new-accepted",\n                new_token,' in source
    assert '"replicas": before' in source
    assert '"image_id": status.get("imageID", "")' in source
    assert "real_probe_b" in source


def test_real_processor_workflow_activation_is_source_bound():
    import json

    import yaml

    workflow = yaml.safe_load(WORKFLOW.read_text())
    job = workflow["jobs"]["networkpolicy-kind-proof"]
    assert job["timeout-minutes"] == 45
    steps = job["steps"]
    assert (
        steps[0]["with"]["ref"]
        == "${{ github.event.pull_request.head.sha || github.sha }}"
    )
    run = next(
        step
        for step in steps
        if step.get("run") == "bash scripts/k8s/networkpolicy_runtime_proof.sh"
    )
    assert run["env"]["UE_NETPOL_REAL_FP"] == "1"
    catalog = json.loads((ROOT / "quality/ci-check-catalog.json").read_text())
    entry = next(
        row
        for row in catalog["workflows"]
        if row["path"] == ".github/workflows/k8s-networkpolicy-runtime.yml"
    )
    guard = next(
        row["guard"] for row in entry["events"] if row["event"] == "pull_request"
    )
    assert json.loads(guard) == workflow[True]["pull_request"]


def test_completed_matrix_receipt_survives_interrupted_actual_phase(tmp_path):
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    import json
    from contextlib import ExitStack
    from types import SimpleNamespace

    import networkpolicy_runtime_real_fp
    import pytest

    loader = importlib.util.spec_from_file_location(
        "private_runner_checkpoint",
        ROOT / "scripts/k8s/networkpolicy_runtime_probe.py",
    )
    runner = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(runner)
    receipt = tmp_path / "receipt.json"
    args = SimpleNamespace(
        receipt=receipt,
        kubernetes_version="fixture",
        node_image="fixture",
        calico_sha256="fixture",
        real_processor_image="fixture",
        diagnostic_image="fixture",
        source_sha="a" * 40,
    )
    pods = {
        key: m.Pod("probe-a", key, ip="127.0.0.1", uid=key)
        for key in ["a-fp", "a-redis", "b-redis"]
    }
    rows = [{"probe_id": str(i), "verdict": "pass"} for i in range(40)]

    def interrupt(*args, **kwargs):
        observed = json.loads(receipt.read_text())
        assert len(observed["probes"]) == 40
        assert observed["matrix_verdict"] == "pass"
        assert observed["verdict"] == "inconclusive"
        assert observed["real_processor"]["verdict"] == "in_progress"
        assert observed["finished_utc"] is None
        raise KeyboardInterrupt

    replacements = {
        "runtime_base_image": "fixture",
        "render_all": {},
        "set_up_cluster": pods,
        "cluster_ip": "127.0.0.1",
        "build_targets": {},
        "make_executor": None,
        "measure_baseline": {},
        "redis_ping": {"result": "redis-pong"},
        "apply_policies": [],
        "evaluate_rows": rows,
        "resolver_status": {"verdict": "pass"},
        "run_app_checks": {"fixture": {"verdict": "pass"}},
        "policy_summary": [],
    }
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                runner.argparse.ArgumentParser, "parse_args", return_value=args
            )
        )
        for name, value in replacements.items():
            stack.enter_context(patch.object(runner, name, return_value=value))
        stack.enter_context(
            patch.object(
                networkpolicy_runtime_real_fp,
                "actual_processor_phase",
                side_effect=interrupt,
            )
        )
        with pytest.raises(KeyboardInterrupt):
            runner.main()
    assert receipt.exists()
    assert not receipt.with_suffix(".tmp").exists()


@pytest.mark.parametrize("outcome", ["pass", "inconclusive", "disabled"])
def test_runner_finishes_atomic_receipt_and_exit_status(tmp_path, outcome):
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    import json
    from contextlib import ExitStack
    from types import SimpleNamespace

    import networkpolicy_runtime_real_fp

    loader = importlib.util.spec_from_file_location(
        "private_runner_final", ROOT / "scripts/k8s/networkpolicy_runtime_probe.py"
    )
    runner = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(runner)
    args = SimpleNamespace(
        receipt=tmp_path / "receipt.json",
        kubernetes_version="fixture",
        node_image="fixture",
        calico_sha256="fixture",
        real_processor_image=None if outcome == "disabled" else "fixture",
        diagnostic_image=None if outcome == "disabled" else "fixture",
        source_sha=None if outcome == "disabled" else "a" * 40,
    )
    pods = {
        key: m.Pod("probe-a", key, ip="127.0.0.1", uid=key)
        for key in ["a-fp", "a-redis", "b-redis"]
    }
    rows = [{"probe_id": str(i), "verdict": "pass"} for i in range(40)]
    replacements = {
        "runtime_base_image": "fixture",
        "render_all": {},
        "set_up_cluster": pods,
        "cluster_ip": "127.0.0.1",
        "build_targets": {},
        "make_executor": None,
        "measure_baseline": {},
        "redis_ping": {"result": "redis-pong"},
        "apply_policies": [],
        "evaluate_rows": rows,
        "resolver_status": {"verdict": "pass"},
        "run_app_checks": {"fixture": {"verdict": "pass"}},
        "policy_summary": [],
    }
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                runner.argparse.ArgumentParser, "parse_args", return_value=args
            )
        )
        for name, value in replacements.items():
            stack.enter_context(patch.object(runner, name, return_value=value))
        phase = stack.enter_context(
            patch.object(
                networkpolicy_runtime_real_fp,
                "actual_processor_phase",
                return_value={"verdict": outcome, "checks": []},
            )
        )
        status = runner.main()
    observed = json.loads(args.receipt.read_text())
    assert status == (1 if outcome == "inconclusive" else 0)
    assert observed["finished_utc"] is not None
    assert observed["verdict"] == ("fail" if outcome == "inconclusive" else "pass")
    assert len(observed["probes"]) == 40
    if outcome == "disabled":
        phase.assert_not_called()
    else:
        phase.assert_called_once()
    assert any(r["finding"] == "AUD-169" for r in observed["not_run"]) == (
        outcome != "pass"
    )


def test_runner_rejects_partial_source_arguments(tmp_path):
    from unittest.mock import patch

    import pytest

    loader = importlib.util.spec_from_file_location(
        "private_runner_arguments",
        ROOT / "scripts/k8s/networkpolicy_runtime_probe.py",
    )
    runner = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(runner)
    args = [
        "fixture",
        "--receipt",
        str(tmp_path / "receipt.json"),
        "--kubernetes-version",
        "fixture",
        "--node-image",
        "fixture",
        "--calico-sha256",
        "fixture",
        "--real-processor-image",
        "only-one",
    ]
    with patch.object(sys, "argv", args), pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def deployment():
    env = {
        "FP_ENVIRONMENT": "staging",
        "FP_TEMPORAL_TLS_DISABLED": "false",
        "FP_MINIO_SECURE": "true",
        "FP_OTLP_INSECURE": "false",
        "FP_GRPC_TLS_CERT_FILE": "cert",
        "FP_GRPC_TLS_KEY_FILE": "key",
        "FP_GRPC_CLIENT_CA_FILE": "ca",
        "FP_GRPC_ALLOWED_CLIENT_URIS": "uri",
        "FP_REVOCATION_REDIS_URL_FILE": "redis",
        "FP_JWKS_URL": "http://backend:8000/.well-known/jwks.json",
        "FP_TEMPORAL_HOST": "old",
        "FP_TEMPORAL_API_KEY_FILE": "/run/temporal/token",
    }
    return {
        "kind": "Deployment",
        "metadata": {"name": "probe-a-file-processor"},
        "spec": {
            "replicas": 2,
            "template": {
                "metadata": {"labels": {"app": "original"}},
                "spec": {
                    "containers": [
                        {
                            "name": "file-processor",
                            "env": [{"name": k, "value": v} for k, v in env.items()],
                        }
                    ]
                },
            },
        },
    }


def prepared(**changes):
    processor = _real_runtime_module("networkpolicy_runtime_processor")
    SHA = "a" * 40

    arguments = {
        "image": "local:" + SHA,
        "diagnostic_image": "probe:" + SHA,
        "source_sha": SHA,
        "temporal_endpoint": "temporal:7233",
        "temporal_ca_configmap": "public-ca",
    }
    arguments.update(changes)
    return processor.real_processor_deployment([deployment()], "probe-a", **arguments)


def test_valid_deployment_is_copy_and_wires_temporal():
    from unittest.mock import patch

    processor = _real_runtime_module("networkpolicy_runtime_processor")
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    original = deployment()
    with patch.object(processor, "find", return_value=original):
        result = prepared()
    assert original == deployment()
    assert result["spec"]["replicas"] == 2
    temporal.wire_processor_temporal(
        result,
        dict(
            result="ready",
            endpoint="temporal:7233",
            worker_secret=original["metadata"]["name"],
        ),
    )
    container = result["spec"]["template"]["spec"]["containers"][0]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["FP_TEMPORAL_API_KEY_FILE"] == "/run/netpol-temporal/token"
    assert env["FP_TEMPORAL_TLS_DISABLED"] == "false"


@pytest.mark.parametrize(
    "changes",
    [
        {"source_sha": "bad"},
        {"image": ""},
        {"image": "wrong:tag"},
        {"diagnostic_image": "wrong:tag"},
    ],
)
def test_deployment_rejects_invalid_source_inputs(changes):
    with pytest.raises(ValueError):
        prepared(**changes)


@pytest.mark.parametrize(
    "field,value", [("FP_ENVIRONMENT", "development"), ("FP_GRPC_TLS_KEY_FILE", "")]
)
def test_deployment_preserves_staging_security(field, value):
    from unittest.mock import patch

    processor = _real_runtime_module("networkpolicy_runtime_processor")

    source = deployment()
    next(
        e
        for e in source["spec"]["template"]["spec"]["containers"][0]["env"]
        if e["name"] == field
    )["value"] = value
    with (
        patch.object(processor, "find", return_value=source),
        pytest.raises(ValueError),
    ):
        prepared()


def test_temporal_wire_refuses_unready_or_cleartext():
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    with pytest.raises(ValueError):
        temporal.wire_processor_temporal({}, {"result": "inconclusive"})
    result = prepared()
    next(
        e
        for e in result["spec"]["template"]["spec"]["containers"][0]["env"]
        if e["name"] == "FP_TEMPORAL_TLS_DISABLED"
    )["value"] = "true"
    with pytest.raises(ValueError):
        temporal.wire_processor_temporal(result, {"result": "ready"})


@pytest.mark.parametrize(
    "observed,expected,verdict",
    [
        (
            {"result": "grpc-status", "code": "InvalidArgument"},
            "InvalidArgument",
            "pass",
        ),
        (
            {"result": "grpc-status", "code": "Unauthenticated"},
            "InvalidArgument",
            "fail",
        ),
        *[
            ({"result": "grpc-status", "code": code}, "Unauthenticated", "inconclusive")
            for code in [
                "Unavailable",
                "DeadlineExceeded",
                "Unknown",
                "Internal",
                "Canceled",
                None,
            ]
        ],
    ],
)
def test_status_classification(observed, expected, verdict):
    processor = _real_runtime_module("networkpolicy_runtime_processor")

    assert processor.grpc_probe_verdict(observed, expected) == verdict


def test_token_and_status_reject_invalid_inputs():
    processor = _real_runtime_module("networkpolicy_runtime_processor")
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    with pytest.raises(ValueError):
        processor.processor_token(None, issuer="", audience="a", session_id="jti")
    with pytest.raises(ValueError):
        processor.grpc_probe_verdict({}, "OK")
    signer = temporal.generate_signing_key("key")
    token = processor.processor_token(
        signer, issuer="issuer", audience="audience", session_id="jti", now=1
    )
    assert token.count(".") == 2


def test_ephemeral_certificates():
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    from cryptography import x509

    ca, server, issuer = temporal._credentials("probe-a")
    assert "PRIVATE KEY" not in ca
    assert x509.load_pem_x509_certificate(
        server["tls.crt"].encode()
    ).extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName) == ["temporal", "temporal.probe-a.svc"]
    assert "PRIVATE KEY" in issuer["tls.key"]


@pytest.mark.parametrize("change", ["auth", "internal"])
def test_native_config_fails_closed_on_security_drift(tmp_path, change):
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    config = yaml.safe_load((ROOT / "services/temporal/config.yaml").read_text())
    if change == "auth":
        config["global"]["authorization"]["authorizer"] = ""
    else:
        config["services"]["history"]["rpc"]["bindOnIP"] = "192.0.2.1"
    dest = tmp_path / "services/temporal"
    dest.mkdir(parents=True)
    (dest / "config.yaml").write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        temporal.native_config(tmp_path)


@pytest.mark.parametrize(
    "document",
    [
        "services: {}",
        "services:\n  temporal:\n    image: latest",
        "services:\n  temporal:\n    image: []",
    ],
)
def test_compose_pin_refuses_ambiguity_or_unpinned_image(tmp_path, document):
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    (tmp_path / "docker-compose.full.yml").write_text(document)
    with pytest.raises(ValueError):
        temporal.compose_image(tmp_path, "temporal")


@pytest.mark.parametrize(
    "namespace,python_image,postgres_image",
    [("INVALID", "unused", "unused"), ("probe-a", "unpinned", "unpinned")],
)
def test_fixture_rejects_namespace_and_unpinned_images(
    namespace, python_image, postgres_image
):
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    with pytest.raises(ValueError):
        temporal.fixture_objects(ROOT, namespace, python_image, postgres_image, None)


def test_fixture_rejects_other_postgres_pin():
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")

    python_image, postgres_image = pins()
    with pytest.raises(ValueError):
        temporal.fixture_objects(
            ROOT,
            "probe-a",
            python_image,
            postgres_image.replace("pgvector/pgvector", "other/image"),
            None,
        )


def sample_deployment():
    env = {
        "FP_GRPC_ALLOWED_CLIENT_URIS": "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway",
        "FP_JWKS_URL": "http://probe-a-backend:8000/.well-known/jwks.json",
        "FP_JWT_ISSUER": "https://fixture.example",
        "FP_JWT_AUDIENCE": "fixture",
        "FP_JWKS_REFRESH_INTERVAL": "300",
    }
    return {
        "metadata": {"name": "probe-a-file-processor"},
        "spec": {
            "replicas": 2,
            "selector": {"matchLabels": {"app": "fp"}},
            "template": {
                "spec": {
                    "serviceAccountName": "probe-a-fp",
                    "containers": [
                        {
                            "name": "file-processor",
                            "env": [{"name": k, "value": v} for k, v in env.items()],
                        }
                    ],
                }
            },
        },
    }


def run_phase(fault=""):
    import base64
    import json
    import subprocess
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    pod = m.Pod("probe-a", "fixture", ip="127.0.0.1", uid="fixture")
    pods = {k: pod for k in ["a-fp", "a-redis", "a-backend"]}
    published = []
    revoked = set()
    counters = {"publish": 0, "replica": 0}
    declaration = sample_deployment()
    overrides = {
        "mtls": ("FP_INTERNAL_HTTP_MTLS_ENABLED", "true"),
        "identity": ("FP_GRPC_ALLOWED_CLIENT_URIS", "one,two"),
        "scheme": ("FP_JWKS_URL", "https://backend:8000/.well-known/jwks.json"),
        "port": ("FP_JWKS_URL", "http://backend:9000/.well-known/jwks.json"),
        "path": ("FP_JWKS_URL", "http://backend:8000/wrong"),
        "refresh": ("FP_JWKS_REFRESH_INTERVAL", "301"),
    }
    if fault in overrides:
        key, value = overrides[fault]
        declaration["spec"]["template"]["spec"]["containers"][0]["env"] = [
            e
            for e in declaration["spec"]["template"]["spec"]["containers"][0]["env"]
            if e["name"] != key
        ] + [{"name": key, "value": value}]

    def find(resources, kind, name):
        if kind == "ServiceAccount":
            return {"kind": kind, "metadata": {"name": name}}
        return {"spec": {"template": {"metadata": {"labels": {"gateway": "true"}}}}}

    def publish(*args):
        counters["publish"] += 1
        if fault == "publish" + str(counters["publish"]):
            return {"result": "error"}
        published[:] = [k["kid"] for k in json.loads(args[1])["keys"]]
        return {"result": "published"}

    def replicas(*args):
        counters["replica"] += 1
        items = [
            {
                "uid": f"uid-{i}",
                "name": f"fp-{i}",
                "ip": f"127.0.0.{i + 1}",
                "container_id": str(i),
                "image_id": str(i),
                "restarts": 0,
            }
            for i in range(2)
        ]
        if fault == "replica-count":
            return items[:1]
        if fault == "restart" and counters["replica"] == 2:
            items[0]["restarts"] = 1
        return items

    def decode(segment):
        return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))

    def call(namespace, replica, server, token):
        header, claims, _ = token.split(".")
        denied = (
            decode(header)["kid"] not in published or decode(claims)["jti"] in revoked
        )
        return {
            "result": "grpc-status",
            "code": "OK"
            if fault == "status"
            else "Unauthenticated"
            if denied
            else "InvalidArgument",
        }

    def redis(*args, **kwargs):
        config = json.loads(kwargs["stdin"])
        if config.get("action") == "check":
            return {"result": "error" if fault == "unrevoked" else "unrevoked"}
        revoked.add(config["jti"])
        return {"result": "error" if fault == "revocation" else "revoked"}

    def command(argv, **kwargs):
        if fault == "network-command":
            raise subprocess.CalledProcessError(1, argv, output="private-output")
        if "redis-ping" in argv:
            result = {"result": "redis-pong", "auth": "+OK"}
        else:
            result = {"result": "http", "status": "200"}
        if fault == "network-result":
            result = {"result": "timeout"}
        return SimpleNamespace(stdout=json.dumps(result))

    def kube(*args, **kwargs):
        if fault == "cleanup" and "delete" in args:
            raise subprocess.CalledProcessError(1, ["kubectl"])
        if fault == "rollout" and "rollout" in args:
            raise subprocess.CalledProcessError(1, ["kubectl"])

    monotonic = (
        [0, 541]
        if fault == "revocation-expiry"
        else [0, 1, 2, 543]
        if fault == "new-expiry"
        else [0, 1, 2, 3]
    )
    worker_resource = m._object("Secret", "worker", "probe-a")
    with ExitStack() as stack:
        setup = stack.enter_context(
            patch.object(
                m,
                "bootstrap_temporal",
                return_value={
                    "result": "ready",
                    "endpoint": "temporal:7233",
                    "ca_configmap": "ca",
                    "worker_secret": worker_resource["metadata"]["name"],
                },
            )
        )
        stack.enter_context(
            patch.object(m, "bootstrap_nats", return_value="nats://fixture")
        )
        stack.enter_context(
            patch.object(m, "real_processor_deployment", return_value=declaration)
        )
        stack.enter_context(patch.object(m, "wire_processor_temporal"))
        stack.enter_context(patch.object(m, "materialize_processor_secrets"))
        stack.enter_context(patch.object(m, "grpc_credentials", return_value=({}, {})))
        stack.enter_context(patch.object(m, "find", side_effect=find))
        stack.enter_context(patch.object(m, "apply_objects"))
        stack.enter_context(patch.object(m, "publish_jwks", side_effect=publish))
        stack.enter_context(patch.object(m, "replica_state", side_effect=replicas))
        stack.enter_context(patch.object(m, "call_processor", side_effect=call))
        stack.enter_context(patch.object(m, "run_in_pod", side_effect=redis))
        stack.enter_context(patch.object(m, "run_command", side_effect=command))
        stack.enter_context(patch.object(m, "kubectl", side_effect=kube))
        stack.enter_context(patch.object(m.time, "monotonic", side_effect=monotonic))
        stack.enter_context(patch.object(m.time, "sleep"))
        result = m.actual_processor_phase(
            ROOT,
            {"probe-a": ([], []), "probe-b": ([], [])},
            pods,
            {"probe-a": "private"},
            python_image="python",
            processor_image="fp",
            diagnostic_image="probe",
            source_sha="a" * 40,
        )
        assert setup.call_count == 1
    return result


def test_full_orchestration_uses_both_a_replicas_and_preserves_scope():
    result = run_phase()
    assert result["verdict"] == "pass"
    assert len(result["checks"]) == 24
    assert len(result["replicas"]) == 2
    assert result["replica_state_unchanged"] is True
    assert result["real_probe_b"].startswith("not_run")
    assert all("private" not in str(row) for row in result["checks"])


@pytest.mark.parametrize(
    "fault",
    [
        "mtls",
        "identity",
        "scheme",
        "port",
        "path",
        "refresh",
        "publish1",
        "publish2",
        "publish3",
        "replica-count",
        "restart",
        "unrevoked",
        "revocation",
        "revocation-expiry",
        "new-expiry",
        "network-command",
        "network-result",
        "cleanup",
        "rollout",
    ],
)
def test_every_failed_precondition_is_inconclusive(fault):
    result = run_phase(fault)
    assert result["verdict"] == "inconclusive"
    assert "private-output" not in str(result)
    assert "replica_state_unchanged" not in result


def test_wrong_actual_status_cannot_pass():
    assert run_phase("status")["verdict"] == "fail"


def test_nats_native_bootstrap_uses_tracked_image_and_authenticated_reply():
    from types import SimpleNamespace
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    with (
        patch.object(m, "apply_objects") as applied,
        patch.object(m, "kubectl"),
        patch.object(
            m, "run_command", return_value=SimpleNamespace(stdout='{"result":"ready"}')
        ),
    ):
        url = m.bootstrap_nats(ROOT, "probe-a", "python")
    assert url.startswith("nats://netpol:")
    objects = applied.call_args.args[0]
    assert objects[-1]["spec"]["containers"][0]["image"] == m.compose_image(
        ROOT, "nats"
    )
    with (
        patch.object(m, "apply_objects"),
        patch.object(m, "kubectl"),
        patch.object(
            m, "run_command", return_value=SimpleNamespace(stdout='{"result":"failed"}')
        ),
        pytest.raises(ValueError),
    ):
        m.bootstrap_nats(ROOT, "probe-a", "python")


def secret_deployment():
    temporal = _real_runtime_module("networkpolicy_runtime_temporal")
    original_volume = temporal.secret_volume("secret", "original")
    original_volume["secret"]["items"] = [
        {"key": name, "path": name} for name in ["cert", "key", "ca", "public"]
    ]
    values = {
        "FP_GRPC_TLS_CERT_FILE": "/secret/cert",
        "FP_GRPC_TLS_KEY_FILE": "/secret/key",
        "FP_GRPC_CLIENT_CA_FILE": "/secret/ca",
        "FP_RSA_PUBLIC_KEY_FILE": "/secret/public",
    }
    return {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "file-processor",
                            "env": [{"name": k, "value": v} for k, v in values.items()],
                            "volumeMounts": [
                                {"name": "secret", "mountPath": "/secret"}
                            ],
                        }
                    ],
                    "volumes": [
                        {"name": "empty", "emptyDir": {}},
                        temporal.secret_volume("netpol-temporal-worker", "worker"),
                        original_volume,
                    ],
                }
            }
        }
    }


def test_secret_mapping_retains_rendered_names_and_fields():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    with patch.object(m, "apply_objects") as applied:
        m.materialize_processor_secrets(
            secret_deployment(),
            "probe-a",
            {"FP_RSA_PUBLIC_KEY_FILE": "public"},
            {"tls.crt": "cert", "tls.key": "key", "ca.crt": "ca"},
        )
    assert applied.call_args.args[0][0]["stringData"] == {
        "cert": "cert",
        "key": "key",
        "ca": "ca",
        "public": "public",
    }


@pytest.mark.parametrize("fault", ["unmapped", "missing"])
def test_secret_mapping_fails_closed(fault):
    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    deployment = secret_deployment()
    values = {}
    if fault == "unmapped":
        deployment["spec"]["template"]["spec"]["volumes"][-1]["secret"]["items"].append(
            {"key": "extra", "path": "extra"}
        )
    else:
        values = {}
    if fault == "unmapped":
        values = {"FP_RSA_PUBLIC_KEY_FILE": "public"}
    with pytest.raises(ValueError):
        m.materialize_processor_secrets(
            deployment,
            "probe-a",
            values,
            {"tls.crt": "cert", "tls.key": "key", "ca.crt": "ca"},
        )


def test_replica_inventory_keeps_exact_running_container():
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    pod = {
        "metadata": {"name": "fp", "uid": "uid"},
        "status": {
            "podIP": "127.0.0.1",
            "containerStatuses": [
                {
                    "name": "file-processor",
                    "ready": True,
                    "containerID": "container",
                    "imageID": "image",
                    "restartCount": 0,
                }
            ],
        },
    }
    with patch.object(m, "kubectl_json", return_value={"items": [{"status": {}}, pod]}):
        assert m.replica_state("probe-a", {"app": "fp"}) == [
            {
                "name": "fp",
                "uid": "uid",
                "ip": "127.0.0.1",
                "container_id": "container",
                "image_id": "image",
                "restarts": 0,
            }
        ]
    pod["status"]["containerStatuses"][0]["ready"] = False
    with (
        patch.object(m, "kubectl_json", return_value={"items": [pod]}),
        pytest.raises(ValueError),
    ):
        m.replica_state("probe-a", {})


def test_client_stdout_nonobject_is_setup_error():
    from types import SimpleNamespace
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    with patch.object(m, "run_command", return_value=SimpleNamespace(stdout="[]")):
        assert m.call_processor("probe-a", {"ip": "127.0.0.1"}, "fixture", "token") == {
            "result": "setup-error"
        }


def test_client_returns_only_safe_status_object():
    from types import SimpleNamespace
    from unittest.mock import patch

    m = _real_runtime_module("networkpolicy_runtime_real_fp")

    with patch.object(
        m,
        "run_command",
        return_value=SimpleNamespace(
            stdout='{"result":"grpc-status","code":"InvalidArgument"}'
        ),
    ):
        assert m.call_processor("probe-a", {"ip": "127.0.0.1"}, "fixture", "token") == {
            "result": "grpc-status",
            "code": "InvalidArgument",
        }


def git(root, *args):
    import shlex
    import shutil
    import subprocess

    return subprocess.run(
        ["/bin/bash", "-s"],
        input=shlex.join([shutil.which("git"), "-C", str(root), *args]),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def committed(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "main.go").write_text("package main\n")
    (tmp_path / ".gitignore").write_text("cache/\n")
    git(tmp_path, "add", ".")
    git(
        tmp_path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    return tmp_path


def check(root):
    import os
    import subprocess

    script = (ROOT / "scripts/k8s/networkpolicy_runtime_proof.sh").read_text()
    guard = script[
        script.index("require_clean_source() {") : script.index(
            "build_real_processor_images() {"
        )
    ]
    program = (
        'set -euo pipefail\nlog() { printf "%s\\n" "$*" >&2; }\n'
        + guard
        + "\nrequire_clean_source\n"
    )
    return subprocess.run(
        ["/bin/bash", "-s"],
        input=program,
        env={**os.environ, "ROOT_DIR": str(root)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_source_and_ignored_cache_allowed(committed):
    (committed / "cache").mkdir()
    (committed / "cache/private.go").write_text("synthetic ignored content")
    assert check(committed).returncode == 0
    # Docker context must come from committed archive, not ignored worktree data.
    script = (ROOT / "scripts/k8s/networkpolicy_runtime_proof.sh").read_text()
    assert 'git -C "$ROOT_DIR" archive --format=tar "$SOURCE_SHA"' in script
    assert '-t "$FP_IMAGE" "$build_source"' in script
    assert '-t "$DIAGNOSTIC_IMAGE" "$build_source"' in script


@pytest.mark.parametrize("dirty", ["tracked", "untracked", "staged", "index-only"])
def test_dirty_source_is_rejected_without_filenames(committed, dirty):
    name = "untracked-sensitive-name.go" if dirty == "untracked" else "main.go"
    (committed / name).write_text("package altered\n")
    if dirty in {"staged", "index-only"}:
        git(committed, "add", name)
    if dirty == "index-only":
        (committed / name).write_text("package main\n")
    result = check(committed)
    assert result.returncode != 0
    assert "committed clean source tree" in result.stderr
    assert name not in result.stdout + result.stderr
    assert "package altered" not in result.stdout + result.stderr


def test_real_runtime_loader_uses_the_current_proof_directory(monkeypatch):
    import sys

    monkeypatch.setattr(
        sys, "path", [entry for entry in sys.path if entry != str(PROBE_DIR)]
    )
    module = _real_runtime_module("networkpolicy_runtime_processor")
    assert sys.path[0] == str(PROBE_DIR)
    assert module.__name__ == "networkpolicy_runtime_processor"


@pytest.mark.parametrize("failed_command", ["diff", "ls-files"])
def test_real_source_guard_rejects_git_inspection_failure(tmp_path, failed_command):
    import os
    import subprocess

    script = PROOF.read_text()
    guard = script[
        script.index("require_clean_source() {") : script.index(
            "build_real_processor_images() {"
        )
    ]
    shim = (
        'git() { case "$*" in *"'
        + failed_command
        + '"*) return 2;; *) return 0;; esac; }\n'
    )
    program = (
        'set -euo pipefail\nlog() { printf "%s\\n" "$*" >&2; }\n'
        + shim
        + guard
        + "\nrequire_clean_source\n"
    )
    observed = subprocess.run(
        ["/bin/bash", "-s"],
        input=program,
        env={**os.environ, "ROOT_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert observed.returncode != 0
    assert observed.stdout == ""


@pytest.mark.parametrize(
    "failure",
    [
        "",
        "transient",
        "missing",
        "duplicate",
        "save",
        "import",
        "inspect",
        "bad-id",
        "cri",
        "json",
        "mismatch",
        "second",
    ],
)
def test_native_image_import_fails_closed_and_verifies_both_ids(tmp_path, failure):
    import os
    import subprocess

    source = PROOF.read_text()
    loader = source[
        source.index("load_real_processor_images() {") : source.index("main() {")
    ]
    shim = r"""
set -euo pipefail
CLUSTER_NAME=fixture
FP_IMAGE=ue-netpol-fp:fixture
DIAGNOSTIC_IMAGE=ue-netpol-diagnostic:fixture
docker() {
  printf '%s\n' "$*" >> "$WORK_DIR/calls"
  case "$1 $2" in
    'save --output')
      [[ "$FAILURE" != save ]] || return 31
      printf 'fixture archive' > "$3" ;;
    'exec -i')
      [[ "$*" == 'exec -i fixture-control-plane ctr --namespace=k8s.io images import --local --all-platforms --digests --snapshotter=overlayfs -' ]]
      [[ "$(cat)" == 'fixture archive' ]]
      [[ "$FAILURE" != import ]] || return 32 ;;
    'image inspect')
      [[ "$FAILURE" != inspect ]] || return 33
      if [[ "$FAILURE" == bad-id ]]; then printf 'invalid'; else printf '%s' "$IMAGE_ID"; fi ;;
    'exec fixture-control-plane')
      [[ "$FAILURE" != cri ]] || return 34
      if [[ "$4" == images ]]; then
        [[ "$3 $4 $5 $6" == 'crictl images --output json' ]]
        if [[ "$FAILURE" == json ]]; then printf 'invalid';
        elif [[ "$FAILURE" == missing || ( "$FAILURE" == transient && ! -f "$WORK_DIR/seen" ) ]]; then
          touch "$WORK_DIR/seen"; printf '{"images":[]}'
        elif [[ "$FAILURE" == mismatch ]]; then
          printf '{"images":[{"id":"wrong","repoTags":["docker.io/library/%s"]}]}' "$FP_IMAGE"
        elif [[ "$FAILURE" == duplicate ]]; then
          printf '{"images":[{"id":"%s","repoTags":["docker.io/library/%s"]},{"id":"%s","repoTags":["docker.io/library/%s"]}]}' "$IMAGE_ID" "$FP_IMAGE" "$IMAGE_ID" "$FP_IMAGE"
        else printf '{"images":[{"id":"%s","repoTags":["docker.io/library/%s","docker.io/library/%s"]}]}' "$IMAGE_ID" "$FP_IMAGE" "$DIAGNOSTIC_IMAGE"; fi
      else
        [[ "$3 $4 $5 $6" == 'crictl inspecti --output json' ]]
        if [[ "$FAILURE" == second && "$7" == "$DIAGNOSTIC_IMAGE" ]]; then
          printf '{"status":{"id":"wrong"}}'
        else printf '{"status":{"id":"%s"}}' "$IMAGE_ID"; fi
      fi ;;
    *) return 35 ;;
  esac
}
uv() { "$TEST_PYTHON" "${@:4}"; }
sleep() { printf "wait\n" >> "$WORK_DIR/waits"; }
"""
    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=shim + loader + "\nload_real_processor_images\nprintf completed\n",
        env={
            **os.environ,
            "WORK_DIR": str(tmp_path),
            "FAILURE": failure,
            "IMAGE_ID": "sha256:" + "a" * 64,
            "TEST_PYTHON": sys.executable,
        },
        text=True,
        capture_output=True,
        check=False,
    )
    success = failure in {"", "transient"}
    assert (result.returncode == 0) == success
    assert ("completed" in result.stdout) == success
    if success:
        calls = (tmp_path / "calls").read_text()
        assert calls.count("crictl inspecti --output json") == 2
        assert "ue-netpol-fp:fixture" in calls
        assert "ue-netpol-diagnostic:fixture" in calls
        assert not (tmp_path / "real-processor-images.tar").exists()
    assert "kind load docker-image" not in source
    assert "    load_real_processor_images\n" in source

    if failure in {"missing", "transient"}:
        assert (tmp_path / "waits").read_text().splitlines() == ["wait"] * (
            29 if failure == "missing" else 1
        )
    else:
        assert not (tmp_path / "waits").exists()
