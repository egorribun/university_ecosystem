"""Closure tests for geolocation double-checked initialization guards."""

from unittest.mock import patch

import pytest

import app.services.geolocation as geolocation_module
from app.services.geolocation import (
    GeolocationService,
    get_geolocation_service_instance,
)


@pytest.mark.asyncio
async def test_initialize_rechecks_flag_after_acquiring_lock():
    service = GeolocationService(db_path="unused")

    class Lock:
        async def __aenter__(self):
            service._initialized = True

        async def __aexit__(self, exc_type, exc, tb):
            return None

    service._init_lock = Lock()

    await service.initialize()

    assert service.reader is None


@pytest.mark.asyncio
async def test_singleton_rechecks_global_inside_thread_lock():
    original_instance = geolocation_module._geolocation_service_instance
    existing = GeolocationService(db_path="")
    existing._initialized = True

    class Lock:
        def __enter__(self):
            geolocation_module._geolocation_service_instance = existing
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    try:
        geolocation_module._geolocation_service_instance = None
        with patch.object(geolocation_module, "_geolocation_service_lock", Lock()):
            result = await get_geolocation_service_instance()
        assert result is existing
    finally:
        geolocation_module._geolocation_service_instance = original_instance
