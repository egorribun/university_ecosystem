"""Keep admin partial-update contracts consistent with runtime validation."""

import json
from pathlib import Path

from app.main import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_admin_update_openapi_artifacts_match_non_nullable_identity() -> None:
    live = app.openapi()["components"]["schemas"]["UserAdminUpdate"]
    properties = live["properties"]

    assert properties["email"] == {
        "format": "email",
        "title": "Email",
        "type": "string",
        "x-pii": True,
    }
    assert properties["role"] == {"$ref": "#/components/schemas/UserRole"}
    assert "email" not in live.get("required", [])
    assert "role" not in live.get("required", [])
    assert {"type": "null"} in properties["full_name"]["anyOf"]
    assert {"type": "null"} in properties["group_id"]["anyOf"]

    for relative_path in (
        "frontend/openapi.json",
        "tests/contracts/snapshots/api_openapi_v1.json",
    ):
        tracked = json.loads(
            (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        )
        assert tracked["components"]["schemas"]["UserAdminUpdate"] == live


def test_admin_update_generated_types_preserve_optional_non_nullable_identity() -> None:
    generated = (
        REPOSITORY_ROOT / "frontend/src/api/generated/types.gen.ts"
    ).read_text(encoding="utf-8")
    identity = generated.split("export type UserAdminUpdate = {", 1)[1].split("}", 1)[0]

    assert "  email?: string\n" in identity
    assert "  role?: UserRole\n" in identity
    assert "  full_name?: string | null\n" in identity
    assert "  group_id?: string | null\n" in identity
