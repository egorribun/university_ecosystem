import pytest

from app.core.di import container


@pytest.mark.asyncio
async def test_container_registration():
    # Verify core services are registered in the DI container
    assert container.resolve("db_session") is not None
