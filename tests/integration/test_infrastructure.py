import os

import nats
import psycopg
import pytest

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
pytestmark = pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run")


@pytest.fixture(scope="module")
def postgres():
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:15-alpine@sha256:fe0737ba566a2c5b2a28f34433c0a423261900ec17b9bf7ad115e1aae7e57f1b"
    ) as postgres:
        yield postgres


@pytest.fixture(scope="module")
def redis_client():
    # Import lazily so disabled integration tests do not load Docker dependencies.
    from testcontainers.community.redis import RedisContainer

    with RedisContainer(
        "redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
    ) as redis:
        yield redis


@pytest.fixture(scope="module")
def nats_server():
    from testcontainers.core.container import DockerContainer

    with DockerContainer(
        "nats:2.12.15-alpine@sha256:b270f5e2428354c0335612694d7dd2fb588148e567a5757fdff325ef9c9332e6"
    ).with_exposed_ports(4222) as nats:
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
