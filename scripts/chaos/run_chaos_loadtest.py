#!/usr/bin/env python3
"""Chaos engineering load test orchestrator.

Orchestrates Chaos Mesh fault injection scenarios alongside HTTP load generation
to monitor HTTP availability and latency under failure and recovery.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import math
import pathlib
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from types import FrameType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger("chaos_loadtest")

_CHAOS_API_VERSION = "chaos-mesh.org/v1alpha1"
_CHAOS_RESOURCES = {"PodChaos": "podchaos", "NetworkChaos": "networkchaos"}
_RUN_ANNOTATION = "university-ecosystem.io/chaos-loadtest-run-id"
_DNS_LABEL = re.compile(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?")
_DNS_SUBDOMAIN = re.compile(
    r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*"
)
_KUBECTL_TIMEOUT = 30.0
_CLEANUP_SUBPROCESS_BUDGET = 24.0
_MAX_FAULTS = 16


class _TerminationRequested(BaseException):
    """Exit after bounded cleanup when the CLI receives SIGTERM."""


@dataclass(frozen=True)
class _FaultIdentity:
    kind: str
    namespace: str
    name: str
    uid: str = ""


@dataclass
class PhaseMetrics:
    phase_name: str
    duration_sec: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    status_codes: dict[int, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0

    @property
    def displayed_success_rate(self) -> str:
        return f"{self.success_rate:.2f}%" if self.total_requests else "N/A"

    @property
    def avg_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    @property
    def p95_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = math.ceil(0.95 * len(sorted_lats)) - 1
        idx = max(0, min(idx, len(sorted_lats) - 1))
        return sorted_lats[idx]


class ChaosLoadTestOrchestrator:
    def __init__(
        self,
        manifest_path: str,
        duration: int,
        target_url: str,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        self.manifest_path = pathlib.Path(manifest_path)
        self.duration = float(duration)
        self.target_url = target_url
        self.dry_run = dry_run
        self.verbose = verbose
        self.results: dict[str, PhaseMetrics] = {}
        self._kubectl_bin = ""
        self._context = ""
        self._server = ""
        self._server_origin = ""
        self._server_sha256 = ""
        self._run_id = ""
        self._owned_faults: list[_FaultIdentity] = []
        self._pending_fault: _FaultIdentity | None = None
        self._cleanup_in_progress = False
        self._shutdown_requested = False
        self._kubectl_in_progress = False
        self._execution_task: asyncio.Task[Any] | None = None

    def _request_termination(self, _signum: int, _frame: FrameType | None) -> None:
        self._shutdown_requested = True
        if self._cleanup_in_progress:
            return
        if self._kubectl_in_progress:
            raise _TerminationRequested
        if self._execution_task is not None:
            self._execution_task.cancel()

    def _run_kubectl(
        self,
        command: list[str],
        *,
        timeout: float,
        input: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self._kubectl_in_progress = True
        try:
            if self._shutdown_requested and not self._cleanup_in_progress:
                raise _TerminationRequested
            return subprocess.run(  # noqa: S603
                command,
                input=input,
                capture_output=True,
                text=True,
                check=check,
                timeout=timeout,
            )
        finally:
            self._kubectl_in_progress = False

    def setup_logging(self) -> None:
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def _send_http_request(
        self, url: str, timeout: float = 5.0
    ) -> tuple[int, float, str | None]:
        start_time = time.monotonic()
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return 0, 0.0, f"Unsupported URL scheme: {url}"

        req = Request(url, headers={"User-Agent": "ChaosLoadTest/1.0"})  # noqa: S310
        try:
            # Operator-supplied load-test target; URL structure and scheme are
            # constrained above, so file/data handlers cannot be reached.
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                elapsed_ms = (time.monotonic() - start_time) * 1000.0
                return resp.status, elapsed_ms, None
        except HTTPError as err:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            return err.code, elapsed_ms, str(err)
        except (URLError, OSError, TimeoutError) as err:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            return 0, elapsed_ms, str(err)

    async def _run_http_load(
        self, phase_name: str, duration_sec: float, concurrency: int = 5
    ) -> PhaseMetrics:
        metrics = PhaseMetrics(phase_name=phase_name)
        start_wall = time.monotonic()

        async def worker() -> None:
            while (time.monotonic() - start_wall) < duration_sec:
                loop = asyncio.get_running_loop()
                try:
                    status, lat, err = await loop.run_in_executor(
                        None, self._send_http_request, self.target_url
                    )
                except (OSError, RuntimeError) as exc:
                    status, lat, err = 0, 0.0, str(exc)

                metrics.total_requests += 1
                metrics.latencies_ms.append(lat)
                if status in (200, 201, 202, 204):
                    metrics.successful_requests += 1
                else:
                    metrics.failed_requests += 1
                    if err:
                        metrics.errors.append(err)
                metrics.status_codes[status] = metrics.status_codes.get(status, 0) + 1
                await asyncio.sleep(0.1)

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*workers)
        metrics.duration_sec = time.monotonic() - start_wall
        return metrics

    def phase1_preflight(self) -> bool:
        logger.info("=== Phase 1/7: Pre-flight Health & Environment Check ===")
        if not self.manifest_path.exists():
            logger.error("Manifest file not found: %s", self.manifest_path)
            return False

        logger.info("Found manifest: %s", self.manifest_path)

        kubectl_bin = shutil.which("kubectl")
        if not kubectl_bin:
            if self.dry_run:
                logger.warning(
                    "[DRY-RUN] 'kubectl' binary not found in PATH, skipping cluster check."
                )
            else:
                logger.error(
                    "'kubectl' binary not found in PATH. Install kubectl or use --dry-run."
                )
                return False
        else:
            if self.dry_run:
                logger.info("[DRY-RUN] kubectl binary verified: %s", kubectl_bin)
            else:
                try:
                    res = self._run_kubectl(
                        [kubectl_bin, "version", "--client"],
                        check=False,
                        timeout=_KUBECTL_TIMEOUT,
                    )
                    logger.info(
                        "kubectl client version check exit code: %d", res.returncode
                    )
                except (subprocess.SubprocessError, OSError) as kubectl_error:
                    logger.error(
                        "Failed executing kubectl (%s)", type(kubectl_error).__name__
                    )
                    return False

        status, lat, err = self._send_http_request(self.target_url, timeout=3.0)
        logger.info(
            "Target URL health check [%s]: status=%d, latency=%.2fms",
            self.target_url,
            status,
            lat,
        )
        if status == 0 and not self.dry_run:
            logger.warning(
                "Target URL unreachable during pre-flight: %s. Continuing with caution.",
                err,
            )
        return True

    async def phase2_baseline_load(self) -> PhaseMetrics:
        logger.info("=== Phase 2/7: Baseline Load Injection ===")
        baseline_dur = min(5.0, max(2.0, self.duration / 3.0))
        metrics = await self._run_http_load("Phase 2: Baseline", baseline_dur)
        logger.info(
            "Baseline completed: %d requests, %s success rate, avg latency: %.2fms",
            metrics.total_requests,
            metrics.displayed_success_rate,
            metrics.avg_latency,
        )
        self.results["phase2"] = metrics
        return metrics

    def _bound_kubectl(self) -> list[str]:
        return [
            self._kubectl_bin,
            f"--context={self._context}",
            f"--server={self._server}",
        ]

    def _log_manual_fault(self, identity: _FaultIdentity, reason: str) -> None:
        logger.error(
            "%s for %s %s/%s in context %s; server-origin=%s server-sha256=%s "
            "uid=%s run-id=%s; manual inspection is required (run-id is not ownership proof)",
            reason,
            identity.kind,
            identity.namespace,
            identity.name,
            self._context,
            self._server_origin,
            self._server_sha256,
            identity.uid or "unknown",
            self._run_id,
        )

    def _prepare_faults(self) -> list[tuple[_FaultIdentity, dict[str, Any]]]:
        config_result = self._run_kubectl(
            [self._kubectl_bin, "config", "view", "--minify", "-o", "json"],
            timeout=_KUBECTL_TIMEOUT,
        )
        config = json.loads(config_result.stdout)
        context_name = config.get("current-context")
        if not isinstance(context_name, str) or not context_name:
            raise ValueError("No current Kubernetes context")
        contexts = [
            entry
            for entry in config.get("contexts", [])
            if entry.get("name") == context_name
        ]
        if len(contexts) != 1:
            raise ValueError("Cannot determine Kubernetes context")
        context = contexts[0].get("context", {})
        clusters = [
            entry
            for entry in config.get("clusters", [])
            if entry.get("name") == context.get("cluster")
        ]
        if len(clusters) != 1:
            raise ValueError("Cannot determine Kubernetes cluster")
        server = clusters[0].get("cluster", {}).get("server")
        if not isinstance(server, str):
            raise ValueError("No Kubernetes API server")
        parsed_server = urlsplit(server)
        if (
            parsed_server.scheme not in {"http", "https"}
            or not parsed_server.hostname
            or parsed_server.username is not None
            or parsed_server.password is not None
            or parsed_server.query
            or parsed_server.fragment
        ):
            raise ValueError("Invalid Kubernetes API server")
        default_namespace = context.get("namespace") or "default"
        if (
            not isinstance(default_namespace, str)
            or len(default_namespace) > 63
            or _DNS_LABEL.fullmatch(default_namespace) is None
        ):
            raise ValueError("Invalid Kubernetes namespace")
        self._context = context_name
        self._server = server
        self._server_origin = f"{parsed_server.scheme}://{parsed_server.netloc}"
        self._server_sha256 = hashlib.sha256(server.encode("utf-8")).hexdigest()

        try:
            parse_result = self._run_kubectl(
                [
                    *self._bound_kubectl(),
                    f"--namespace={default_namespace}",
                    "create",
                    "--dry-run=client",
                    "-f",
                    str(self.manifest_path),
                    "-o",
                    "json",
                ],
                timeout=_KUBECTL_TIMEOUT,
            )
        except (subprocess.SubprocessError, OSError):
            logger.error(
                "Manifest parsing failed; live manifests must use the current context namespace %s",
                default_namespace,
            )
            raise
        decoder = json.JSONDecoder()
        source = parse_result.stdout
        index = 0
        documents: list[dict[str, Any]] = []
        while index < len(source):
            index = len(source) - len(source[index:].lstrip())
            if index == len(source):
                break
            document, index = decoder.raw_decode(source, index)
            if not isinstance(document, dict) or len(documents) >= _MAX_FAULTS:
                raise ValueError("Invalid or too many chaos resources")
            documents.append(document)
        if not documents:
            raise ValueError("No chaos resources in manifest")

        self._run_id = secrets.token_hex(16)
        identities: set[tuple[str, str, str]] = set()
        prepared: list[tuple[_FaultIdentity, dict[str, Any]]] = []
        for document in documents:
            kind = document.get("kind")
            metadata = document.get("metadata")
            if (
                document.get("apiVersion") != _CHAOS_API_VERSION
                or kind not in _CHAOS_RESOURCES
                or not isinstance(metadata, dict)
            ):
                raise ValueError("Only supported Chaos Mesh resources may be created")
            name = metadata.get("name")
            namespace = metadata.get("namespace") or default_namespace
            if (
                not isinstance(name, str)
                or len(name) > 253
                or _DNS_SUBDOMAIN.fullmatch(name) is None
                or not isinstance(namespace, str)
                or len(namespace) > 63
                or _DNS_LABEL.fullmatch(namespace) is None
                or namespace != default_namespace
                or "generateName" in metadata
            ):
                raise ValueError("Chaos resource has invalid identity")
            identity = (kind, namespace, name)
            if identity in identities:
                raise ValueError("Duplicate chaos resource identity")
            identities.add(identity)
            annotations = metadata.setdefault("annotations", {})
            if not isinstance(annotations, dict) or _RUN_ANNOTATION in annotations:
                raise ValueError("Chaos resource has invalid run annotations")
            annotations[_RUN_ANNOTATION] = self._run_id
            metadata["namespace"] = namespace
            prepared.append((_FaultIdentity(kind, namespace, name), document))
        return prepared

    def phase3_apply_fault(self) -> bool:
        logger.info("=== Phase 3/7: Apply Chaos Fault Injection ===")
        if self.dry_run:
            logger.info(
                "[DRY-RUN] Would create chaos resources from %s", self.manifest_path
            )
            return True

        self._kubectl_bin = shutil.which("kubectl") or "kubectl"
        try:
            faults = self._prepare_faults()
            for identity, document in faults:
                self._pending_fault = identity
                res = self._run_kubectl(
                    [
                        *self._bound_kubectl(),
                        f"--namespace={identity.namespace}",
                        "create",
                        "-f",
                        "-",
                        "-o",
                        "json",
                    ],
                    input=json.dumps(document),
                    timeout=_KUBECTL_TIMEOUT,
                )
                created = json.loads(res.stdout)
                metadata = created.get("metadata", {})
                expected_annotations = document["metadata"]["annotations"]
                annotations = metadata.get("annotations", {})
                uid = metadata.get("uid")
                if (
                    created.get("apiVersion") != _CHAOS_API_VERSION
                    or created.get("kind") != identity.kind
                    or metadata.get("namespace") != identity.namespace
                    or metadata.get("name") != identity.name
                    or not isinstance(annotations, dict)
                    or annotations.get(_RUN_ANNOTATION)
                    != expected_annotations[_RUN_ANNOTATION]
                    or not isinstance(uid, str)
                    or not uid
                ):
                    raise ValueError(
                        "Create response did not confirm resource identity"
                    )
                self._owned_faults.append(
                    _FaultIdentity(
                        identity.kind, identity.namespace, identity.name, uid
                    )
                )
                self._pending_fault = None
                logger.info(
                    "Created chaos resource %s/%s", identity.namespace, identity.name
                )
            return True
        except (
            subprocess.SubprocessError,
            OSError,
            ValueError,
            TypeError,
            AttributeError,
        ) as err:
            logger.error(
                "Failed to create chaos fault manifest (%s)", type(err).__name__
            )
            return False

    async def phase4_monitor_fault(self) -> PhaseMetrics:
        logger.info(
            "=== Phase 4/7: Monitor System Behaviour Under Fault (%ds) ===",
            int(self.duration),
        )
        metrics = await self._run_http_load("Phase 4: Fault Injection", self.duration)
        logger.info(
            "Fault phase completed: %d requests, %s success rate, avg latency: %.2fms",
            metrics.total_requests,
            metrics.displayed_success_rate,
            metrics.avg_latency,
        )
        self.results["phase4"] = metrics
        return metrics

    def phase5_remove_fault(self) -> bool:
        logger.info("=== Phase 5/7: Remove Fault Injection ===")
        if self.dry_run:
            logger.info("[DRY-RUN] Would remove this run's chaos resources")
            return True

        success = True
        remaining: list[_FaultIdentity] = []
        awaiting: list[_FaultIdentity] = []
        timeout = (
            _CLEANUP_SUBPROCESS_BUDGET / (2 * len(self._owned_faults))
            if self._owned_faults
            else 0.0
        )
        for identity in self._owned_faults:
            resource = _CHAOS_RESOURCES[identity.kind]
            path = f"/apis/{_CHAOS_API_VERSION}/namespaces/{identity.namespace}/{resource}/{identity.name}"
            options = {
                "apiVersion": "v1",
                "kind": "DeleteOptions",
                "preconditions": {"uid": identity.uid},
            }
            try:
                self._run_kubectl(
                    [*self._bound_kubectl(), "delete", f"--raw={path}", "-f", "-"],
                    input=json.dumps(options),
                    timeout=timeout,
                )
                awaiting.append(identity)
            except (subprocess.SubprocessError, OSError) as err:
                self._log_manual_fault(
                    identity,
                    f"Failed to remove or verify chaos resource ({type(err).__name__})",
                )
                remaining.append(identity)
                success = False
        for identity in awaiting:
            resource = _CHAOS_RESOURCES[identity.kind]
            try:
                self._run_kubectl(
                    [
                        *self._bound_kubectl(),
                        f"--namespace={identity.namespace}",
                        "wait",
                        "--for=delete",
                        f"{resource}.chaos-mesh.org/{identity.name}",
                        f"--timeout={timeout * 0.8:.3f}s",
                    ],
                    timeout=timeout,
                )
                logger.info(
                    "Removed chaos resource %s/%s", identity.namespace, identity.name
                )
            except (subprocess.SubprocessError, OSError) as err:
                self._log_manual_fault(
                    identity,
                    f"Failed to remove or verify chaos resource ({type(err).__name__})",
                )
                remaining.append(identity)
                success = False
        self._owned_faults = remaining
        if self._pending_fault is not None:
            self._log_manual_fault(self._pending_fault, "Create outcome is unknown")
            success = False
        return success

    async def phase6_verify_recovery(self) -> PhaseMetrics:
        logger.info("=== Phase 6/7: Check Post-Fault Health & Load ===")
        poll_start = time.monotonic()
        recovered = False
        max_wait = 15.0

        while (time.monotonic() - poll_start) < max_wait:
            status, _lat, _err = self._send_http_request(self.target_url, timeout=2.0)
            if status in (200, 201, 202, 204):
                recovered = True
                break
            if self.dry_run:
                break
            await asyncio.sleep(1.0)

        if recovered:
            logger.info("System health endpoint responded successfully post-fault.")
        elif self.dry_run:
            logger.info("[DRY-RUN] Post-fault health response not required.")
        else:
            logger.warning("System recovery check timed out after %.1fs.", max_wait)

        metrics = await self._run_http_load("Phase 6: Recovery Verification", 3.0)
        logger.info(
            "Recovery verification load test: %d requests, %s success rate",
            metrics.total_requests,
            metrics.displayed_success_rate,
        )
        self.results["phase6"] = metrics
        return metrics

    def phase7_assert_and_report(self) -> bool:
        logger.info("=== Phase 7/7: Assert Recovery Availability & Summary Report ===")
        p2 = self.results.get("phase2", PhaseMetrics("Phase 2"))
        p4 = self.results.get("phase4", PhaseMetrics("Phase 4"))
        p6 = self.results.get("phase6", PhaseMetrics("Phase 6"))

        total_all_reqs = p2.total_requests + p4.total_requests + p6.total_requests
        total_all_succ = (
            p2.successful_requests + p4.successful_requests + p6.successful_requests
        )
        p2_rate = f"{p2.success_rate:.1f}%" if p2.total_requests else "N/A"
        p4_rate = f"{p4.success_rate:.1f}%" if p4.total_requests else "N/A"
        p6_rate = f"{p6.success_rate:.1f}%" if p6.total_requests else "N/A"

        summary_lines = [
            "\n" + "=" * 65,
            "               CHAOS LOAD TEST SUMMARY REPORT               ",
            "=" * 65,
            f" Manifest Target   : {self.manifest_path}",
            f" Target URL        : {self.target_url}",
            f" Duration          : {self.duration}s",
            f" Mode              : {'DRY-RUN' if self.dry_run else 'LIVE'}",
            "-" * 65,
            f" Phase 2 Baseline  : {p2.total_requests} reqs | Success: {p2_rate} | Avg Lat: {p2.avg_latency:.2f}ms",
            f" Phase 4 Under Fault: {p4.total_requests} reqs | Success: {p4_rate} | Avg Lat: {p4.avg_latency:.2f}ms",
            f" Phase 6 Recovery  : {p6.total_requests} reqs | Success: {p6_rate} | Avg Lat: {p6.avg_latency:.2f}ms",
            "-" * 65,
            f" Total Requests    : {total_all_reqs}",
            f" Total Successes   : {total_all_succ}",
            " Data loss         : NOT VERIFIED",
            "=" * 65,
        ]

        report_output = "\n".join(summary_lines)
        logger.info(report_output)

        success = True
        if not self.dry_run:
            if p6.total_requests == 0:
                logger.error("ASSERTION FAILED: No recovery requests were recorded.")
                success = False
            elif p6.success_rate < 80.0:
                logger.error(
                    "ASSERTION FAILED: Post-recovery success rate below threshold (%.1f%% < 80.0%%)",
                    p6.success_rate,
                )
                success = False

        if self.dry_run:
            logger.info("[DRY-RUN] Recovery availability assertion skipped.")
        elif success:
            logger.info("Recovery availability assertion passed.")
        else:
            logger.error("Recovery availability assertion failed.")

        return success

    async def execute(self) -> int:
        self.setup_logging()
        logger.info("Starting Chaos Engineering Load Test Orchestrator")

        self._execution_task = asyncio.current_task()
        try:
            if self._shutdown_requested:
                raise _TerminationRequested
            if self._owned_faults or self._pending_fault is not None:
                logger.error("Previous chaos resources require manual inspection")
                return 1
            if not self.phase1_preflight():
                return 1

            await self.phase2_baseline_load()

            try:
                applied = self.phase3_apply_fault()
                if applied:
                    await self.phase4_monitor_fault()
            finally:
                self._cleanup_in_progress = True
                try:
                    removed = self.phase5_remove_fault()
                finally:
                    self._cleanup_in_progress = False

            if self._shutdown_requested:
                raise _TerminationRequested
            if not applied or not removed:
                return 1

            await self.phase6_verify_recovery()

            if not self.phase7_assert_and_report():
                return 1

            return 0
        except Exception as exc:  # RZ-22-01-JUSTIFIED: top-level CLI orchestrator error handler to guarantee return code
            logger.error(
                "Unexpected error during chaos loadtest execution (%s)",
                type(exc).__name__,
            )
            return 1
        finally:
            self._execution_task = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chaos Mesh K8s load test orchestrator. Live manifests must use the current context namespace."
    )
    parser.add_argument(
        "--manifest",
        default="k8s/chaos/redis-chaos.yaml",
        help="Path to Chaos Mesh manifest YAML file",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration of fault injection phase in seconds",
    )
    parser.add_argument(
        "--target-url",
        default="http://localhost:8000/health",
        help="Target URL for HTTP load generation and health monitoring",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode without applying actual K8s chaos manifests",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()
    orchestrator = ChaosLoadTestOrchestrator(
        manifest_path=args.manifest,
        duration=args.duration,
        target_url=args.target_url,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    previous_sigterm = signal.signal(signal.SIGTERM, orchestrator._request_termination)
    try:
        try:
            exit_code = asyncio.run(orchestrator.execute())
        except _TerminationRequested:
            logger.error("Termination requested; cleanup was attempted")
            exit_code = 143
        except asyncio.CancelledError:
            if not orchestrator._shutdown_requested:
                raise
            logger.error("Termination requested; cleanup was attempted")
            exit_code = 143
        if orchestrator._shutdown_requested:
            exit_code = 143
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
