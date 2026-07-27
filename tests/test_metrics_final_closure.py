from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core import metrics


def test_record_pool_metrics_handles_pool_without_checkedout_method(monkeypatch):
    pool = SimpleNamespace(
        size=lambda: 4,
        overflow=lambda: 1,
        checkedin=lambda: 3,
    )
    monkeypatch.setattr(
        metrics,
        "engine",
        SimpleNamespace(sync_engine=SimpleNamespace(pool=pool)),
    )
    pool_size = MagicMock()
    checked_out = MagicMock()
    overflow = MagicMock()
    checked_in = MagicMock()
    monkeypatch.setattr(metrics, "_DB_POOL_SIZE", pool_size)
    monkeypatch.setattr(metrics, "_DB_POOL_CHECKEDOUT", checked_out)
    monkeypatch.setattr(metrics, "_DB_POOL_OVERFLOW", overflow)
    monkeypatch.setattr(metrics, "_DB_POOL_CHECKEDIN", checked_in)

    metrics._record_pool_metrics()

    pool_size.set.assert_called_once_with(4.0)
    checked_out.set.assert_not_called()
    overflow.set.assert_called_once_with(1.0)
    checked_in.set.assert_called_once_with(3.0)

    monkeypatch.setattr(
        metrics,
        "engine",
        SimpleNamespace(
            sync_engine=SimpleNamespace(
                pool=SimpleNamespace(overflow=lambda: 0, checkedin=lambda: 0)
            )
        ),
    )
    metrics._record_pool_metrics()


def test_notification_queue_metrics_registry_is_already_default():
    current = SimpleNamespace(registry=metrics.REGISTRY)
    with (
        patch(
            "app.core.observability.get_notification_queue_metrics",
            return_value=current,
        ) as get_metrics,
        patch(
            "app.core.observability.reinitialize_notification_queue_metrics"
        ) as reinitialize,
    ):
        metrics._ensure_notification_queue_metrics_registry()

    get_metrics.assert_called_once_with()
    reinitialize.assert_not_called()
