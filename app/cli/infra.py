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


@app.command()
def check():
    """Run health checks for all infrastructure components."""

    async def _run():
        table = Table(title="Infrastructure Health Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Details", justify="right")

        # 1. PostgreSQL
        try:
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
            table.add_row("PostgreSQL", "[green]ONLINE[/]", "Connected successfully")
        except Exception as e:
            table.add_row("PostgreSQL", "[red]OFFLINE[/]", str(e))

        # 2. Redis (Cache)
        try:
            cache = get_cache()
            if isinstance(cache, RedisCache):
                client = await cache._get_client()
                await client.ping()
                table.add_row("Redis (Cache)", "[green]ONLINE[/]", "Ping successful")
            else:
                table.add_row(
                    "Redis (Cache)",
                    "[yellow]SKIPPED[/]",
                    f"Using {type(cache).__name__}",
                )
        except Exception as e:
            table.add_row("Redis (Cache)", "[red]OFFLINE[/]", str(e))

        # 3. NATS
        try:
            nats_service = get_nats_service()
            # We don't want to block forever if NATS is down
            await asyncio.wait_for(nats_service.connect(), timeout=5.0)
            table.add_row("NATS", "[green]ONLINE[/]", "Connected successfully")
            await nats_service.close()
        except TimeoutError:
            table.add_row("NATS", "[red]OFFLINE[/]", "Connection timed out (5s)")
        except Exception as e:
            table.add_row("NATS", "[red]OFFLINE[/]", str(e))

        # 4. Storage (MinIO)
        if hasattr(settings, "storage_backend") and settings.storage_backend in (
            "s3",
            "minio",
        ):
            from app.services.storage import get_storage_service

            try:
                get_storage_service()
                table.add_row(
                    "S3 Storage",
                    "[green]ONLINE[/]",
                    f"Backend: {settings.storage_backend}",
                )
            except Exception as e:
                table.add_row("S3 Storage", "[red]OFFLINE[/]", str(e))
        else:
            table.add_row(
                "S3 Storage",
                "[yellow]SKIPPED[/]",
                f"Backend: {getattr(settings, 'storage_backend', 'unknown')}",
            )

        console.print(table)

    asyncio.run(_run())
