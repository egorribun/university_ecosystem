file_path = "app/api/websocket.py"
marker = (
    "# ── Sub-package imports (re-exported for backwards compat) ─────────────────────"
)

with open(file_path, encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
found_marker = False
skip_next = False

for line in lines:
    if skip_next:
        if line.strip() == ")":
            skip_next = False
        continue

    new_lines.append(line)

    if marker in line and not found_marker:
        new_lines.extend(
            [
                "from app.api.ws.connection_manager import (\n",
                "    ConnectionManager,\n",
                "    manager,\n",
                ")\n",
                "from app.api.ws.presence import (\n",
                "    PRESENCE_SOURCE_CONNECT,\n",
                "    PRESENCE_SOURCE_DISCONNECT,\n",
                "    PRESENCE_SOURCE_PING,\n",
                "    PRESENCE_SOURCE_PUBSUB,\n",
                "    invalidate_chat_participants_cache,\n",
                "    invalidate_presence_audience_cache,\n",
                "    presence_pubsub,\n",
                ")\n",
            ]
        )
        found_marker = True
        skip_next = True  # Skip the OLD incomplete import block

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Successfully patched app/api/websocket.py")
