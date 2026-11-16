"""Admin identity updates preserve required fields and nullable profile clears."""

import pytest
from pydantic import ValidationError

from app.models.enums import UserRole
from app.schemas.users import UserAdminUpdate


@pytest.mark.parametrize("field", ["email", "role"])
def test_admin_update_rejects_null_required_identity(field: str) -> None:
    """An explicit null must fail before a non-null database column is changed."""
    with pytest.raises(ValidationError) as error:
        UserAdminUpdate.model_validate({field: None})

    assert error.value.errors()[0]["loc"] == (field,)


def test_admin_update_omitted_identity_fields_remain_unchanged() -> None:
    update = UserAdminUpdate(full_name="Updated Name")

    assert update.model_dump(exclude_unset=True) == {"full_name": "Updated Name"}


def test_admin_update_accepts_valid_email_and_role() -> None:
    update = UserAdminUpdate.model_validate(
        {"email": "updated@example.com", "role": "teacher"}
    )

    assert update.email == "updated@example.com"
    assert update.role is UserRole.TEACHER


def test_admin_update_can_still_clear_nullable_fields() -> None:
    update = UserAdminUpdate(full_name=None, group_id=None)

    assert update.model_dump(exclude_unset=True) == {
        "full_name": None,
        "group_id": None,
    }


def test_admin_update_schema_allows_omission_but_not_null_identity() -> None:
    schema = UserAdminUpdate.model_json_schema()
    properties = schema["properties"]

    assert properties["email"] == {
        "format": "email",
        "title": "Email",
        "type": "string",
    }
    assert properties["role"] == {"$ref": "#/$defs/UserRole"}
    assert "email" not in schema.get("required", [])
    assert "role" not in schema.get("required", [])
    assert {"type": "null"} in properties["full_name"]["anyOf"]
    assert {"type": "null"} in properties["group_id"]["anyOf"]
