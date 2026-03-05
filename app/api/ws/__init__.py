"""WebSocket sub-package — SRP-compliant decomposition of the original monolithic webssocket.py.

TD-9 / MOD-9 (audit 2026-03-05): app/api/websocket.py had 1 150+ lines and
6+ responsibilities.  This package splits them into focused modules:

    app/api/ws/
    ├── __init__.py          — public re-exports (backwards compat)
    ├── presence.py          — PresencePubSub, cache, audience resolution
    ├── connection_manager.py — ConnectionManager, WebSocketRateLimiter
    ├── auth.py              — JWT/cookie token validation, subprotocol handling
    └── serializers.py       — serialize_message, build_presence_map

Route handlers remain in app/api/websocket.py (now ~400 lines) which imports
from this package.
"""
