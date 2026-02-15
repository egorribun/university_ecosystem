import pytest
from prometheus_client import CollectorRegistry

from app.core.observability import get_periodic_task_metrics


@pytest.mark.asyncio
async def test_periodic_task_metrics_records_success() -> None:
    registry = CollectorRegistry()
    metrics = get_periodic_task_metrics("test_periodic_task_success", registry=registry)

    async with metrics.track_execution() as run:
        run.observe_deleted((3, 2, None))

    prefix = "periodic_task_test_periodic_task_success"
    assert registry.get_sample_value(f"{prefix}_runs_total") == pytest.approx(1.0)
    assert registry.get_sample_value(f"{prefix}_errors_total") == pytest.approx(0.0)
    assert registry.get_sample_value(f"{prefix}_deleted_total") == pytest.approx(5.0)
    assert registry.get_sample_value(
        f"{prefix}_duration_seconds_count"
    ) == pytest.approx(1.0)
    duration_sum = registry.get_sample_value(f"{prefix}_duration_seconds_sum")
    assert duration_sum is not None and duration_sum >= 0.0


@pytest.mark.asyncio
async def test_periodic_task_metrics_records_failure() -> None:
    registry = CollectorRegistry()
    metrics = get_periodic_task_metrics("test_periodic_task_failure", registry=registry)

    with pytest.raises(RuntimeError):
        async with metrics.track_execution():
            raise RuntimeError("boom")

    prefix = "periodic_task_test_periodic_task_failure"
    assert registry.get_sample_value(f"{prefix}_runs_total") == pytest.approx(0.0)
    assert registry.get_sample_value(f"{prefix}_errors_total") == pytest.approx(1.0)
    assert registry.get_sample_value(f"{prefix}_deleted_total") == pytest.approx(0.0)
    assert registry.get_sample_value(
        f"{prefix}_duration_seconds_count"
    ) == pytest.approx(1.0)
    duration_sum = registry.get_sample_value(f"{prefix}_duration_seconds_sum")
    assert duration_sum is not None and duration_sum >= 0.0
