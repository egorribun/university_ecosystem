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
