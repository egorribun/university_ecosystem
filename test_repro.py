import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import models
from app.schemas import schemas
from app.services.user_service import UserService


async def run():
    repo = AsyncMock()
    audit = MagicMock()
    notifications = MagicMock()
    service = UserService(repo, audit, notifications)

    user = models.User(id=1, email="test@example.com")
    repo.get.return_value = user

    update_data = schemas.UserProfileUpdate(
        about="New about", institute="New institute", timezone="Europe/Moscow"
    )
    request = MagicMock()

    with patch(
        "app.services.user_profile_service.attach_pending_email", new_callable=AsyncMock
    ):
        try:
            await service.update_user_profile(user, update_data, request)
            print("SUCCESS")
        except Exception:
            import traceback

            traceback.print_exc()


asyncio.run(run())
