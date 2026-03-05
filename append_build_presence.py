file_path = "app/api/ws/presence.py"

with open(file_path, "a", encoding="utf-8") as f:
    f.write(
        "\n\nasync def build_presence_map(\n"
        "    user_ids: Iterable[uuid.UUID],\n"
        "    db: AsyncDatabaseSession | None = None,\n"
        ") -> dict[uuid.UUID, PresenceStatus]:\n"
        '    """Return presence info for a set of users.\n\n'
        "    Accepts an optional open DB session (request-scoped callers) or opens\n"
        "    its own session (background tasks / non-request contexts).\n"
        '    """\n'
        "    # Lazy import avoids a circular dependency with connection_manager.\n"
        "    from app.api.ws.connection_manager import manager\n\n"
        "    ids = {uid for uid in user_ids if uid is not None}\n"
        "    if not ids:\n"
        "        return {}\n\n"
        "    from app.repositories.session_repository import SessionRepository\n"
        "    from app.schemas.chat import PresenceStatus\n\n"
        "    if db:\n"
        "        repo = SessionRepository(db)\n"
        "        last_seen_map = await repo.get_last_seen_map(list(ids))\n"
        "    else:\n"
        "        async with async_session() as new_session:\n"
        "            repo = SessionRepository(new_session)\n"
        "            last_seen_map = await repo.get_last_seen_map(list(ids))\n\n"
        "    return {\n"
        "        uid: PresenceStatus(\n"
        "            active=manager.is_online(uid),\n"
        "            last_seen_at=last_seen_map.get(uid),\n"
        "        )\n"
        "        for uid in ids\n"
        "    }\n"
    )

print("Successfully appended build_presence_map to app/api/ws/presence.py")
