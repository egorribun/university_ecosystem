"""Keep nullable admin identity PATCH inputs consistent across API artifacts."""

import json
from pathlib import Path

from app.main import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_admin_update_openapi_artifacts_preserve_nullable_identity() -> None:
    live = app.openapi()["components"]["schemas"]["UserAdminUpdate"]
    properties = live["properties"]

    for field in ("email", "role", "full_name", "group_id"):
        assert {"type": "null"} in properties[field]["anyOf"]
        assert field not in live.get("required", [])
    assert {"format": "email", "type": "string"} in properties["email"]["anyOf"]
    assert {"$ref": "#/components/schemas/UserRole"} in properties["role"]["anyOf"]
    assert properties["email"]["x-pii"] is True

    for relative_path in (
        "frontend/openapi.json",
        "tests/contracts/snapshots/api_openapi_v1.json",
    ):
        tracked = json.loads(
            (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        )
        assert tracked["components"]["schemas"]["UserAdminUpdate"] == live


def test_admin_update_generated_types_preserve_nullable_identity() -> None:
    generated = (REPOSITORY_ROOT / "frontend/src/api/generated/types.gen.ts").read_text(
        encoding="utf-8"
    )
    identity = generated.split("export type UserAdminUpdate = {", 1)[1].split("}", 1)[0]

    assert "  email?: string | null\n" in identity
    assert "  role?: UserRole | null\n" in identity
    assert "  full_name?: string | null\n" in identity
    assert "  group_id?: string | null\n" in identity
