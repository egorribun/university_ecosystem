"""Branch closure tests for OpenAPI hardening helpers."""

from fastapi import FastAPI

from app.openapi import (
    _default_operation_description,
    _derive_tag_from_path,
    _humanize,
    harden_openapi_schema,
    install_custom_openapi,
)


def test_humanize_and_derive_tag_cover_empty_and_api_paths():
    assert _humanize("hello_world") == "Hello world"
    assert _humanize("___") == "API"
    assert _derive_tag_from_path("/api/v1/events/{event_id}") == "events"
    assert _derive_tag_from_path("/health") == "health"
    assert _derive_tag_from_path("/") == "root"


def test_default_operation_description_prefers_summary_then_operation_id():
    assert (
        _default_operation_description("get", "/items", {"summary": "  List  "})
        == "List"
    )
    assert (
        _default_operation_description("post", "/items", {"operationId": "create_item"})
        == "Create item"
    )
    assert (
        _default_operation_description("get", "/items", {"tags": ["catalog"]})
        == "GET /items for catalog resources."
    )
    assert (
        _default_operation_description("get", "/items", {})
        == "GET /items for items resources."
    )


def test_harden_openapi_schema_handles_irregular_nodes_and_marks_nested_pii():
    schema = {
        "info": "legacy-info",
        "paths": {
            "/ignored": "not-an-operation",
            "/api/v1/items": {
                "parameters": {},
                "options": {},
                "get": "not-an-operation",
                "post": {"tags": [], "responses": {}},
            },
        },
        "tags": [
            {"name": "existing", "description": "kept"},
            {"description": "ignored"},
            "ignored",
        ],
        "components": {
            "schemas": [
                {
                    "properties": {
                        "email": {},
                        "phone": "not-a-schema",
                        "nested": {"properties": {"password_hash": {}}},
                    }
                }
            ]
        },
    }

    result = harden_openapi_schema(schema)

    assert result["servers"]
    assert result["tags"] == [
        {"name": "existing", "description": "kept"},
        {"name": "items", "description": "Items API operations."},
    ]
    operation = result["paths"]["/api/v1/items"]["post"]
    assert operation["description"] == "POST /api/v1/items for items resources."
    assert result["components"]["schemas"][0]["properties"]["email"]["x-pii"] is True
    assert (
        result["components"]["schemas"][0]["properties"]["nested"]["properties"][
            "password_hash"
        ]["x-pii"]
        is True
    )


def test_harden_openapi_schema_accepts_non_mapping_paths_and_tags():
    schema = {"info": {}, "paths": "legacy", "tags": "legacy"}

    result = harden_openapi_schema(schema)

    assert result["info"]["contact"]["name"]
    assert result["tags"] == []


def test_harden_openapi_schema_injects_all_known_response_links():
    schema = {
        "paths": {
            "/api/v1/auth/login": {
                "post": {
                    "operationId": "login_api_v1_auth_login_post",
                    "description": "Documented login operation.",
                    "responses": {"200": {}},
                }
            },
            "/api/v1/events": {
                "post": {
                    "operationId": "create_event_api_v1_events_post",
                    "responses": {"201": {}},
                }
            },
            "/api/v1/chats": {
                "post": {
                    "operationId": "create_chat_api_v1_chats_post",
                    "responses": {"200": {}},
                }
            },
        }
    }

    result = harden_openapi_schema(schema)

    assert (
        result["paths"]["/api/v1/auth/login"]["post"]["responses"]["200"]["links"][
            "GetCurrentUser"
        ]["operationId"]
        == "get_me_api_v1_users_me_get"
    )
    assert (
        result["paths"]["/api/v1/events"]["post"]["responses"]["201"]["links"][
            "GetEventById"
        ]["parameters"]["event_id"]
        == "$response.body#/id"
    )
    assert (
        result["paths"]["/api/v1/chats"]["post"]["responses"]["200"]["links"][
            "GetChatMessages"
        ]["parameters"]["chat_id"]
        == "$response.body#/id"
    )


def test_install_custom_openapi_builds_once_and_reuses_schema():
    app = FastAPI(title="Closure API", version="1.0.0")

    @app.get("/health")
    def health():
        return {"ok": True}

    install_custom_openapi(app)

    first = app.openapi()
    second = app.openapi()

    assert first is second
    assert first["servers"][0]["url"] == "/"
    assert first["paths"]["/health"]["get"]["description"]
