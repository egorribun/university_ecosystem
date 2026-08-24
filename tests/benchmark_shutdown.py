"""Direct benchmark runner for OpenTelemetry shutdown under unreachable collector."""

import logging
import statistics
import sys
import time
import warnings
from pathlib import Path

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.core.observability as obs

logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")

endpoint = "http://127.0.0.1:49999"
trials = 10
latencies = []

print(
    f"=== RUNNING {trials} EMPIRICAL SHUTDOWN BENCHMARK TRIALS AGAINST {endpoint} ==="
)

for i in range(trials):
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

    resource = Resource.create({"service.name": "benchmark"})
    span_exp = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(span_exp))
    trace.set_tracer_provider(tp)

    metric_exp = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(metric_exp, export_interval_millis=60000)
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)

    log_exp = OTLPLogExporter(endpoint=endpoint, insecure=True)
    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(log_exp))
    obs._otel_logger_provider = lp
    obs._otel_configured = True

    # Emit telemetry
    tracer = tp.get_tracer("bench")
    with tracer.start_as_current_span("bench_span"):
        mp.get_meter("bench").create_counter("bench_counter").add(10)

    t0 = time.perf_counter()
    obs.shutdown_observability()
    dt = time.perf_counter() - t0
    latencies.append(dt)
    verdict = "PASS" if dt <= 2.05 else "FAIL"
    print(
        f"Trial {i + 1:2d}: {dt * 1000:7.2f} ms ({dt:.4f} s) - SLA <= 2050 ms: {verdict}"
    )

min_l = min(latencies)
max_l = max(latencies)
mean_l = statistics.mean(latencies)
stdev_l = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

print("=" * 60)
print("BENCHMARK SUMMARY:")
print(f"  Trials:   {trials}")
print(f"  Min:      {min_l * 1000:7.2f} ms ({min_l:.4f} s)")
print(f"  Max:      {max_l * 1000:7.2f} ms ({max_l:.4f} s)")
print(f"  Mean:     {mean_l * 1000:7.2f} ms ({mean_l:.4f} s)")
print(f"  StdDev:   {stdev_l * 1000:7.2f} ms ({stdev_l:.4f} s)")
sla_verdict = "PASSED (100% compliant)" if max_l <= 2.05 else "FAILED"
print(f"  SLA (<= 2050 ms): {sla_verdict}")
print("=" * 60)
