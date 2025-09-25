import pytest
from pydantic import ValidationError

from app.schemas import schemas

pytestmark = pytest.mark.anyio("asyncio")

def test_user_create_requires_valid_email():
    with pytest.raises(ValidationError):
        schemas.UserCreate(email="invalid-email", password="secret")


def test_user_profile_update_validates_email():
    with pytest.raises(ValidationError):
        schemas.UserProfileUpdate(email="not-an-email")


async def test_user_out_contract(user_factory):
    user = await user_factory(full_name="Test User", spotify_is_connected=True, spotify_display_name="DJ Test")
    payload = schemas.UserOut.from_orm(user)
    data = payload.model_dump()

    assert data["id"] == user.id
    assert data["email"] == user.email
    assert data["spotify_connected"] is True
    assert data["spotify_is_connected"] is True
    assert "hashed_password" not in data
