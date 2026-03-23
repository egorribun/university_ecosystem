"""Compatibility re-export for legacy ``app.auth.spotify`` imports.

The Spotify integration now lives in :mod:`app.api.spotify`.  This module
re-exports the public surface so any remaining imports continue to work while
pointing to the new implementation.
"""

# LOW-W19: replaced wildcard import with explicit names so static analysis
# tools (mypy, pylint, ruff F401) can resolve re-exported symbols and flag
# any future drift between this shim and the real implementation.
from app.api.spotify import (  # noqa: F401
    disconnect,
    list_playlists,
    now_playing,
    router,
    spotify_auth_url,
    spotify_callback,
    sync_playlists,
)
