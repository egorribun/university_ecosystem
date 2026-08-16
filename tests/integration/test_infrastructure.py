import os

import nats
import psycopg
import pytest

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
pytestmark = pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run")


@pytest.fixture(scope="module")
def postgres():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="module")
def redis_client():
    # Import lazily: Testcontainers currently emits a deprecation warning from
    # its Redis module at import time.  Disabled integration tests must not load
    # or warn from infrastructure they never execute.
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture(scope="module")
def nats_server():
    from testcontainers.core.container import DockerContainer

    with DockerContainer("nats:2.10-alpine").with_exposed_ports(4222) as nats:
        yield nats


def test_postgres_container(postgres):
    url = postgres.get_connection_url()
    assert url is not None
    # Basic connectivity check
    with psycopg.connect(url.replace("+psycopg2", "")) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            assert cur.fetchone() == (1,)


def test_redis_container(redis_client):
    client = redis_client.get_client()
    client.set("key", "value")
    assert client.get("key") == b"value"


@pytest.mark.asyncio
async def test_nats_container(nats_server):
    port = nats_server.get_exposed_port(4222)
    host = nats_server.get_container_host_ip()
    url = f"nats://{host}:{port}"

    nc = await nats.connect(url)
    assert nc.is_connected
    await nc.close()
