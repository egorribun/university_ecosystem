import ast
import re
from pathlib import Path

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


def test_deployment_metric_inventory_matches_cleanup_factory_calls() -> None:
    root = Path(__file__).resolve().parents[1]
    metric_keys = set()
    for path in (root / "app" / "services").glob("*cleanup.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_periodic_task_metrics"
            ):
                assert node.args
                name = node.args[0]
                assert isinstance(name, ast.Constant) and isinstance(name.value, str)
                metric_keys.add(f"periodic_task_{name.value}")

    assert metric_keys
    for filename in ("DEPLOY.md", "DEPLOY.en.md"):
        document = (root / "docs" / filename).read_text(encoding="utf-8")
        documented_keys = set(re.findall(r"`(periodic_task_[a-z_]+)_\*`", document))
        assert documented_keys == metric_keys, filename
        assert "periodic_task_notifications_retention_" not in document
