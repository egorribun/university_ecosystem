import asyncio

import typer
from rich.console import Console
from rich.table import Table

from app.core.config import settings
from app.core.database import engine
from app.deps.cache import RedisCache, get_cache
from app.services.nats_messaging import get_nats_service

app = typer.Typer(help="Infrastructure health checks.")
console = Console()

# Status constants
STATUS_ONLINE = "[green]ONLINE[/]"
STATUS_OFFLINE = "[red]OFFLINE[/]"
STATUS_SKIPPED = "[yellow]SKIPPED[/]"

# Component constants
COMPONENT_POSTGRES = "PostgreSQL"
COMPONENT_REDIS = "Redis (Cache)"
COMPONENT_NATS = "NATS"
COMPONENT_S3 = "S3 Storage"


async def check_infra() -> None:
    """Check infrastructure health status."""
    table = Table(title="Infrastructure Health Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", justify="right")

    # 1. PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        table.add_row(COMPONENT_POSTGRES, STATUS_ONLINE, "Connected successfully")
    except Exception as e:
        table.add_row(COMPONENT_POSTGRES, STATUS_OFFLINE, str(e))

    # 2. Redis (Cache)
    try:
        cache = get_cache()
        if isinstance(cache, RedisCache):
            from typing import Any, cast

            client = await cache._get_client()
            await cast(Any, client.ping())
            table.add_row(COMPONENT_REDIS, STATUS_ONLINE, "Ping successful")
        else:
            table.add_row(
                COMPONENT_REDIS,
                STATUS_SKIPPED,
                f"Using {type(cache).__name__}",
            )
    except Exception as e:
        table.add_row(COMPONENT_REDIS, STATUS_OFFLINE, str(e))

    # 3. NATS
    try:
        nats_service = get_nats_service()
        # We don't want to block forever if NATS is down
        await asyncio.wait_for(nats_service.connect(), timeout=5.0)
        table.add_row(COMPONENT_NATS, STATUS_ONLINE, "Connected successfully")
        await nats_service.close()
    except TimeoutError:
        table.add_row(COMPONENT_NATS, STATUS_OFFLINE, "Connection timed out (5s)")
    except Exception as e:
        table.add_row(COMPONENT_NATS, STATUS_OFFLINE, str(e))

    # 4. Storage (MinIO)
    if hasattr(settings, "storage_backend") and settings.storage_backend in (
        "s3",
        "minio",
    ):
        from app.services.storage import get_storage_backend

        try:
            get_storage_backend(settings)
            table.add_row(
                COMPONENT_S3,
                STATUS_ONLINE,
                f"Backend: {settings.storage_backend}",
            )
        except Exception as e:
            table.add_row(COMPONENT_S3, STATUS_OFFLINE, str(e))
    else:
        table.add_row(
            COMPONENT_S3,
            STATUS_SKIPPED,
            f"Backend: {getattr(settings, 'storage_backend', 'unknown')}",
        )

    console.print(table)


@app.command()
def main() -> None:
    """Run health checks for all infrastructure components."""
    asyncio.run(check_infra())
