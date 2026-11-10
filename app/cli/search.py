import asyncio

import typer

from app.services.search_indexer import reindex_all

app = typer.Typer(help="Full-text search index maintenance.")


@app.callback()
def _group() -> None:
    """Search index commands."""


@app.command("reindex")
def reindex(
    batch_size: int = typer.Option(200, min=1, max=1000, help="Rows per bulk request"),
) -> None:
    """Rebuild search with writes/outbox paused and an active MVP_TENANT_ID.

    Use the ordinary RLS application database role, never migration credentials.
    """
    counts = asyncio.run(reindex_all(batch_size=batch_size))
    for index, total in counts.items():
        typer.echo(f"{index}: {total} documents indexed")
