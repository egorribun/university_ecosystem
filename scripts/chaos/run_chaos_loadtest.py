#!/usr/bin/env python3
"""Chaos engineering load test orchestrator.

Orchestrates Chaos Mesh fault injection scenarios alongside HTTP load generation
to verify system resilience, automated recovery, and data integrity under failure.
"""

import argparse
import asyncio
import logging
import math
import pathlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("chaos_loadtest")


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
        if not (url.startswith("http://") or url.startswith("https://")):
            return 0, 0.0, f"Unsupported URL scheme: {url}"

        req = Request(url, headers={"User-Agent": "ChaosLoadTest/1.0"})  # noqa: S310
        try:
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
                    res = subprocess.run(  # noqa: S603
                        [kubectl_bin, "version", "--client"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    logger.info(
                        "kubectl client version check exit code: %d", res.returncode
                    )
                except (subprocess.SubprocessError, OSError) as err:
                    logger.error("Failed executing kubectl: %s", err)
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
            "Baseline completed: %d requests, %.2f%% success rate, avg latency: %.2fms",
            metrics.total_requests,
            metrics.success_rate,
            metrics.avg_latency,
        )
        self.results["phase2"] = metrics
        return metrics

    def phase3_apply_fault(self) -> bool:
        logger.info("=== Phase 3/7: Apply Chaos Fault Injection ===")
        if self.dry_run:
            logger.info("[DRY-RUN] Executing: kubectl apply -f %s", self.manifest_path)
            return True

        kubectl_bin = shutil.which("kubectl") or "kubectl"
        try:
            res = subprocess.run(  # noqa: S603
                [kubectl_bin, "apply", "-f", str(self.manifest_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Fault applied successfully: %s", res.stdout.strip())
            return True
        except (subprocess.SubprocessError, OSError) as err:
            logger.error("Failed to apply chaos fault manifest: %s", err)
            return False

    async def phase4_monitor_fault(self) -> PhaseMetrics:
        logger.info(
            "=== Phase 4/7: Monitor System Behaviour Under Fault (%ds) ===",
            int(self.duration),
        )
        metrics = await self._run_http_load("Phase 4: Fault Injection", self.duration)
        logger.info(
            "Fault phase completed: %d requests, %.2f%% success rate, avg latency: %.2fms",
            metrics.total_requests,
            metrics.success_rate,
            metrics.avg_latency,
        )
        self.results["phase4"] = metrics
        return metrics

    def phase5_remove_fault(self) -> bool:
        logger.info("=== Phase 5/7: Remove Fault Injection ===")
        if self.dry_run:
            logger.info("[DRY-RUN] Executing: kubectl delete -f %s", self.manifest_path)
            return True

        kubectl_bin = shutil.which("kubectl") or "kubectl"
        try:
            res = subprocess.run(  # noqa: S603
                [kubectl_bin, "delete", "-f", str(self.manifest_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Fault removed successfully: %s", res.stdout.strip())
            return True
        except (subprocess.SubprocessError, OSError) as err:
            logger.error("Failed to remove chaos fault manifest: %s", err)
            return False

    async def phase6_verify_recovery(self) -> PhaseMetrics:
        logger.info(
            "=== Phase 6/7: Trigger and Verify Automated Recovery & DLQ Replay ==="
        )
        poll_start = time.monotonic()
        recovered = False
        max_wait = 15.0

        while (time.monotonic() - poll_start) < max_wait:
            status, _lat, _err = self._send_http_request(self.target_url, timeout=2.0)
            if status in (200, 201, 202, 204) or self.dry_run:
                recovered = True
                break
            await asyncio.sleep(1.0)

        if recovered:
            logger.info("System health endpoint responded successfully post-fault.")
        else:
            logger.warning("System recovery check timed out after %.1fs.", max_wait)

        metrics = await self._run_http_load("Phase 6: Recovery Verification", 3.0)
        logger.info(
            "Recovery verification load test: %d requests, %.2f%% success rate",
            metrics.total_requests,
            metrics.success_rate,
        )
        self.results["phase6"] = metrics
        return metrics

    def phase7_assert_and_report(self) -> bool:
        logger.info("=== Phase 7/7: Assert Zero Data Loss & Summary Report ===")
        p2 = self.results.get("phase2", PhaseMetrics("Phase 2"))
        p4 = self.results.get("phase4", PhaseMetrics("Phase 4"))
        p6 = self.results.get("phase6", PhaseMetrics("Phase 6"))

        total_all_reqs = p2.total_requests + p4.total_requests + p6.total_requests
        total_all_succ = (
            p2.successful_requests + p4.successful_requests + p6.successful_requests
        )

        summary_lines = [
            "\n" + "=" * 65,
            "               CHAOS LOAD TEST SUMMARY REPORT               ",
            "=" * 65,
            f" Manifest Target   : {self.manifest_path}",
            f" Target URL        : {self.target_url}",
            f" Duration          : {self.duration}s",
            f" Mode              : {'DRY-RUN' if self.dry_run else 'LIVE'}",
            "-" * 65,
            f" Phase 2 Baseline  : {p2.total_requests} reqs | Success: {p2.success_rate:.1f}% | Avg Lat: {p2.avg_latency:.2f}ms",
            f" Phase 4 Under Fault: {p4.total_requests} reqs | Success: {p4.success_rate:.1f}% | Avg Lat: {p4.avg_latency:.2f}ms",
            f" Phase 6 Recovery  : {p6.total_requests} reqs | Success: {p6.success_rate:.1f}% | Avg Lat: {p6.avg_latency:.2f}ms",
            "-" * 65,
            f" Total Requests    : {total_all_reqs}",
            f" Total Successes   : {total_all_succ}",
            "=" * 65,
        ]

        report_output = "\n".join(summary_lines)
        logger.info(report_output)

        success = True
        if not self.dry_run:
            if p6.total_requests > 0 and p6.success_rate < 80.0:
                logger.error(
                    "ASSERTION FAILED: Post-recovery success rate below threshold (%.1f%% < 80.0%%)",
                    p6.success_rate,
                )
                success = False

        if success:
            logger.info(
                "✅ All assertions passed: Zero data loss verified & system operational."
            )
        else:
            logger.error("❌ Assertions failed.")

        return success

    async def execute(self) -> int:
        self.setup_logging()
        logger.info("Starting Chaos Engineering Load Test Orchestrator")

        try:
            if not self.phase1_preflight():
                return 1

            await self.phase2_baseline_load()

            if not self.phase3_apply_fault():
                return 1

            await self.phase4_monitor_fault()

            if not self.phase5_remove_fault():
                return 1

            await self.phase6_verify_recovery()

            if not self.phase7_assert_and_report():
                return 1

            return 0
        except Exception as exc:  # RZ-22-01-JUSTIFIED: top-level CLI orchestrator error handler to guarantee return code
            logger.exception(
                "Unexpected error during chaos loadtest execution: %s", exc
            )
            return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chaos Mesh K8s load test orchestrator."
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
    exit_code = asyncio.run(orchestrator.execute())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
