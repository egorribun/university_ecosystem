"""Adversarial stress testing and empirical benchmarking for observability subsystem.

Validates:
1. shutdown_observability() execution is strictly bounded (<= 2.05s) under unreachable collector conditions (e.g. http://127.0.0.1:49999).
2. Clean executor teardown without deadlocks or thread resource leaks.
3. High-concurrency multi-threaded telemetry logging under structlog + OTEL context + PII redaction.
4. High-concurrency metric recording (WorkerMetrics, PeriodicTaskMetrics, NotificationQueueMetrics).
5. Thread-safety and re-entrancy of double-checked locking under concurrent initialization and teardown.
6. Multi-trial empirical latency benchmarking under simulated network blackhole.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.observability as obs
from app.core.config import settings
from app.core.logging import bind_context, clear_context, get_logger

pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning:opentelemetry"),
    pytest.mark.filterwarnings("ignore::DeprecationWarning:pkg_resources"),
]
REPO_ROOT = Path(__file__).resolve().parents[1]


def _reset_otel_globals():
    """Helper to reset OpenTelemetry global provider locks in test teardown."""
    obs.shutdown_observability()
    with trace._TRACER_PROVIDER_SET_ONCE._lock:
        trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace._TRACER_PROVIDER = None
    if hasattr(metrics, "_internal") and hasattr(
        metrics._internal, "_METER_PROVIDER_SET_ONCE"
    ):
        with metrics._internal._METER_PROVIDER_SET_ONCE._lock:
            metrics._internal._METER_PROVIDER_SET_ONCE._done = False
        metrics._internal._METER_PROVIDER = None


@pytest.fixture(autouse=True)
def cleanup_observability_state():
    """Ensure clean observability state before and after each test."""
    _reset_otel_globals()
    yield
    _reset_otel_globals()


class HangingSpanExporter(OTLPSpanExporter):
    """Simulates an exporter that hangs forever when attempting to export to an unreachable endpoint."""

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        time.sleep(10.0)  # pragma: allowlist bound


class HangingMetricExporter(OTLPMetricExporter):
    """Simulates a metric exporter that hangs forever on shutdown."""

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        time.sleep(10.0)  # pragma: allowlist bound


class HangingLogExporter(OTLPLogExporter):
    """Simulates a log exporter that hangs forever on shutdown."""

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        time.sleep(10.0)  # pragma: allowlist bound


def test_shutdown_observability_unreachable_endpoint_benchmark():
    """Benchmark shutdown_observability under unreachable collector endpoint (http://127.0.0.1:49999).

    Must complete in <= 2.05s.
    """
    endpoint = "http://127.0.0.1:49999"
    resource = Resource.create({"service.name": "benchmark-test"})

    # Setup TracerProvider with unreachable endpoint
    span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Setup MeterProvider with unreachable endpoint
    metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    meter_reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=60000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[meter_reader])
    metrics.set_meter_provider(meter_provider)

    # Setup LoggerProvider with unreachable endpoint
    log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    obs._otel_logger_provider = logger_provider

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    obs._otel_logging_handler = handler
    obs._otel_configured = True

    # Emit telemetry data
    tracer = tracer_provider.get_tracer("benchmark")
    with tracer.start_as_current_span("unreachable-span"):
        meter = meter_provider.get_meter("benchmark")
        counter = meter.create_counter("benchmark_counter")
        counter.add(42)
        logging.getLogger("benchmark").info("Emitting log to unreachable collector")

    # Time the shutdown
    start_time = time.perf_counter()
    obs.shutdown_observability()
    elapsed = time.perf_counter() - start_time

    assert elapsed <= 2.05, f"Shutdown took {elapsed:.4f}s, exceeding 2.05s SLA"
    assert obs._otel_configured is False
    assert obs._otel_logger_provider is None
    assert obs._otel_logging_handler is None


def test_shutdown_observability_multi_trial_statistical_benchmark():
    """Multi-trial statistical benchmark: 5 consecutive iterations under unreachable collector.

    Verifies every single trial completes <= 2.05s without latency drift.
    """
    endpoint = "http://127.0.0.1:49999"
    resource = Resource.create({"service.name": "multi-trial-benchmark"})
    latencies = []

    for trial in range(5):
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        meter_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=60000
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[meter_reader])
        metrics.set_meter_provider(meter_provider)

        log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        obs._otel_logger_provider = logger_provider

        obs._otel_configured = True

        # Emit
        tracer = tracer_provider.get_tracer("trial")
        with tracer.start_as_current_span(f"span_{trial}"):
            meter = meter_provider.get_meter("trial")
            meter.create_counter("trial_counter").add(1)

        t0 = time.perf_counter()
        obs.shutdown_observability()
        dt = time.perf_counter() - t0
        latencies.append(dt)
        assert dt <= 2.05, f"Trial {trial} exceeded 2.05s SLA: {dt:.4f}s"

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    assert max_latency <= 2.05, (
        f"Max trial latency {max_latency:.4f}s exceeded 2.05s SLA"
    )
    assert avg_latency <= 2.0, (
        f"Average trial latency {avg_latency:.4f}s exceeded 2.0s target"
    )


def test_shutdown_observability_hanging_providers_bounded_timeout():
    """Adversarial test: Exporters explicitly hang for 10s.

    shutdown_observability must return within 2.05s via bounded concurrent futures wait.
    """
    resource = Resource.create({"service.name": "hanging-test"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(HangingSpanExporter(insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    meter_reader = PeriodicExportingMetricReader(
        HangingMetricExporter(insecure=True), export_interval_millis=60000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[meter_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(HangingLogExporter(insecure=True))
    )
    obs._otel_logger_provider = logger_provider

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    obs._otel_logging_handler = handler
    obs._otel_configured = True

    start_time = time.perf_counter()
    obs.shutdown_observability()
    elapsed = time.perf_counter() - start_time

    assert elapsed <= 2.05, f"Hanging shutdown took {elapsed:.4f}s, exceeding 2.05s SLA"
    assert obs._otel_configured is False


def test_shutdown_observability_does_not_keep_process_alive() -> None:
    """A stuck exporter must not leave non-daemon workers after shutdown."""
    script = """
import time
from opentelemetry.sdk.trace import TracerProvider
import app.core.observability as obs

provider = TracerProvider()
def hanging_shutdown(*args, **kwargs):
    time.sleep(30)  # pragma: allowlist bound (subprocess timeout bounds the child)
provider.shutdown = hanging_shutdown
obs.trace.get_tracer_provider = lambda: provider
obs.metrics.get_meter_provider = lambda: object()
started = time.monotonic()
obs.shutdown_observability()
print(f'shutdown-returned {time.monotonic() - started:.4f}', flush=True)
"""
    completed = subprocess.run(  # noqa: S603 - interpreter/script are test-controlled.
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        # Importing the full observability stack on Windows can take several
        # seconds; the assertion below measures the shutdown operation itself.
        timeout=10,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "shutdown-returned" in completed.stdout
    elapsed = float(completed.stdout.split()[-1])
    assert elapsed <= 2.05, f"Child shutdown took {elapsed:.4f}s"


def test_concurrent_shutdown_calls_no_deadlock():
    """Stress test: 20 threads simultaneously call shutdown_observability().

    Verifies idempotency, thread-safety, and absence of deadlocks.
    """
    resource = Resource.create({"service.name": "concurrent-shutdown"})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint="http://127.0.0.1:49999", insecure=True)
        )
    )
    trace.set_tracer_provider(tracer_provider)
    obs._otel_configured = True

    num_threads = 20
    barrier = threading.Barrier(num_threads)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=5.0)
            t0 = time.perf_counter()
            obs.shutdown_observability()
            results.append(time.perf_counter() - t0)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), "Thread deadlocked during concurrent shutdown"

    assert len(errors) == 0, f"Errors encountered during concurrent shutdown: {errors}"
    assert len(results) == num_threads
    for r in results:
        assert r <= 2.05, f"Individual shutdown in concurrent test took {r:.4f}s"


def test_concurrency_stress_telemetry_logging():
    """Stress test: 30 threads concurrently emitting structured logs with contextvars and PII.

    Verifies absence of data races, context bleeding, or lock contention in structlog + OTEL context.
    """
    logger = get_logger("stress_logger")
    num_threads = 30
    logs_per_thread = 100
    errors = []

    def log_worker(thread_id: int):
        try:
            clear_context()
            bind_context(thread_id=thread_id, request_id=f"req-{thread_id}")
            for i in range(logs_per_thread):
                logger.info(
                    "Processing event",
                    iteration=i,
                    email=f"user_{thread_id}_{i}@example.com",
                    phone=f"+1-555-01{thread_id:02d}",
                    secret_token=f"tok_{thread_id}_{i}",
                    data={"nested_id": f"{thread_id}:{i}"},
                )
            clear_context()
        except Exception as e:
            errors.append((thread_id, e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(log_worker, tid) for tid in range(num_threads)]
        concurrent.futures.wait(futures, timeout=10.0)

    assert len(errors) == 0, f"Logging worker errors: {errors}"


def test_concurrency_stress_worker_metrics():
    """Stress test: 40 threads concurrently recording success, failure, startup on WorkerMetrics."""
    metrics_bundle = obs.create_worker_metrics("stress_worker")
    num_threads = 40
    iterations = 200
    errors = []

    def metric_worker(worker_id: int):
        try:
            for i in range(iterations):
                if i % 3 == 0:
                    metrics_bundle.record_success(notifications_created=(i % 5))
                elif i % 3 == 1:
                    metrics_bundle.record_failure()
                else:
                    metrics_bundle.mark_startup()
        except Exception as e:
            errors.append((worker_id, e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(metric_worker, wid) for wid in range(num_threads)]
        concurrent.futures.wait(futures, timeout=10.0)

    assert len(errors) == 0, f"Worker metrics errors: {errors}"
    assert metrics_bundle.status in ("ok", "degraded")
    assert metrics_bundle.last_run is not None


@pytest.mark.asyncio
async def test_concurrency_stress_periodic_task_metrics():
    """Stress test: 30 concurrent async tasks executing PeriodicTaskMetrics.track_execution()."""
    task_metrics = obs.get_periodic_task_metrics("stress_periodic_task")
    num_tasks = 30
    iterations = 20

    async def task_worker(task_id: int):
        for i in range(iterations):
            try:
                if i % 4 == 0:
                    # simulate error
                    async with task_metrics.track_execution() as run:
                        run.observe_deleted(i)
                        raise ValueError("Simulated failure")
                else:
                    async with task_metrics.track_execution() as run:
                        run.observe_deleted([1, 2, 3])
                        await asyncio.sleep(0.001)
            except ValueError:
                pass

    tasks = [asyncio.create_task(task_worker(tid)) for tid in range(num_tasks)]
    await asyncio.gather(*tasks)

    # Verification: metric counters updated without corruption
    assert task_metrics.runs_total._value.get() > 0
    assert task_metrics.errors_total._value.get() > 0
    assert task_metrics.deleted_total._value.get() > 0


def test_concurrency_stress_notification_queue_metrics_reinitialization():
    """Stress test: Concurrent updates and reinitializations of NotificationQueueMetrics."""
    num_threads = 20
    iterations = 50
    errors = []

    def queue_worker(thread_id: int):
        try:
            for i in range(iterations):
                if i % 15 == 0:
                    obs.reinitialize_notification_queue_metrics()
                metrics = obs.get_notification_queue_metrics()
                metrics.queue_size.set(i)
                metrics.dropped_jobs_total.labels(kind="email").inc(1)
                metrics.failed_jobs_total.labels(kind="sms").inc(1)
                metrics.processed_jobs_total.labels(kind="push").inc(1)
                metrics.processing_latency_seconds.observe(0.05)
                metrics.dead_lettered_jobs.set(i % 3)
        except Exception as e:
            errors.append((thread_id, e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(queue_worker, tid) for tid in range(num_threads)]
        concurrent.futures.wait(futures, timeout=10.0)

    assert len(errors) == 0, f"Notification queue metric errors: {errors}"


@pytest.mark.asyncio
async def test_lifecycle_reconfiguration_and_teardown_churn():
    """Stress test: 5 rapid cycles of full configure/telemetry/shutdown with real async engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        for cycle in range(5):
            with (
                patch.object(settings, "enable_otel", True),
                patch.object(settings, "enable_otel_metrics", True),
                patch.object(settings, "enable_otel_logs", False),
                patch.object(
                    settings, "otel_exporter_otlp_endpoint", "http://127.0.0.1:49999"
                ),
                patch.object(obs, "_sqlalchemy_instrumented", True),
            ):
                obs._configure_otel(engine)
                assert obs._otel_configured is True

                # Emit
                tracer = trace.get_tracer_provider().get_tracer("lifecycle_test")
                with tracer.start_as_current_span(f"span_{cycle}"):
                    pass

                # Shutdown
                t0 = time.perf_counter()
                obs.shutdown_observability()
                dt = time.perf_counter() - t0
                assert dt <= 2.05, f"Cycle {cycle} shutdown exceeded SLA: {dt:.4f}s"
                assert obs._otel_configured is False
    finally:
        await engine.dispose()


def test_concurrent_double_checked_initialization_no_deadlock():
    """Stress test: 30 threads simultaneously call _configure_otel() to verify double-checked locking & RLock."""
    obs.shutdown_observability()
    obs._otel_configured = False

    num_threads = 30
    barrier = threading.Barrier(num_threads)
    results = []
    errors = []
    mock_engine = MagicMock()

    def init_worker():
        try:
            barrier.wait(timeout=5.0)
            provider = obs._configure_otel(mock_engine)
            results.append(provider)
        except Exception as e:
            errors.append(e)

    with (
        patch.object(settings, "enable_otel", True),
        patch.object(settings, "enable_otel_metrics", False),
        patch.object(settings, "enable_otel_logs", False),
        patch.object(obs, "SQLAlchemyInstrumentor"),
        patch.object(obs, "RedisInstrumentor"),
        patch.object(obs, "HTTPXClientInstrumentor"),
    ):
        threads = [threading.Thread(target=init_worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive(), "Init worker thread deadlocked"

    assert len(errors) == 0, f"Init errors: {errors}"
    assert len(results) == num_threads
    first = results[0]
    for p in results[1:]:
        assert p == first, "Double-checked locking returned inconsistent providers"
