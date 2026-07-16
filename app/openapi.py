from __future__ import annotations

import re
from collections.abc import MutableMapping
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

SENSITIVE_PROPERTY_NAMES = {"email", "phone", "password", "password_hash"}


def _humanize(value: str) -> str:
    words = re.sub(r"[_-]+", " ", value).strip()
    return words[:1].upper() + words[1:] if words else "API"


def _derive_tag_from_path(path: str) -> str:
    parts = [part for part in path.strip("/").split("/") if part]
    if parts[:2] == ["api", "v1"] and len(parts) > 2:
        return parts[2]
    return parts[0] if parts else "root"


def _default_operation_description(
    method: str, path: str, operation: dict[str, Any]
) -> str:
    summary = str(operation.get("summary") or "").strip()
    if summary:
        return summary

    operation_id = str(operation.get("operationId") or "").strip()
    if operation_id:
        return _humanize(operation_id)

    tag = operation.get("tags", [_derive_tag_from_path(path)])[0]
    return f"{method.upper()} {path} for {_humanize(str(tag)).lower()} resources."


def _mark_pii_properties(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _mark_pii_properties(item)
        return

    if not isinstance(node, MutableMapping):
        return

    properties = node.get("properties")
    if isinstance(properties, MutableMapping):
        for name, property_schema in properties.items():
            if name in SENSITIVE_PROPERTY_NAMES and isinstance(
                property_schema, MutableMapping
            ):
                property_schema.setdefault("x-pii", True)
            _mark_pii_properties(property_schema)

    for value in node.values():
        _mark_pii_properties(value)


def harden_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Apply contract metadata expected by Spectral and API consumers."""

    schema.setdefault("servers", [{"url": "/", "description": "Current deployment"}])

    info = schema.setdefault("info", {})
    if isinstance(info, MutableMapping):
        info.setdefault(
            "contact",
            {
                "name": "University Ecosystem maintainers",
                "url": "https://github.com/egorribun/university_ecosystem",
            },
        )

    tag_names: set[str] = set()
    paths = schema.get("paths", {})
    if isinstance(paths, MutableMapping):
        for path, path_item in paths.items():
            if not isinstance(path_item, MutableMapping):
                continue

            fallback_tag = _derive_tag_from_path(str(path))
            for method, operation in path_item.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not isinstance(operation, MutableMapping):
                    continue

                tags = operation.setdefault("tags", [fallback_tag])
                if not tags:
                    operation["tags"] = [fallback_tag]
                    tags = operation["tags"]

                for tag in tags:
                    tag_names.add(str(tag))

                description = str(operation.get("description") or "").strip()
                if not description:
                    operation["description"] = _default_operation_description(
                        method, str(path), dict(operation)
                    )

                # Inject OpenAPI Links
                operation_id = operation.get("operationId")
                if operation_id == "login_api_v1_auth_login_post":
                    responses = operation.setdefault("responses", {})
                    for status_code in ["200", "201"]:
                        if status_code in responses:
                            responses[status_code]["links"] = {
                                "GetCurrentUser": {
                                    "operationId": "get_me_api_v1_users_me_get",
                                    "description": "Get current user profile after login",
                                }
                            }
                elif operation_id == "create_event_api_v1_events_post":
                    responses = operation.setdefault("responses", {})
                    for status_code in ["200", "201"]:
                        if status_code in responses:
                            responses[status_code]["links"] = {
                                "GetEventById": {
                                    "operationId": "get_event_api_v1_events__event_id__get",
                                    "parameters": {
                                        "event_id": "$response.body#/id",
                                    },
                                    "description": "Retrieve the created event details",
                                }
                            }
                elif operation_id == "create_chat_api_v1_chats_post":
                    responses = operation.setdefault("responses", {})
                    for status_code in ["200", "201"]:
                        if status_code in responses:
                            responses[status_code]["links"] = {
                                "GetChatMessages": {
                                    "operationId": "get_messages_api_v1_chats__chat_id__messages_get",
                                    "parameters": {
                                        "chat_id": "$response.body#/id",
                                    },
                                    "description": "Get messages for the created chat",
                                }
                            }

    existing_tags = schema.get("tags", [])
    described_tags: dict[str, dict[str, str]] = {}
    if isinstance(existing_tags, list):
        for tag in existing_tags:
            if isinstance(tag, MutableMapping) and "name" in tag:
                name = str(tag["name"])
                described_tags[name] = dict(tag)

    for tag_name in tag_names:
        described_tags.setdefault(
            tag_name,
            {
                "name": tag_name,
                "description": f"{_humanize(tag_name)} API operations.",
            },
        )
    schema["tags"] = [described_tags[name] for name in sorted(described_tags)]

    _mark_pii_properties(schema.get("components", {}))
    return schema


def install_custom_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
        )
        app.openapi_schema = harden_openapi_schema(schema)
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
