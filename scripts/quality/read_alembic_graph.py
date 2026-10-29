"""Pure Alembic graph-metadata contract, not a migration execution adapter.

This independent tests-first scaffold rejects every graph until the hosted
literal positive control has failed semantically. It does not alter the legacy
single-parent reader or CLI, import migrations, render SQL, or admit a database.
Callers own source collection and input-size limits; this API is neither a file
loader nor an execution plan.
"""


def read_revision_graph(
    sources: dict[str, str],
) -> dict[str, tuple[str, ...]] | None:
    """Return literal revision-to-parent edges, or None for an invalid graph."""
    _ = sources
    return None
