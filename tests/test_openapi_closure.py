"""Branch closure tests for OpenAPI hardening helpers."""

from app.openapi import (
    _default_operation_description,
    _derive_tag_from_path,
    _humanize,
    harden_openapi_schema,
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
