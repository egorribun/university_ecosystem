"""Configuration-free chat content and transport limits."""

# Canonical message content limit shared by persistence, HTTP schemas and the
# generated API contract.  Keep this in the backend-owned constants module so a
# boundary change has one source of truth instead of drifting per layer.
CHAT_MAX_MESSAGE_LENGTH = 32_768
# Transport guard shared by the Python fallback endpoint and ws-hub.  This is
# intentionally independent from the content limit: JSON framing and UTF-8
# encoding can make a valid message body larger on the wire.
CHAT_MAX_WEBSOCKET_FRAME_BYTES = 60 * 1024
