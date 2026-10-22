from __future__ import annotations

import app.services.nats_messaging as nats_module
from app.services.nats_messaging import NatsService


def test_nats_singleton_double_check_handles_race_inside_lock():
    original_service = nats_module._nats_service
    original_lock = nats_module._nats_service_lock
    raced_service = NatsService(name="raced")

    class RaceLock:
        def __enter__(self):
            nats_module._nats_service = raced_service
            return self

        def __exit__(self, *_args):
            return False

    try:
        nats_module._nats_service = None
        nats_module._nats_service_lock = RaceLock()
        assert nats_module.get_nats_service() is raced_service
    finally:
        nats_module._nats_service = original_service
        nats_module._nats_service_lock = original_lock
