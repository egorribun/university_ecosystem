"""Compatibility re-export for legacy ``app.auth.spotify`` imports.

The Spotify integration now lives in :mod:`app.api.spotify`.  This module
re-exports the public surface so any remaining imports continue to work while
pointing to the new implementation.
"""

from app.api.spotify import *  # noqa: F401,F403
