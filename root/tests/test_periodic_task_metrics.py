import pytest
from prometheus_client import REGISTRY

from app.core.observability import get_periodic_task_metrics


@pytest.mark.anyio
async def test_periodic_task_metrics_records_success() -> None:
    metrics = get_periodic_task_metrics("test_periodic_task_success")

    async with metrics.track_execution() as run:
        run.observe_deleted((3, 2, None))

    prefix = "periodic_task_test_periodic_task_success"
    assert REGISTRY.get_sample_value(f"{prefix}_runs_total") == pytest.approx(1.0)
    assert REGISTRY.get_sample_value(f"{prefix}_errors_total") == pytest.approx(0.0)
    assert REGISTRY.get_sample_value(f"{prefix}_deleted_total") == pytest.approx(5.0)
    assert REGISTRY.get_sample_value(
        f"{prefix}_duration_seconds_count"
    ) == pytest.approx(1.0)
    duration_sum = REGISTRY.get_sample_value(f"{prefix}_duration_seconds_sum")
    assert duration_sum is not None and duration_sum >= 0.0


@pytest.mark.anyio
async def test_periodic_task_metrics_records_failure() -> None:
    metrics = get_periodic_task_metrics("test_periodic_task_failure")

    with pytest.raises(RuntimeError):
        async with metrics.track_execution():
            raise RuntimeError("boom")

    prefix = "periodic_task_test_periodic_task_failure"
    assert REGISTRY.get_sample_value(f"{prefix}_runs_total") == pytest.approx(0.0)
    assert REGISTRY.get_sample_value(f"{prefix}_errors_total") == pytest.approx(1.0)
    assert REGISTRY.get_sample_value(f"{prefix}_deleted_total") == pytest.approx(0.0)
    assert REGISTRY.get_sample_value(
        f"{prefix}_duration_seconds_count"
    ) == pytest.approx(1.0)
    duration_sum = REGISTRY.get_sample_value(f"{prefix}_duration_seconds_sum")
    assert duration_sum is not None and duration_sum >= 0.0
